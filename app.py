# app.py

import os
from flask import Flask, render_template, request, jsonify, redirect, url_for
import uuid
import json
import time
import asyncio
import concurrent.futures
import re
import difflib
import logging

from modules.pydantic_models import PYDANTIC_MODELS
from pydantic import ValidationError

from modules.storage import (
    save_project,
    load_project,
    ensure_storage_dir
)
from modules.workflow_manager import WorkflowManager, WorkflowStep, StepCall, FunctionCall
from modules.llm_interface import generate_llm_response
from modules.evaluation import evaluate_outputs
from modules.project_manager import ProjectManager
from modules.graph_generator import generate_mermaid
from modules.evaluation import evaluate_outputs

from markupsafe import Markup


from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)
workflows = {}  # In-memory store for demonstration; can use DB or JSON files

STORAGE_DIR = "workflows_data"
PROJECTS_DIR = "projects_data"  # New directory for projects

def replace_double_braces(template, variables):
    """
    Replaces double curly braces {{ }} with the corresponding values from variables.
    Now supports bracket/dict-based lookup, e.g. {{my_var['subfield']}}.
    """

    pattern = re.compile(r'{{\s*(.*?)\s*}}')

    def replacer(match):
        expr = match.group(1)
        if re.match(r'^[A-Za-z0-9_]+$', expr):
            # Simple variable
            if expr in variables:
                return str(variables[expr])
            else:
                raise KeyError(f"Variable '{expr}' not found.")
        else:
            # Attempt bracket/dict-based lookups
            try:
                import ast
                base_var_name = expr.split("[", 1)[0].strip()
                if base_var_name not in variables:
                    raise KeyError(f"Base variable '{base_var_name}' not found.")

                custom_var = variables[base_var_name]
                bracket_expr = expr[len(base_var_name):].strip()

                while bracket_expr.startswith("["):
                    end_index = bracket_expr.find("]")
                    if end_index == -1:
                        raise ValueError("Mismatched brackets in expression: " + expr)
                    key_str = bracket_expr[1:end_index].strip()
                    bracket_expr = bracket_expr[end_index+1:].strip()
                    key_str = key_str.strip("'\"")
                    if isinstance(custom_var, dict):
                        if key_str in custom_var:
                            custom_var = custom_var[key_str]
                        else:
                            raise KeyError(f"{key_str} not found in variable '{base_var_name}'")
                    else:
                        raise TypeError(f"Variable '{base_var_name}' is not a dictionary; cannot index '{key_str}'")
                return str(custom_var)

            except Exception as e:
                raise KeyError(f"Error accessing expression '{expr}': {str(e)}")

    return pattern.sub(replacer, template)


ensure_storage_dir()


@app.template_filter('tojson_no_escape')
def tojson_no_escape(value):
    """
    Custom Jinja2 filter to serialize data to JSON without escaping non-ASCII characters.
    """
    return Markup(json.dumps(value, ensure_ascii=False, indent=2))


# =====================================
# PROJECT ROUTES
# =====================================

@app.route("/projects", methods=["GET"])
def list_projects():
    # List all project files from projects_data
    project_files = os.listdir(PROJECTS_DIR)
    projects_data = {}
    for file in project_files:
        if file.endswith(".json"):
            project_id = file.replace(".json", "")
            project = load_project(project_id)
            if project:
                projects_data[project_id] = project
    return render_template("projects_index.html", projects=projects_data)

@app.route("/projects/create", methods=["POST"])
def create_project_route():
    data = request.json
    project_name = data.get("name", "Untitled Project")
    description = data.get("description", "")

    # Generate a unique project_id
    project_id = str(uuid.uuid4())

    # Pass the project_id when creating ProjectManager
    new_project = ProjectManager(project_id=project_id, name=project_name, description=description)
    project_dict = new_project.to_dict()
    save_project(new_project.project_id, project_dict)

    app.logger.info(f"Created new project: {project_name} with ID: {new_project.project_id}")
    return jsonify({"status": "success", "project_id": new_project.project_id})

@app.route("/projects/<project_id>", methods=["GET"])
def get_project_route(project_id):
    project_data = load_project(project_id)
    if not project_data:
        app.logger.error(f"Project not found: {project_id}")
        return "Project not found", 404

    pm = ProjectManager.from_dict(project_data)
    workflows_data = {}
    for wf in pm.workflows:
        workflows_data[wf['workflow_id']] = wf

    return render_template("project_detail.html", project=project_data, workflows=workflows_data)

@app.route("/projects/<project_id>/edit", methods=["POST"])
def edit_project(project_id):
    data = request.json
    project_data = load_project(project_id)
    if not project_data:
        app.logger.error(f"Project not found: {project_id}")
        return jsonify({"error": "Project not found"}), 404

    pm = ProjectManager.from_dict(project_data)
    pm.name = data.get("name", pm.name)
    pm.description = data.get("description", pm.description)
    updated_dict = pm.to_dict()
    save_project(project_id, updated_dict)

    app.logger.info(f"Edited project: {project_id}")
    return jsonify({"status": "project_edited", "project": updated_dict})

@app.route("/projects/<project_id>/remove", methods=["POST"])
def remove_project(project_id):
    project_data = load_project(project_id)
    if not project_data:
        app.logger.error(f"Project not found: {project_id}")
        return jsonify({"error": "Project not found"}), 404

    # Remove the project JSON
    p_path = os.path.join(PROJECTS_DIR, f"{project_id}.json")
    if os.path.exists(p_path):
        os.remove(p_path)
        app.logger.info(f"Deleted project file: {p_path}")

    return jsonify({"status": "project_removed"})

# =====================================
# WORKFLOW ROUTES UNDER PROJECTS
# =====================================

@app.route("/projects/<project_id>/add_workflow", methods=["POST"])
def add_workflow_to_project(project_id):
    data = request.json
    workflow_name = data.get("workflow_name", "Untitled Workflow")
    workflow_description = data.get("workflow_description", "")

    project_data = load_project(project_id)
    if not project_data:
        app.logger.error(f"Project not found: {project_id}")
        return jsonify({"error": "Project not found"}), 404

    pm = ProjectManager.from_dict(project_data)

    new_wf_id = str(uuid.uuid4())
    new_workflow = {
        "workflow_id": new_wf_id,
        "name": workflow_name,
        "workflow_description": workflow_description,
        "steps": [],
        "variables": {}
    }
    pm.add_workflow(new_workflow)

    # Preserve other fields like 'evaluations'
    project_data['workflows'] = pm.to_dict()['workflows']
    save_project(project_id, project_data)

    app.logger.info(f"Added new workflow '{workflow_name}' with ID: {new_wf_id} to project {project_id}.")
    return jsonify({"status": "workflow_added", "workflow_id": new_wf_id})


@app.route("/projects/<project_id>/delete_workflow", methods=["POST"])
def delete_workflow_under_project(project_id):
    data = request.json
    workflow_id = data.get("workflow_id")

    project_data = load_project(project_id)
    if not project_data:
        app.logger.error(f"Project not found: {project_id}")
        return jsonify({"error": "Project not found"}), 404

    pm = ProjectManager.from_dict(project_data)
    workflow_exists = any(wf['workflow_id'] == workflow_id for wf in pm.workflows)
    if not workflow_exists:
        app.logger.error(f"Workflow '{workflow_id}' not found in project {project_id}.")
        return jsonify({"error": "Workflow not found in project"}), 404

    pm.remove_workflow(workflow_id)

    # Preserve other fields like 'evaluations'
    project_data['workflows'] = pm.to_dict()['workflows']
    save_project(project_id, project_data)

    app.logger.info(f"Removed workflow '{workflow_id}' from project {project_id}.")
    return jsonify({"status": "workflow_deleted"})


@app.route("/projects/<project_id>/copy_workflow", methods=["POST"])
def copy_workflow_under_project(project_id):
    data = request.json
    source_workflow_id = data.get("workflow_id")

    project_data = load_project(project_id)
    if not project_data:
        app.logger.error(f"Project not found: {project_id}")
        return jsonify({"error": "Project not found"}), 404

    pm = ProjectManager.from_dict(project_data)
    workflow_exists = any(wf['workflow_id'] == source_workflow_id for wf in pm.workflows)
    if not workflow_exists:
        app.logger.error(f"Workflow '{source_workflow_id}' not found in project {project_id}.")
        return jsonify({"error": "Workflow not found in project"}), 404

    new_wf_id = pm.copy_workflow(source_workflow_id)
    if new_wf_id:
        # Preserve other fields like 'evaluations'
        project_data['workflows'] = pm.to_dict()['workflows']
        save_project(project_id, project_data)

        app.logger.info(f"Copied workflow '{source_workflow_id}' to new workflow '{new_wf_id}' in project {project_id}.")
        return jsonify({"status": "workflow_copied", "new_workflow_id": new_wf_id})
    else:
        app.logger.error(f"Failed to copy workflow '{source_workflow_id}' in project {project_id}.")
        return jsonify({"error": "Failed to copy workflow"}), 500


# =====================================
# MAIN PAGE ROUTE
# =====================================

@app.route("/")
def home():
    return redirect(url_for('list_projects'))

# =====================================
# WORKFLOW ROUTES WITHIN PROJECTS
# =====================================

@app.route("/projects/<project_id>/workflow/<workflow_id>", methods=["GET"])
def get_workflow(project_id, workflow_id):
    project_data = load_project(project_id)
    if not project_data:
        app.logger.error(f"Project not found: {project_id}")
        return "Project not found", 404

    pm = ProjectManager.from_dict(project_data)
    workflow = next((wf for wf in pm.workflows if wf['workflow_id'] == workflow_id), None)
    if not workflow:
        app.logger.error(f"Workflow not found: {workflow_id} in project {project_id}")
        return "Workflow not found", 404

    # **Corrected Line: Pass the 'project' object to the template**
    return render_template("workflow_detail.html", workflow=workflow, project_id=project_id, project=project_data)

@app.route("/projects/<project_id>/workflow/create", methods=["POST"])
def create_workflow_route(project_id):
    # Legacy route: Associate with a specific project
    data = request.json
    workflow_name = data.get("workflow_name", "Untitled Workflow")
    workflow_description = data.get("workflow_description", "")
    # Assuming the project exists; else, return error
    project_data = load_project(project_id)
    if not project_data:
        app.logger.error(f"Project not found: {project_id}")
        return jsonify({"error": "Project not found"}), 404

    pm = ProjectManager.from_dict(project_data)

    new_wf_id = str(uuid.uuid4())
    new_workflow = {
        "workflow_id": new_wf_id,
        "name": workflow_name,
        "workflow_description": workflow_description,
        "steps": [],
        "variables": {}
    }
    pm.add_workflow(new_workflow)

    # Preserve other fields like 'evaluations'
    project_data['workflows'] = pm.to_dict()['workflows']
    save_project(project_id, project_data)

    app.logger.info(f"Created new workflow: {workflow_name} with ID: {new_wf_id} under project {project_id}.")
    return jsonify({"status": "success", "workflow_id": new_wf_id})


@app.route("/projects/<project_id>/workflow/<workflow_id>/add_step", methods=["POST"])
def add_step_route(project_id, workflow_id):
    data = request.json
    if not data:
        app.logger.error("No JSON data received in add_step.")
        return jsonify({"error": "No data provided"}), 400

    title = data.get("title", "").strip()  # UPDATED: Extract title if provided
    description = data.get("description", "").strip()
    inputs = data.get("inputs", "").strip()
    calls_data = data.get("calls", [])

    if not isinstance(calls_data, list):
        return jsonify({"error": "'calls' must be a list of subcalls."}), 400

    project_data = load_project(project_id)
    if project_data is None:
        app.logger.error(f"Project not found: {project_id}")
        return jsonify({"error": "Project not found"}), 404

    pm = ProjectManager.from_dict(project_data)
    workflow = next((wf for wf in pm.workflows if wf['workflow_id'] == workflow_id), None)
    if not workflow:
        app.logger.error(f"Workflow not found: {workflow_id} in project {project_id}")
        return jsonify({"error": "Workflow not found"}), 404

    new_step = WorkflowStep(
        title=title,
        description=description,
        inputs=inputs,
        calls=[]
    )

    for cdata in calls_data:
        call_id = str(uuid.uuid4())
        call_title = cdata.get("title", "").strip()  # NEW: Extract title
        sc = StepCall(
            call_id=call_id,
            title=call_title,  # NEW: Assign title
            system_prompt=cdata.get("system_prompt", "").strip(),
            user_prompt=cdata.get("user_prompt", "").strip(),
            variable_name=cdata.get("variable_name", "").strip(),
            variables=cdata.get("variables", {}),
            model_name=cdata.get("model_name", "gpt-4"),
            temperature=cdata.get("temperature", 1.0),
            max_tokens=cdata.get("max_tokens", 1024),
            top_p=cdata.get("top_p", 1.0),
            output_type=cdata.get("output_type", "text"),
            conversation=cdata.get("conversation", [])  # Ensure conversation is included
        )
        new_step.calls.append(sc)

    manager = WorkflowManager.from_dict(workflow)
    manager.add_step(new_step)
    updated_workflow = manager.to_dict()

    # Update the workflow in the project
    for idx, wf in enumerate(pm.workflows):
        if wf['workflow_id'] == workflow_id:
            pm.workflows[idx] = updated_workflow
            break

    # Preserve other fields like 'evaluations'
    project_data['workflows'] = pm.to_dict()['workflows']
    save_project(project_id, project_data)
    workflows[workflow_id] = updated_workflow

    app.logger.info(f"Added step {new_step.step_id} to workflow {workflow_id} in project {project_id}")
    return jsonify({"status": "step_added", "workflow": updated_workflow})


@app.route("/projects/<project_id>/workflow/<workflow_id>/edit_step", methods=["POST"])
def edit_step_route(project_id, workflow_id):
    data = request.json
    step_id = data.get("step_id")
    title = data.get("title")
    description = data.get("description")
    inputs = data.get("inputs")
    calls = data.get("calls")

    project_data = load_project(project_id)
    if not project_data:
        return jsonify({"status": "error", "error": "Project not found."}), 404

    pm = ProjectManager.from_dict(project_data)
    workflow = next((wf for wf in pm.workflows if wf['workflow_id'] == workflow_id), None)
    if not workflow:
        return jsonify({"status": "error", "error": "Workflow not found."}), 404

    manager = WorkflowManager.from_dict(workflow)
    for step in manager.steps:
        if step.step_id == step_id:
            step.title = title
            step.description = description
            step.inputs = inputs
            processed_calls = []
            for call in calls:
                processed_call = StepCall.from_dict(call)
                processed_calls.append(processed_call)
            step.calls = processed_calls
            break
    else:
        return jsonify({"status": "error", "error": "Step not found."}), 404

    updated_workflow = manager.to_dict()

    # Update the workflow in the project
    for idx, wf in enumerate(pm.workflows):
        if wf['workflow_id'] == workflow_id:
            pm.workflows[idx] = updated_workflow
            break

    # Preserve other fields like 'evaluations'
    project_data['workflows'] = pm.to_dict()['workflows']
    save_project(project_id, project_data)
    workflows[workflow_id] = updated_workflow

    app.logger.info(f"Edited step {step_id} in workflow {workflow_id} of project {project_id}")
    return jsonify({"status": "step_edited"}), 200


@app.route("/projects/<project_id>/workflow/<workflow_id>/remove_step", methods=["POST"])
def remove_step_route(project_id, workflow_id):
    data = request.json
    step_id = data.get("step_id")
    
    if not step_id:
        logging.error("No step_id provided in the request.")
        return jsonify({"error": "No step_id provided"}), 400
    
    # Load project data
    project_data = load_project(project_id)
    if not project_data:
        logging.error(f"Project with ID {project_id} not found.")
        return jsonify({"error": "Project not found"}), 404
    
    pm = ProjectManager.from_dict(project_data)
    workflow_data = next((wf for wf in pm.workflows if wf['workflow_id'] == workflow_id), None)
    if not workflow_data:
        logging.error(f"Workflow with ID {workflow_id} not found in project {project_id}.")
        return jsonify({"error": "Workflow not found"}), 404
    
    manager = WorkflowManager.from_dict(workflow_data)
    
    # Check if the step exists
    step_exists = any(step.step_id == step_id for step in manager.steps)
    if not step_exists:
        logging.error(f"Step with ID {step_id} not found in workflow {workflow_id}.")
        return jsonify({"error": "Step not found"}), 404
    
    # Remove the step
    original_step_count = len(manager.steps)
    manager.steps = [step for step in manager.steps if step.step_id != step_id]
    removed_step_count = original_step_count - len(manager.steps)
    
    if removed_step_count == 0:
        logging.error(f"Failed to remove step with ID {step_id}.")
        return jsonify({"error": "Failed to remove step"}), 500
    
    # Serialize and save back
    updated_workflow = manager.to_dict()
    for idx, wf in enumerate(pm.workflows):
        if wf['workflow_id'] == workflow_id:
            pm.workflows[idx] = updated_workflow
            break
    
    # Preserve other fields like 'evaluations'
    project_data['workflows'] = pm.to_dict()['workflows']
    save_project(project_id, project_data)
    workflows[workflow_id] = updated_workflow

    logging.info(f"Step {step_id} removed from workflow {workflow_id} in project {project_id}.")
    
    return jsonify({"status": "step_removed"}), 200


@app.route("/projects/<project_id>/workflow/<workflow_id>/reorder_steps", methods=["POST"])
def reorder_steps_route(project_id, workflow_id):
    data = request.json
    new_order = data.get("new_order")
    if not new_order or not isinstance(new_order, list):
        app.logger.error("Invalid new_order provided in reorder_steps.")
        return jsonify({"error": "Invalid new_order"}), 400

    project_data = load_project(project_id)
    if project_data is None:
        app.logger.error(f"Project not found: {project_id}")
        return jsonify({"error": "Project not found"}), 404

    pm = ProjectManager.from_dict(project_data)
    workflow = next((wf for wf in pm.workflows if wf['workflow_id'] == workflow_id), None)
    if not workflow:
        app.logger.error(f"Workflow not found: {workflow_id} in project {project_id}")
        return jsonify({"error": "Workflow not found"}), 404

    manager = WorkflowManager.from_dict(workflow)
    manager.reorder_steps(new_order)
    updated_workflow = manager.to_dict()

    # Update the workflow in the project
    for idx, wf in enumerate(pm.workflows):
        if wf['workflow_id'] == workflow_id:
            pm.workflows[idx] = updated_workflow
            break

    # Preserve other fields like 'evaluations'
    project_data['workflows'] = pm.to_dict()['workflows']
    save_project(project_id, project_data)
    workflows[workflow_id] = updated_workflow

    app.logger.info(f"Reordered steps in workflow {workflow_id} of project {project_id} to: {new_order}")
    return jsonify({"status": "steps_reordered", "workflow": updated_workflow})


@app.route("/projects/<project_id>/workflow/<workflow_id>/add_variable", methods=["POST"])
def add_variable_route(project_id, workflow_id):
    data = request.json
    var_name = data.get("var_name", "").strip()
    var_content = data.get("var_content", "").strip()

    if not var_name:
        app.logger.error("No var_name provided in add_variable.")
        return jsonify({"error": "Variable name is required."}), 400

    project_data = load_project(project_id)
    if project_data is None:
        app.logger.error(f"Project not found: {project_id}")
        return jsonify({"error": "Project not found"}), 404

    pm = ProjectManager.from_dict(project_data)
    workflow = next((wf for wf in pm.workflows if wf['workflow_id'] == workflow_id), None)
    if not workflow:
        app.logger.error(f"Workflow not found: {workflow_id} in project {project_id}")
        return jsonify({"error": "Workflow not found"}), 404

    if var_name in workflow['variables']:
        app.logger.error(f"Variable '{var_name}' already exists in workflow {workflow_id}.")
        return jsonify({"error": f"Variable '{var_name}' already exists."}), 400

    workflow['variables'][var_name] = var_content

    # Update the workflow in the project
    for idx, wf in enumerate(pm.workflows):
        if wf['workflow_id'] == workflow_id:
            pm.workflows[idx] = workflow
            break

    # Preserve other fields like 'evaluations'
    project_data['workflows'] = pm.to_dict()['workflows']
    save_project(project_id, project_data)
    workflows[workflow_id] = workflow

    app.logger.info(f"Added variable '{var_name}' to workflow {workflow_id} in project {project_id}.")
    return jsonify({"status": "variable_added", "workflow": workflow})


@app.route("/projects/<project_id>/workflow/<workflow_id>/edit_variable", methods=["POST"])
def edit_variable_route(project_id, workflow_id):
    data = request.json
    var_name = data.get("var_name", "").strip()
    var_content = data.get("var_content", "").strip()

    if not var_name:
        app.logger.error("No var_name provided in edit_variable.")
        return jsonify({"error": "Variable name is required."}), 400

    project_data = load_project(project_id)
    if project_data is None:
        app.logger.error(f"Project not found: {project_id}")
        return jsonify({"error": "Project not found"}), 404

    pm = ProjectManager.from_dict(project_data)
    workflow = next((wf for wf in pm.workflows if wf['workflow_id'] == workflow_id), None)
    if not workflow:
        app.logger.error(f"Workflow not found: {workflow_id} in project {project_id}")
        return jsonify({"error": "Workflow not found"}), 404

    if var_name not in workflow['variables']:
        app.logger.error(f"Variable '{var_name}' does not exist in workflow {workflow_id}.")
        return jsonify({"error": f"Variable '{var_name}' does not exist."}), 404

    workflow['variables'][var_name] = var_content

    # Update the workflow in the project
    for idx, wf in enumerate(pm.workflows):
        if wf['workflow_id'] == workflow_id:
            pm.workflows[idx] = workflow
            break

    # Preserve other fields like 'evaluations'
    project_data['workflows'] = pm.to_dict()['workflows']
    save_project(project_id, project_data)
    workflows[workflow_id] = workflow

    app.logger.info(f"Edited variable '{var_name}' in workflow {workflow_id} of project {project_id}.")
    return jsonify({"status": "variable_edited", "workflow": workflow})


@app.route("/projects/<project_id>/workflow/<workflow_id>/remove_variable", methods=["POST"])
def remove_variable_route(project_id, workflow_id):
    data = request.json
    var_name = data.get("var_name", "").strip()

    if not var_name:
        app.logger.error("No var_name provided in remove_variable.")
        return jsonify({"error": "Variable name is required."}), 400

    project_data = load_project(project_id)
    if project_data is None:
        app.logger.error(f"Project not found: {project_id}")
        return jsonify({"error": "Project not found"}), 404

    pm = ProjectManager.from_dict(project_data)
    workflow = next((wf for wf in pm.workflows if wf['workflow_id'] == workflow_id), None)
    if not workflow:
        app.logger.error(f"Workflow not found: {workflow_id} in project {project_id}")
        return jsonify({"error": "Workflow not found"}), 404

    if var_name not in workflow['variables']:
        app.logger.error(f"Variable '{var_name}' does not exist in workflow {workflow_id}.")
        return jsonify({"error": f"Variable '{var_name}' does not exist."}), 404

    del workflow['variables'][var_name]

    # Update the workflow in the project
    for idx, wf in enumerate(pm.workflows):
        if wf['workflow_id'] == workflow_id:
            pm.workflows[idx] = workflow
            break

    # Preserve other fields like 'evaluations'
    project_data['workflows'] = pm.to_dict()['workflows']
    save_project(project_id, project_data)
    workflows[workflow_id] = workflow

    app.logger.info(f"Removed variable '{var_name}' from workflow {workflow_id} in project {project_id}.")
    return jsonify({"status": "variable_removed", "workflow": workflow})



# =====================================
# ADDITIONAL ROUTES FOR COMMON VARIABLE NAMES AT PROJECT LEVEL
# =====================================

@app.route("/projects/<project_id>/add_common_variable_name", methods=["POST"])
def add_common_variable_name(project_id):
    """
    Adds a new common variable name to the project.
    """
    data = request.json
    var_name = data.get("var_name", "").strip()

    if not var_name:
        app.logger.error("No var_name provided in add_common_variable_name.")
        return jsonify({"error": "Variable name is required."}), 400

    project_data = load_project(project_id)
    if not project_data:
        app.logger.error(f"Project not found: {project_id}")
        return jsonify({"error": "Project not found"}), 404

    pm = ProjectManager.from_dict(project_data)

    if var_name in pm.common_variable_names:
        app.logger.error(f"Variable name '{var_name}' already exists in project {project_id}.")
        return jsonify({"error": f"Variable name '{var_name}' already exists."}), 400

    try:
        pm.add_common_variable_name(var_name)
        save_project(project_id, pm.to_dict())
        app.logger.info(f"Added common variable name '{var_name}' to project {project_id}.")
        return jsonify({"status": "common_variable_name_added", "var_name": var_name})
    except Exception as e:
        app.logger.error(f"Error adding common variable name '{var_name}' to project {project_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/projects/<project_id>/remove_common_variable_name", methods=["POST"])
def remove_common_variable_name(project_id):
    """
    Removes an existing common variable name from the project.
    """
    data = request.json
    var_name = data.get("var_name", "").strip()

    if not var_name:
        app.logger.error("No var_name provided in remove_common_variable_name.")
        return jsonify({"error": "Variable name is required."}), 400

    project_data = load_project(project_id)
    if not project_data:
        app.logger.error(f"Project not found: {project_id}")
        return jsonify({"error": "Project not found"}), 404

    pm = ProjectManager.from_dict(project_data)

    if var_name not in pm.common_variable_names:
        app.logger.error(f"Variable name '{var_name}' does not exist in project {project_id}.")
        return jsonify({"error": f"Variable name '{var_name}' does not exist."}), 404

    try:
        pm.remove_common_variable_name(var_name)
        save_project(project_id, pm.to_dict())
        app.logger.info(f"Removed common variable name '{var_name}' from project {project_id}.")
        return jsonify({"status": "common_variable_name_removed", "var_name": var_name})
    except Exception as e:
        app.logger.error(f"Error removing common variable name '{var_name}' from project {project_id}: {str(e)}")
        return jsonify({"error": str(e)}), 500

# =====================================
# RUN WORKFLOW ROUTE
# =====================================

@app.route("/report/<project_id>/<workflow_id>")
def get_report(project_id, workflow_id):
    project_data = load_project(project_id)
    if not project_data:
        app.logger.error(f"Project not found: {project_id}")
        return "Project not found", 404
    pm = ProjectManager.from_dict(project_data)
    workflow = next((wf for wf in pm.workflows if wf['workflow_id'] == workflow_id), None)
    if not workflow:
        app.logger.error(f"Workflow not found: {workflow_id} in project {project_id}")
        return "Workflow not found", 404
    return jsonify(workflow)

@app.route("/projects/<project_id>/workflow/<workflow_id>/run", methods=["POST"])
def run_workflow(project_id, workflow_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided."}), 400

    initial_variables = data.get("variables", {})

    try:
        step_results = run_workflow_synchronously(project_id, workflow_id, initial_variables)
        return jsonify({"status": "success", "outputs": step_results}), 200
    except Exception as e:
        app.logger.error(f"Error running workflow: {e}")
        return jsonify({"error": str(e)}), 500



def format_per_step_outputs(per_step_outputs):
    formatted_steps = []
    for step in per_step_outputs:
        # Format LLM calls
        formatted_calls = []
        for call in step.get("calls", []):
            formatted_calls.append({
                "call_id": call["call_id"],
                "title": call["title"],
                "system_prompt": call["system_prompt"],
                "conversation": call.get("conversation", []),
                "response": call["response"],
                "model_name": call["model_name"],
                "variable_name": call["variable_name"]
            })

        # Format Function calls
        formatted_functions = []
        for fn in step.get("functions", []):
            formatted_functions.append({
                "call_id": fn["call_id"],
                "title": fn["title"],
                "code": fn["code"],
                "input_variables": fn["input_variables"],
                "output_variable": fn["output_variable"],
                "response": fn["response"]
            })

        formatted_steps.append({
            "step_id": step["step_id"],
            "step_title": step["step_title"],
            "calls": formatted_calls,
            "functions": formatted_functions
        })
    return formatted_steps



async def run_subcalls_in_parallel(subcall_prompts, workflow_variables):
    """
    Executes multiple LLM calls in parallel with proper variable substitution.
    
    Args:
        subcall_prompts (list): List of StepCall objects representing LLM calls.
        workflow_variables (dict): Dictionary of workflow-level variables.
    
    Returns:
        list: List of results from each LLM call.
    """
    with concurrent.futures.ThreadPoolExecutor() as pool:
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(
                pool,
                run_single_call,
                call_obj,
                {**workflow_variables, **call_obj.variables}  # Merge workflow and call-specific variables
            )
            for call_obj in subcall_prompts
        ]
        results = await asyncio.gather(*tasks)
    return results

def parse_potential_json(raw_text):
    """
    Attempt to parse raw_text as JSON, even if it's wrapped in triple backticks
    or has extraneous text. If parsing fails, returns an error string.
    """
    print("Attempting to parse raw_text as JSON...")
    # Remove code fences like ```json ... ``` or plain ```
    content_str = re.sub(r"```(\w+)?", "", raw_text).strip()
    content_str = re.sub(r"```", "", content_str).strip()
    #print(f"Cleaned content for parsing: {content_str}")

    # Attempt to parse the cleaned string
    try:
        parsed = json.loads(content_str)
        print("JSON parsing successful.")
        return parsed
    except json.JSONDecodeError as e:
        print(f"Initial JSON parsing failed: {e}")
        # Attempt to find a JSON substring
        start_index = content_str.find("{")
        end_index = content_str.rfind("}")
        if start_index != -1 and end_index != -1 and end_index > start_index:
            json_substring = content_str[start_index:end_index+1]
            print(f"Attempting to parse JSON substring: {json_substring}")
            try:
                parsed = json.loads(json_substring)
                print("JSON substring parsing successful.")
                return parsed
            except json.JSONDecodeError as e_sub:
                print(f"JSON substring parsing failed: {e_sub}")
        # If parsing fails, return an error string
        error_message = f"[JSON PARSE ERROR] {raw_text}"
        print(f"Returning error message: {error_message}")
        return error_message

    

@app.route("/pydantic_models", methods=["GET"])
def list_pydantic_models():
    from modules.pydantic_models import PYDANTIC_MODELS
    return jsonify({"models": list(PYDANTIC_MODELS.keys())})


def resolve_ref(schema: dict, ref: str) -> dict:
    """Resolve a `$ref` in the schema."""
    if ref.startswith("#/$defs/"):
        def_name = ref.split("/")[-1]
        return schema["$defs"][def_name]
    raise ValueError(f"Unsupported $ref format: {ref}")


def generate_json_schema(schema: dict) -> dict:
    """
    Generate a JSON-like structure from a Pydantic schema where keys are field names,
    and values are their descriptions and types in a human-readable format.
    """
    json_structure = {}
    properties = schema.get("properties", {})

    for field, details in properties.items():
        if "$ref" in details:
            # Handle references
            ref_schema = resolve_ref(schema, details["$ref"])
            if not ref_schema:
                raise ValueError(f"Reference schema for '{field}' not found.")
            # Include a nested structure with descriptions and types for subfields
            json_structure[field] = {
                subfield: (
                    f"Description: {subdetails.get('description', 'No description provided.')} "
                    f"Data Type: {subdetails.get('type', 'unknown')}"
                )
                for subfield, subdetails in ref_schema.get("properties", {}).items()
            }
        else:
            # Include the field description and type directly
            json_structure[field] = (
                f"Description: {details.get('description', 'No description provided.')}. "
                f"Type: {details.get('type', 'unknown')}"
            )
    return json_structure


import json
from typing import Any, Dict
from pydantic import ValidationError

def run_call_with_pydantic_validation(call_obj, per_call_vars):
    """
    Handles the LLM call with Pydantic validation and retries.

    Args:
        call_obj (StepCall): The StepCall object containing call details.
        per_call_vars (dict): Variables to be used for prompt formatting.

    Returns:
        dict: A dictionary containing call details and response.
    """
    attempts = call_obj.max_retries + 1  # Total attempts
    parsed_output = None
    last_error = None  # To store the last encountered error

    print(f"Starting Pydantic validation for call '{call_obj.title}' with variable '{call_obj.variable_name}'.")

    for attempt in range(1, attempts + 1):
        print(f"Attempt {attempt} for call '{call_obj.title}'.")

        # Prepare prompts with variable substitution
        try:
            system_prompt_formatted = replace_double_braces(call_obj.system_prompt, per_call_vars)
            #print(f"Formatted system prompt: {system_prompt_formatted}")
        except KeyError as e:
            error_msg = f"Missing variable for prompt formatting: {e}"
            print(error_msg)
            app.logger.error(error_msg)
            return {"error": error_msg}

        conversation_formatted = []
        for msg in call_obj.conversation:
            try:
                formatted_content = replace_double_braces(msg["content"], per_call_vars)
                #print(f"Formatted conversation message ({msg['role']}): {formatted_content}")
            except KeyError as e:
                error_msg = f"Missing variable for prompt formatting in conversation: {e}"
                print(error_msg)
                app.logger.error(error_msg)
                return {"error": error_msg}
            conversation_formatted.append({
                "role": msg["role"],
                "content": formatted_content
            })

        # Inject Pydantic schema into system prompt if applicable
        if call_obj.pydantic_definition and call_obj.pydantic_definition in PYDANTIC_MODELS:
            pydantic_model = PYDANTIC_MODELS[call_obj.pydantic_definition]
            schema_dict = pydantic_model.schema()
            try:
                structured_schema = generate_json_schema(schema_dict)
                schema_json_str = json.dumps(structured_schema, indent=2)
                system_prompt_formatted += (
                    f"\n\nBelow is JSON like object that describes the expected structure of your output. Only respond in JSON.\n"
                    f"\n{schema_json_str}\n"
                )
                #print(f"Injected Pydantic schema into system prompt for model '{call_obj.pydantic_definition}'.")
                #print(f"System prompt with schema: {system_prompt_formatted}")
            except Exception as e:
                error_msg = f"Error generating JSON schema for model '{call_obj.pydantic_definition}': {e}"
                print(error_msg)
                app.logger.error(error_msg)
                return {"error": error_msg}

        # Build parameters for the LLM call
        llm_params = {
            "model_name": call_obj.model_name,
            "temperature": call_obj.temperature,
            "max_tokens": call_obj.max_tokens,
            "top_p": call_obj.top_p
        }
        #print(f"LLM parameters: {llm_params}")

        # Make the LLM call
        response = generate_llm_response(call_obj.model_name, {
            "system_prompt": system_prompt_formatted,
            "conversation": conversation_formatted
        }, llm_params)
        raw_output = response.get("content", "")
        #print(f"Raw LLM response: {raw_output}")

        # Parse the output
        if call_obj.output_type == "json":
            try:
                parsed_output = parse_potential_json(raw_output)
                if not isinstance(parsed_output, dict):
                    raise ValueError("Parsed output is not a dictionary.")
                #print(f"Parsed output: {parsed_output}")
            except (json.JSONDecodeError, ValueError) as parse_error:
                last_error = f"JSON parsing failed on attempt {attempt} for call '{call_obj.title}': {parse_error}"
                print(last_error)
                app.logger.warning(last_error)
                if attempt < attempts:
                    print(f"Retrying call '{call_obj.title}' due to JSON parsing failure (Attempt {attempt + 1}/{attempts})")
                    app.logger.info(f"Retrying call '{call_obj.title}' due to JSON parsing failure (Attempt {attempt + 1}/{attempts})")
                    continue  # Retry
                else:
                    # All attempts exhausted; return error with raw output
                    error_msg = f"All {attempts} attempts failed to parse JSON for call '{call_obj.title}'."
                    print(error_msg)
                    app.logger.error(error_msg)
                    return {
                        "error": error_msg,
                        "raw_response": raw_output,
                        "step_index": None,
                        "call_id": call_obj.call_id,
                        "title": call_obj.title,
                        "system_prompt": call_obj.system_prompt,
                        "conversation": conversation_formatted,
                        "model_name": call_obj.model_name,
                        "variable_name": call_obj.variable_name,
                        "call_obj": call_obj.to_dict()
                    }

            # Validate with Pydantic if applicable
            if call_obj.pydantic_definition:
                model_name = call_obj.pydantic_definition
                print(f"Using Pydantic model: {model_name} for validation.")
                if model_name in PYDANTIC_MODELS:
                    pydantic_model = PYDANTIC_MODELS[model_name]
                    try:
                        validated_data = pydantic_model(**parsed_output)
                        print(f"Pydantic validation successful for call '{call_obj.title}'.")
                        # If validation succeeds, return the validated data
                        return {
                            "step_index": None,
                            "call_id": call_obj.call_id,
                            "title": call_obj.title,
                            "system_prompt": call_obj.system_prompt,
                            "conversation": conversation_formatted,
                            "response": validated_data.dict(),
                            "model_name": call_obj.model_name,
                            "variable_name": call_obj.variable_name,
                            "call_obj": call_obj.to_dict()
                        }
                    except ValidationError as ve:
                        last_error = f"Pydantic validation failed on attempt {attempt} for call '{call_obj.title}': {ve}"
                        print(last_error)
                        app.logger.warning(last_error)
                        if attempt < attempts:
                            print(f"Retrying call '{call_obj.title}' due to Pydantic validation failure (Attempt {attempt + 1}/{attempts})")
                            app.logger.info(f"Retrying call '{call_obj.title}' due to Pydantic validation failure (Attempt {attempt + 1}/{attempts})")
                            continue  # Retry
                        else:
                            # All attempts exhausted; return error with parsed output
                            error_msg = f"All {attempts} attempts failed for Pydantic validation in call '{call_obj.title}'."
                            print(error_msg)
                            app.logger.error(error_msg)
                            return {
                                "error": error_msg,
                                "raw_response": parsed_output,
                                "step_index": None,
                                "call_id": call_obj.call_id,
                                "title": call_obj.title,
                                "system_prompt": call_obj.system_prompt,
                                "conversation": conversation_formatted,
                                "model_name": call_obj.model_name,
                                "variable_name": call_obj.variable_name,
                                "call_obj": call_obj.to_dict()
                            }
                else:
                    warning_msg = f"Pydantic model '{model_name}' not found. Skipping validation."
                    print(warning_msg)
                    app.logger.warning(warning_msg)
                    # Return the parsed JSON without validation
                    return {
                        "step_index": None,
                        "call_id": call_obj.call_id,
                        "title": call_obj.title,
                        "system_prompt": call_obj.system_prompt,
                        "conversation": conversation_formatted,
                        "response": parsed_output,
                        "model_name": call_obj.model_name,
                        "variable_name": call_obj.variable_name,
                        "call_obj": call_obj.to_dict()
                    }
            else:
                # No Pydantic model specified; return parsed JSON
                print(f"No Pydantic model specified for call '{call_obj.title}'. Returning parsed JSON.")
                return {
                    "step_index": None,
                    "call_id": call_obj.call_id,
                    "title": call_obj.title,
                    "system_prompt": call_obj.system_prompt,
                    "conversation": conversation_formatted,
                    "response": parsed_output,
                    "model_name": call_obj.model_name,
                    "variable_name": call_obj.variable_name,
                    "call_obj": call_obj.to_dict()
                }
        else:
            # Non-JSON output
            parsed_output = raw_output
            print(f"Non-JSON output for call '{call_obj.title}': {parsed_output}")
            return {
                "step_index": None,
                "call_id": call_obj.call_id,
                "title": call_obj.title,
                "system_prompt": call_obj.system_prompt,
                "conversation": conversation_formatted,
                "response": parsed_output,
                "model_name": call_obj.model_name,
                "variable_name": call_obj.variable_name,
                "call_obj": call_obj.to_dict()
            }

    # If all attempts fail, return the last encountered error and the raw output
    final_error = f"All {attempts} attempts failed for call '{call_obj.title}'. Last error: {last_error}"
    print(final_error)
    app.logger.error(final_error)
    return {
        "error": final_error,
        "raw_response": raw_output if 'raw_output' in locals() else None,
        "step_index": None,
        "call_id": call_obj.call_id,
        "title": call_obj.title,
        "system_prompt": call_obj.system_prompt,
        "conversation": conversation_formatted,
        "model_name": call_obj.model_name,
        "variable_name": call_obj.variable_name,
        "call_obj": call_obj.to_dict()
    }





def run_single_call(call_obj, per_call_vars):
    """
    Executes a single call with Pydantic validation and retries.

    Args:
        call_obj (StepCall): The StepCall object containing call details.
        per_call_vars (dict): Variables to be used for prompt formatting.

    Returns:
        dict: A dictionary containing call details and response.
    """
    call_result = run_call_with_pydantic_validation(call_obj, per_call_vars)
    return call_result

@app.route("/projects/<project_id>/workflow/<workflow_id>/graph")
def workflow_graph(project_id, workflow_id):
    """
    Renders the Mermaid.js graph for the specified workflow.

    Args:
        project_id (str): The ID of the project.
        workflow_id (str): The ID of the workflow.

    Returns:
        Rendered HTML template with the Mermaid diagram.
    """
    project_data = load_project(project_id)
    if project_data is None:
        app.logger.error(f"Project not found: {project_id}")
        return "Project not found", 404

    pm = ProjectManager.from_dict(project_data)
    workflow = next((wf for wf in pm.workflows if wf['workflow_id'] == workflow_id), None)
    if workflow is None:
        app.logger.error(f"Workflow not found: {workflow_id} in project {project_id}")
        return "Workflow not found", 404

    mermaid_diagram = generate_mermaid(workflow)
    return render_template("workflow_graph.html", mermaid_diagram=mermaid_diagram, workflow_name=workflow.get("name", "Unnamed Workflow"))


# =====================================
# EVALUATION ROUTES
# =====================================

@app.route("/projects/<project_id>/evaluations", methods=["GET"])
def list_evaluations(project_id):
    project_data = load_project(project_id)
    if not project_data:
        return jsonify({"error": "Project not found"}), 404
    evaluations = project_data.get("evaluations", [])
    return jsonify(evaluations)


@app.route("/projects/<project_id>/evaluations/create", methods=["POST"])
def create_evaluation(project_id):
    data = request.json
    eval_name = data.get("name", "Untitled Evaluation")
    eval_description = data.get("description", "")
    variable_sets_input = data.get("variable_sets", {})  # Now expecting a dict or list

    project_data = load_project(project_id)
    if not project_data:
        return jsonify({"error": "Project not found"}), 404
    if "evaluations" not in project_data:
        project_data["evaluations"] = []

    variable_sets = {}

    if isinstance(variable_sets_input, dict):
        # If variable_sets are already keyed by IDs (e.g., from frontend), use them
        for key, vset in variable_sets_input.items():
            if key in variable_sets:
                # Ensure uniqueness
                return jsonify({"error": f"Duplicate variable set ID: {key}"}), 400
            variable_sets[key] = vset
    elif isinstance(variable_sets_input, list):
        # If variable_sets are a list, assign unique IDs
        for vset in variable_sets_input:
            unique_id = str(uuid.uuid4())
            variable_sets[unique_id] = vset
    else:
        return jsonify({"error": "Invalid format for variable_sets"}), 400

    new_eval = {
        "evaluation_id": str(uuid.uuid4()),
        "name": eval_name,
        "description": eval_description,
        "variable_sets": variable_sets,  # Now a dict with unique IDs as keys
        "results": {}
    }
    project_data["evaluations"].append(new_eval)
    save_project(project_id, project_data)
    return jsonify({
        "status": "evaluation_created",
        "evaluation_id": new_eval["evaluation_id"]
    })
    
    
@app.route("/projects/<project_id>/evaluations/<evaluation_id>", methods=["GET"])
def get_evaluation(project_id, evaluation_id):
    project_data = load_project(project_id)
    if not project_data:
        return jsonify({"error": "Project not found"}), 404
    evaluations = project_data.get("evaluations", [])
    evaluation = next((e for e in evaluations if e["evaluation_id"] == evaluation_id), None)
    if not evaluation:
        return jsonify({"error": "Evaluation not found"}), 404
    return jsonify(evaluation)

@app.route("/projects/<project_id>/evaluations/<evaluation_id>/delete", methods=["POST"])
def delete_evaluation(project_id, evaluation_id):
    project_data = load_project(project_id)
    if not project_data:
        return jsonify({"error": "Project not found"}), 404
    evaluations = project_data.get("evaluations", [])
    new_evals = [e for e in evaluations if e["evaluation_id"] != evaluation_id]
    if len(new_evals) == len(evaluations):
        return jsonify({"error": "Evaluation not found"}), 404
    project_data["evaluations"] = new_evals
    save_project(project_id, project_data)
    return jsonify({"status": "evaluation_deleted"})

@app.route("/projects/<project_id>/evaluations/<evaluation_id>/run", methods=["POST"])
def run_evaluation(project_id, evaluation_id):
    """
    Runs each workflow in the project multiple times using each variable set in the evaluation.
    Stores results and comparisons.
    Logs progress for workflows, variable sets, and iterations by printing to the terminal.
    Saves project data incrementally to prevent data loss in case of errors.
    Skips variable sets that have already been fully processed.
    """
    req_data = request.json

    project_data = load_project(project_id)
    if project_data is None:
        app.logger.error(f"Project not found: {project_id}")
        return jsonify({"error": "Project not found"}), 404

    evaluation = next((e for e in project_data["evaluations"] if e["evaluation_id"] == evaluation_id), None)
    if not evaluation:
        app.logger.error(f"Evaluation not found: {evaluation_id} in project {project_id}")
        return jsonify({"error": "Evaluation not found"}), 404

    workflows_data = project_data.get("workflows", [])
    total_workflows = len(workflows_data)
    if total_workflows == 0:
        app.logger.warning(f"No workflows found in project {project_id}.")
        print(f"No workflows found in project {project_id}.")
        return jsonify({"error": "No workflows to run in this project."}), 400

    variable_sets = evaluation.get("variable_sets", {})
    total_variable_sets = len(variable_sets)
    if total_variable_sets == 0:
        app.logger.warning(f"No variable sets found in evaluation {evaluation_id} of project {project_id}.")
        print(f"No variable sets found in evaluation {evaluation_id} of project {project_id}.")
        return jsonify({"error": "No variable sets to run in this evaluation."}), 400

    # Initialize results if not already present to support incremental updates
    if "results" not in evaluation:
        evaluation["results"] = {}
    results = evaluation["results"]

    try:
        # Enumerate workflows for logging
        for wf_index, wf in enumerate(workflows_data, start=1):
            wf_id = wf["workflow_id"]
            wf_name = wf.get("name", f"Workflow {wf_index}")
            print(f"Workflow {wf_index}/{total_workflows}: {wf_name}")
            app.logger.info(f"Starting Workflow {wf_index}/{total_workflows}: {wf_name}")

            if wf_id not in results:
                results[wf_id] = []

            # Enumerate variable sets for logging
            for var_set_index, (var_set_id, vset) in enumerate(variable_sets.items(), start=1):
                # Count already completed iterations for this variable set
                completed_runs = [
                    r for r in results[wf_id] if r.get("variable_set_id") == var_set_id
                ]
                num_completed = len(completed_runs)

                num_runs = vset.get("num_runs", 1)

                if num_completed >= num_runs:
                    print(f"Skipping Variable Set {var_set_index}/{total_variable_sets} (ID: {var_set_id}) for Workflow {wf_id}: already completed {num_completed}/{num_runs} iterations")
                    app.logger.info(f"Skipping Variable Set {var_set_index}/{total_variable_sets} (ID: {var_set_id}) for Workflow {wf_id}: already completed")
                    continue  # Skip this variable set as it is already complete

                print(f"Workflow {wf_index}/{total_workflows}: {wf_name}")
                print(f"  Variable Set {var_set_index}/{total_variable_sets} (ID: {var_set_id})")
                app.logger.info(f"  Processing Variable Set {var_set_index}/{total_variable_sets} (ID: {var_set_id}) for Workflow {wf_id}")

                # Setup the variables for this run by merging common variables with the specific variable set.
                variables_for_run = {}
                common_vars = project_data.get("common_variable_names", [])
                input_vars = vset.get("variables", {})
                for var_name in common_vars:
                    variables_for_run[var_name] = input_vars.get(var_name, "")

                ideal_output = vset.get("ideal_output", "")

                # Determine from which iteration to resume (1-based index for printing, 0-based in result)
                start_iteration = num_completed + 1

                # Enumerate iterations for logging and execution
                for run_i in range(start_iteration, num_runs + 1):
                    print(f"    Iteration {run_i}/{num_runs} (variable set {var_set_id} for workflow {wf_id})")
                    app.logger.info(f"    Starting Iteration {run_i}/{num_runs} for variable set {var_set_id} in workflow {wf_id}")

                    run_output = run_workflow_synchronously(project_id, wf_id, variables_for_run)
                    comparison = compare_outputs(run_output, ideal_output)

                    run_result = {
                        "variable_set_id": var_set_id,    # Store the unique ID
                        "run_index": run_i - 1,           # 0-based index as per original code
                        "output": run_output,
                        "comparison": comparison
                    }

                    results[wf_id].append(run_result)

                    # Incrementally save the project after each run
                    save_project(project_id, project_data)
                    app.logger.debug(f"Saved project data after run {run_i} of variable set {var_set_id} in workflow {wf_id}")

        print(f"Completed Evaluation {evaluation_id} for Project {project_id}")
        app.logger.info(f"Completed Evaluation {evaluation_id} for Project {project_id}")

        return jsonify({"status": "evaluation_run_complete", "results": results})

    except Exception as e:
        app.logger.error(f"An error occurred during evaluation: {str(e)}")
        print(f"An error occurred: {str(e)}")
        # Optionally, save the project data even if an error occurs
        save_project(project_id, project_data)
        return jsonify({"error": "An error occurred during evaluation.", "details": str(e)}), 500





@app.route("/projects/<project_id>/evaluations/<evaluation_id>/results/save_notes", methods=["POST"])
def save_evaluation_notes(project_id, evaluation_id):
    data = request.json
    variable_set_id = data.get("variable_set_id")  # Changed from index
    run_index = data.get("run_index")  # Keep run_index
    workflow_id = data.get("workflow_id")
    notes = data.get("notes", "")

    # Load the project
    project_data = load_project(project_id)
    if not project_data:
        return jsonify({"error": "Project not found"}), 404

    # Find the evaluation
    evaluations = project_data.get("evaluations", [])
    evaluation = next((e for e in evaluations if e["evaluation_id"] == evaluation_id), None)
    if not evaluation:
        return jsonify({"error": "Evaluation not found"}), 404

    # Access the results for the specific workflow
    results = evaluation.get("results", {})
    workflow_results = results.get(workflow_id, [])

    # Find the specific run based on variable_set_id and run_index
    for run in workflow_results:
        if run.get("variable_set_id") == variable_set_id and run.get("run_index") == run_index:
            run["notes"] = notes
            break
    else:
        return jsonify({"error": "Run not found"}), 404

    # Save the updated project data
    save_project(project_id, project_data)
    return jsonify({"status": "notes_saved"})



@app.route("/projects/<project_id>/evaluations/<evaluation_id>/results", methods=["GET"])
def view_evaluation_results(project_id, evaluation_id):
    project_data = load_project(project_id)
    if not project_data:
        return "Project not found", 404
    evaluations = project_data.get("evaluations", [])
    evaluation = next((e for e in evaluations if e["evaluation_id"] == evaluation_id), None)
    if not evaluation:
        return "Evaluation not found", 404
    
    # Pass the necessary data to the template
    return render_template("evaluation_results.html", project=project_data, evaluation=evaluation)


def run_workflow_synchronously(project_id, workflow_id, variables):
    """
    Runs the specified workflow synchronously with Pydantic validation and retries.
    
    Args:
        project_id (str): The ID of the project.
        workflow_id (str): The ID of the workflow.
        variables (dict): Initial variables for the workflow.
    
    Returns:
        list: A list of dictionaries, each representing a step with its calls and results.
    """
    # Load project and workflow
    project_data = load_project(project_id)
    if not project_data:
        app.logger.error(f"Project not found: {project_id}")
        return {"error": "Project not found"}

    pm = ProjectManager.from_dict(project_data)
    workflow_data = next((wf for wf in pm.workflows if wf['workflow_id'] == workflow_id), None)
    if workflow_data is None:
        app.logger.error(f"Workflow not found: {workflow_id}")
        return {"error": "Workflow not found"}

    manager = WorkflowManager.from_dict(workflow_data)
    context_variables = {**manager.variables, **variables}

    all_outputs = []

    # Initialize asyncio loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        for step in manager.steps:
            step_result = {
                "step_id": step.step_id,
                "step_title": step.title,
                "calls": []
            }
            
            # Collect call objects for the current step
            subcall_prompts = step.calls
            
            # Run all calls in the current step in parallel
            step_call_results = loop.run_until_complete(run_subcalls_in_parallel(subcall_prompts, context_variables))
            
            # Process each call's result
            for result in step_call_results:
                if "error" in result:
                    # Handle error accordingly
                    app.logger.error(f"Error in call '{result.get('title', 'Unnamed Call')}': {result['error']}")
                    step_result["calls"].append(result)
                    continue  # Or decide to halt the workflow

                step_result["calls"].append(result)

                # Store the response in context_variables if variable_name is set
                if result.get("call_obj") and result["call_obj"].get("variable_name") and "response" in result:
                    context_variables[result["call_obj"]["variable_name"]] = result["response"]

            all_outputs.append(step_result)

    finally:
        loop.close()

    return all_outputs




def format_prompts(call_obj, variables):
    # Re-use code similar to that in app.py for formatting prompts
    system_prompt_formatted = replace_double_braces(call_obj.system_prompt, variables)
    conversation_formatted = []
    for msg in call_obj.conversation:
        formatted_content = replace_double_braces(msg["content"], variables)
        conversation_formatted.append({
            "role": msg["role"],
            "content": formatted_content
        })
    return system_prompt_formatted, conversation_formatted

def compare_outputs(run_output, ideal_output):
    """
    A simple comparison method. You can enhance this:
    - If both are strings, measure similarity (e.g., Levenshtein distance, etc.)
    - If JSON, compare keys and values.
    """
    run_str = json.dumps(run_output, indent=2) if isinstance(run_output, (dict, list)) else str(run_output)
    ideal_str = json.dumps(ideal_output, indent=2) if isinstance(ideal_output, (dict, list)) else str(ideal_output)

    diff = difflib.unified_diff(ideal_str.splitlines(), run_str.splitlines())
    diff_text = "\n".join(diff)
    # Simple similarity ratio:
    seq = difflib.SequenceMatcher(None, ideal_str, run_str)
    similarity = seq.ratio()

    return {
        "match_score": round(similarity, 4),
        "differences": diff_text
    }


## FUnction Routes ##
@app.route("/projects/<project_id>/workflow/<workflow_id>/add_function", methods=["POST"])
def add_function_to_step(project_id, workflow_id):
    data = request.json
    step_id = data.get("step_id")
    title = data.get("title", "Untitled Function")
    code = data.get("code", "")
    input_variables = data.get("input_variables", {})
    output_variable = data.get("output_variable", "")

    project_data = load_project(project_id)
    if not project_data:
        return jsonify({"error": "Project not found"}), 404
    pm = ProjectManager.from_dict(project_data)
    workflow = next((wf for wf in pm.workflows if wf["workflow_id"] == workflow_id), None)
    if not workflow:
        return jsonify({"error": "Workflow not found"}), 404

    manager = WorkflowManager.from_dict(workflow)
    step = next((s for s in manager.steps if s.step_id == step_id), None)
    if not step:
        return jsonify({"error": "Step not found"}), 404

    new_call = FunctionCall(call_id=None, title=title, code=code, input_variables=input_variables, output_variable=output_variable)
    step.functions.append(new_call)

    updated_workflow = manager.to_dict()
    for idx, wf in enumerate(pm.workflows):
        if wf['workflow_id'] == workflow_id:
            pm.workflows[idx] = updated_workflow
            break

    # Preserve other fields like 'evaluations'
    project_data['workflows'] = pm.to_dict()['workflows']
    save_project(project_id, project_data)

    return jsonify({"status": "function_added", "function_id": new_call.call_id})


@app.route("/projects/<project_id>/workflow/<workflow_id>/edit_function", methods=["POST"])
def edit_function_in_step(project_id, workflow_id):
    data = request.json
    step_id = data.get("step_id")
    call_id = data.get("call_id")
    title = data.get("title")
    code = data.get("code", "")
    input_variables = data.get("input_variables", {})
    output_variable = data.get("output_variable", "")

    project_data = load_project(project_id)
    if not project_data:
        return jsonify({"error": "Project not found"}), 404
    pm = ProjectManager.from_dict(project_data)
    workflow = next((wf for wf in pm.workflows if wf["workflow_id"] == workflow_id), None)
    if not workflow:
        return jsonify({"error": "Workflow not found"}), 404

    manager = WorkflowManager.from_dict(workflow)
    step = next((s for s in manager.steps if s.step_id == step_id), None)
    if not step:
        return jsonify({"error": "Step not found"}), 404

    func = next((f for f in step.functions if f.call_id == call_id), None)
    if not func:
        return jsonify({"error": "Function call not found"}), 404

    func.title = title
    func.code = code
    func.input_variables = input_variables
    func.output_variable = output_variable

    updated_workflow = manager.to_dict()
    for idx, wf in enumerate(pm.workflows):
        if wf['workflow_id'] == workflow_id:
            pm.workflows[idx] = updated_workflow
            break

    # Preserve other fields like 'evaluations'
    project_data['workflows'] = pm.to_dict()['workflows']
    save_project(project_id, project_data)

    return jsonify({"status": "function_edited"})


@app.route("/projects/<project_id>/workflow/<workflow_id>/remove_function", methods=["POST"])
def remove_function_from_step(project_id, workflow_id):
    data = request.json
    step_id = data.get("step_id")
    call_id = data.get("call_id")

    project_data = load_project(project_id)
    if not project_data:
        return jsonify({"error": "Project not found"}), 404
    pm = ProjectManager.from_dict(project_data)
    workflow = next((wf for wf in pm.workflows if wf["workflow_id"] == workflow_id), None)
    if not workflow:
        return jsonify({"error": "Workflow not found"}), 404

    manager = WorkflowManager.from_dict(workflow)
    step = next((s for s in manager.steps if s.step_id == step_id), None)
    if not step:
        return jsonify({"error": "Step not found"}), 404

    step.functions = [f for f in step.functions if f.call_id != call_id]

    updated_workflow = manager.to_dict()
    for idx, wf in enumerate(pm.workflows):
        if wf['workflow_id'] == workflow_id:
            pm.workflows[idx] = updated_workflow
            break

    # Preserve other fields like 'evaluations'
    project_data['workflows'] = pm.to_dict()['workflows']
    save_project(project_id, project_data)

    return jsonify({"status": "function_removed"})



# =====================================
# Generate Code ROUTE
# =====================================



@app.route("/generate_code/<project_id>/<workflow_id>")
def generate_code(project_id, workflow_id):
    """
    Generates a Python script representing the workflow.
    """
    try:
        project_data = load_project(project_id)
        if not project_data:
            return jsonify({"error": "Project not found"}), 404
        pm = ProjectManager.from_dict(project_data)
        workflow = next((wf for wf in pm.workflows if wf['workflow_id'] == workflow_id), None)
        if not workflow:
            return jsonify({"error": "Workflow not found"}), 404

        generated_code = workflow_to_python_code(workflow, project_data)
        return jsonify({"code": generated_code})

    except Exception as e:
        app.logger.error(f"Error generating code for workflow {workflow_id}: {str(e)}")
        return jsonify({"error": "Failed to generate code."}), 500

def workflow_to_python_code(workflow, project_data):
    """
    Converts a workflow dictionary to an executable Python script.
    Uses sequential identifiers (step_1, call_1, etc.) instead of UUIDs.
    """
    code = """# === Imports ===
import os
import json
import requests
from groq import Groq
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# === Helper functions ===
def generate_llm_response(model_name, combined_prompt, params):

    if "llama" in model_name.lower():
        return call_llama_api(combined_prompt, params)
    elif "groq" in model_name.lower():
        return call_groq_api(combined_prompt, params)
    else:
        return call_openai_api(combined_prompt, params)

def replace_double_braces(template, variables):

    pattern = re.compile(r'{{\s*(.*?)\s*}}')

    def replacer(match):
        expr = match.group(1)
        if re.match(r'^[A-Za-z0-9_]+$', expr):
            # Simple variable
            if expr in variables:
                return str(variables[expr])
            else:
                raise KeyError(f"Variable '{expr}' not found.")
        else:
            # Attempt bracket/dict-based lookups
            try:
                import ast
                base_var_name = expr.split("[", 1)[0].strip()
                if base_var_name not in variables:
                    raise KeyError(f"Base variable '{base_var_name}' not found.")

                custom_var = variables[base_var_name]
                bracket_expr = expr[len(base_var_name):].strip()

                while bracket_expr.startswith("["):
                    end_index = bracket_expr.find("]")
                    if end_index == -1:
                        raise ValueError("Mismatched brackets in expression: " + expr)
                    key_str = bracket_expr[1:end_index].strip()
                    bracket_expr = bracket_expr[end_index+1:].strip()
                    key_str = key_str.strip("'\"")
                    if isinstance(custom_var, dict):
                        if key_str in custom_var:
                            custom_var = custom_var[key_str]
                        else:
                            raise KeyError(f"{key_str} not found in variable '{base_var_name}'")
                    else:
                        raise TypeError(f"Variable '{base_var_name}' is not a dictionary; cannot index '{key_str}'")
                return str(custom_var)

            except Exception as e:
                raise KeyError(f"Error accessing expression '{expr}': {str(e)}")

    return pattern.sub(replacer, template)

def parse_potential_json(raw_text):

    # Remove code fences like ```json ... ``` or plain ```
    content_str = re.sub(r"```(\w+)?", "", raw_text).strip()
    content_str = re.sub(r"```", "", content_str).strip()

    # Attempt to parse the cleaned string
    try:
        return json.loads(content_str)
    except json.JSONDecodeError:
        # Attempt to find a JSON substring
        start_index = content_str.find("{")
        end_index = content_str.rfind("}")
        if start_index != -1 and end_index != -1 and end_index > start_index:
            json_substring = content_str[start_index:end_index+1]
            try:
                return json.loads(json_substring)
            except json.JSONDecodeError:
                pass
        # If parsing fails, return an error string
        return f"[JSON PARSE ERROR] {raw_text}"

# === Workflow-level variables ===
"""

    # Initialize workflow-level variables
    for var_name, var_value in workflow['variables'].items():
        code += f'{var_name} = {json.dumps(var_value)}\n'

    code += "\n"

    # Keep track of call and function counts for sequential IDs
    call_count = 0
    function_count = 0

    # === Step functions ===
    for step_index, step in enumerate(workflow['steps']):
        code += f'def step_{step_index + 1}('
        
        input_vars = set()
        for call in step['calls']:
            for message in call['conversation']:
                content = message['content']
                matches = re.findall(r'\{\{(.*?)\}\}', content)
                for match in matches:
                    var_name = match.strip()
                    if var_name in workflow['variables'] or any(c.get('variable_name') == var_name for s in workflow['steps'][:step_index+1] for c in s['calls']) or any(f.get('output_variable') == var_name for s in workflow['steps'][:step_index+1] for f in s['functions']):
                         input_vars.add(var_name)
        for func in step.get('functions', []):
            for input_var_name in func['input_variables'].values():
                if input_var_name in workflow['variables'] or any(c.get('variable_name') == input_var_name for s in workflow['steps'][:step_index+1] for c in s['calls']) or any(f.get('output_variable') == input_var_name for s in workflow['steps'][:step_index+1] for f in s['functions']):
                    input_vars.add(input_var_name)

        # Function parameters based on collected input variables
        code += ', '.join(input_vars)
        code += '):\n'
        code += f'    """\n    Step: {step["title"]}\n'
        code += f'    Description: {step["description"]}\n    """\n'

        for call in step['calls']:
            call_count += 1
            code += f'    # LLM Call: {call["title"]}\n'
            code += f'    llm_params_call_{call_count} = {{\n'
            code += f'        "model_name": "{call["model_name"]}",\n'
            code += f'        "temperature": {call["temperature"]},\n'
            code += f'        "max_tokens": {call["max_tokens"]},\n'
            code += f'        "top_p": {call["top_p"]}\n'
            code += '    }\n'

            code += f'    system_prompt_call_{call_count} = """{call["system_prompt"]}"""\n'
            code += f'    conversation_call_{call_count} = [\n'
            for message in call['conversation']:
                code += '        {\n'
                code += f'            "role": "{message["role"]}",\n'
                code += f'            "content": """{message["content"]}"""\n'
                code += '        },\n'
            code += '    ]\n'

            # Variable substitution
            code += f'    # Substitute variables in system prompt\n'
            code += f'    system_prompt_call_{call_count} = replace_double_braces(system_prompt_call_{call_count}, locals())\n'
            code += f'    # Substitute variables in conversation\n'
            code += f'    for msg in conversation_call_{call_count}:\n'
            code += f'        msg["content"] = replace_double_braces(msg["content"], locals())\n'

            code += f'    llm_response_call_{call_count} = generate_llm_response(\n'
            code += f'        llm_params_call_{call_count}["model_name"],\n'
            code += '        {\n'
            code += f'            "system_prompt": system_prompt_call_{call_count},\n'
            code += f'            "conversation": conversation_call_{call_count}\n'
            code += '        },\n'
            code += f'        llm_params_call_{call_count}\n'
            code += '    )\n'

            if call['output_type'] == 'json':
                code += f'    {call["variable_name"]} = parse_potential_json(llm_response_call_{call_count}["content"])\n'
            else:
                code += f'    {call["variable_name"]} = llm_response_call_{call_count}["content"]\n'

            code += '\n'

        for func in step.get('functions', []):
            function_count += 1
            code += f'    # Function Call: {func["title"]}\n'
            code += f'    input_data_func_{function_count} = {{\n'
            for input_key, var_name in func['input_variables'].items():
                code += f'        "{input_key}": {var_name},\n'
            code += '    }\n'
            code += f'    # Function code:\n'
            code += f'    # {func["code"]}\n'
            code += f'    # Wrap the user-defined function code in a try-except block\n'
            code += f'    try:\n'
            code += f'        def user_defined_function(input_data):\n'
            code += f'            {func["code"]}\n'
            code += f'        output_data_func_{function_count} = user_defined_function(input_data_func_{function_count})\n'
            if func["output_variable"]:
                code += f'        {func["output_variable"]} = output_data_func_{function_count}\n'
            code += f'    except Exception as e:\n'
            code += f'        print(f"Error in function call \'{func["title"]}\': {{e}}")\n'
            code += f'        output_data_func_{function_count} = None\n'

        # Gather output variables for this step (and from previous steps)
        output_vars = [call['variable_name'] for call in step['calls'] if call['variable_name']]
        output_vars.extend([func['output_variable'] for func in step.get('functions', []) if func['output_variable']])
        
        # Return a dictionary of output variables
        if output_vars:
            code += f'    return {", ".join(output_vars)}\n\n'
        else:
            code += f'    return\n\n'

    # Main workflow function
    code += 'def run_workflow():\n'
    code += '    """\n'
    code += '    This is the main workflow function.\n'
    code += f'    Workflow Name: {workflow["name"]}\n'
    code += f'    Description: {workflow["workflow_description"]}\n'
    code += '    """\n'

    # Call step functions in order and pass outputs as inputs to the next step
    for step_index, step in enumerate(workflow['steps']):
        # Collect the output variables from the current step
        current_step_outputs = []
        for call in step['calls']:
            if call['variable_name']:
                current_step_outputs.append(call['variable_name'])
        for func in step.get('functions', []):
            if func['output_variable']:
                current_step_outputs.append(func['output_variable'])

        # Determine the input variables needed for the current step based on previous steps' outputs
        needed_inputs = set()
        for subsequent_step in workflow['steps'][step_index + 1:]:
            for call in subsequent_step['calls']:
                for message in call['conversation']:
                    content = message['content']
                    matches = re.findall(r'\{\{(.*?)\}\}', content)
                    for match in matches:
                        var_name = match.strip()
                        if var_name in current_step_outputs:
                            needed_inputs.add(var_name)
            for func in subsequent_step.get('functions', []):
                for input_var_name in func['input_variables'].values():
                    if input_var_name in current_step_outputs:
                        needed_inputs.add(input_var_name)

        # Call the step function with the necessary inputs
        if needed_inputs or current_step_outputs:
            code += f'    '
            if current_step_outputs:
                code += f'{", ".join(current_step_outputs)} = '
            code += f'step_{step_index + 1}('
            if needed_inputs:
                code += ', '.join(needed_inputs)
            code += ')\n'
        else:
            code += f'    step_{step_index + 1}()\n'

    code += '\n'
    code += '    print("Workflow completed.")\n\n'

    # Add conditional to run the workflow if the script is executed
    code += 'if __name__ == "__main__":\n'
    code += '    run_workflow()\n'

    return code
# =====================================
# RUN THE APP
# =====================================

if __name__ == "__main__":
    ensure_storage_dir()
    app.run(debug=True)

# modules/project_manager.py

import uuid
import copy
from .storage import save_project, load_project

class ProjectManager:
    def __init__(self, project_id, name="Untitled Project", description="", workflows=None, common_variable_names=None):
        self.project_id = project_id
        self.name = name
        self.description = description
        self.workflows = workflows if workflows is not None else []
        self.common_variable_names = common_variable_names if common_variable_names is not None else []

    def add_workflow(self, workflow_dict):
        self.workflows.append(workflow_dict)

    def remove_workflow(self, workflow_id):
        self.workflows = [wf for wf in self.workflows if wf['workflow_id'] != workflow_id]

    def copy_workflow(self, source_workflow_id):
        source_workflow = next((wf for wf in self.workflows if wf['workflow_id'] == source_workflow_id), None)
        if source_workflow:
            new_workflow = copy.deepcopy(source_workflow)
            new_workflow['workflow_id'] = str(uuid.uuid4())
            new_workflow['name'] += " (Copy)"
            new_workflow['workflow_description'] += " (Copy)"
            self.add_workflow(new_workflow)
            return new_workflow['workflow_id']
        return None

    def add_common_variable_name(self, var_name):
        if var_name in self.common_variable_names:
            raise ValueError("Variable name already exists.")
        self.common_variable_names.append(var_name)

    def remove_common_variable_name(self, var_name):
        if var_name in self.common_variable_names:
            self.common_variable_names.remove(var_name)
        else:
            raise ValueError("Variable name does not exist.")

    def to_dict(self):
        return {
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "common_variable_names": self.common_variable_names,
            "workflows": self.workflows
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            project_id=data.get("project_id"),
            name=data.get("name", "Untitled Project"),
            description=data.get("description", ""),
            workflows=data.get("workflows", []),
            common_variable_names=data.get("common_variable_names", [])
        )

# modules/workflow_manager.py

import uuid

class StepCall:
    def __init__(self, call_id=None, title="Untitled Call", system_prompt="", conversation=None,
                 variable_name="", variables=None, model_name="gpt-4", temperature=1.0,
                 max_tokens=1024, top_p=1.0, output_type="text", pydantic_definition=None, max_retries=0):
        self.call_id = call_id or str(uuid.uuid4())
        self.title = title
        self.system_prompt = system_prompt
        self.conversation = conversation or []
        self.variable_name = variable_name
        self.variables = variables or {}
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.top_p = top_p
        self.output_type = output_type
        self.pydantic_definition = pydantic_definition
        self.max_retries = max_retries

    @classmethod
    def from_dict(cls, data):
        return cls(
            call_id=data.get("call_id"),
            title=data.get("title", "Untitled Call"),
            system_prompt=data.get("system_prompt", ""),
            conversation=data.get("conversation", []),
            variable_name=data.get("variable_name", ""),
            variables=data.get("variables", {}),
            model_name=data.get("model_name", "gpt-4"),
            temperature=data.get("temperature", 1.0),
            max_tokens=data.get("max_tokens", 1024),
            top_p=data.get("top_p", 1.0),
            output_type=data.get("output_type", "text"),
            pydantic_definition=data.get("pydantic_definition", None),
            max_retries=data.get("max_retries", 0)
        )

    def to_dict(self):
        return {
            "call_id": self.call_id,
            "title": self.title,
            "system_prompt": self.system_prompt,
            "conversation": self.conversation,
            "variable_name": self.variable_name,
            "variables": self.variables,
            "model_name": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "top_p": self.top_p,
            "output_type": self.output_type,
            "pydantic_definition": self.pydantic_definition,
            "max_retries": self.max_retries
        }

class FunctionCall:
    def __init__(self, call_id=None, title="Untitled Function", code="", input_variables=None, output_variable=""):
        self.call_id = call_id or str(uuid.uuid4())
        self.title = title
        self.code = code  # The user-defined python code
        self.input_variables = input_variables or {}  # dict: { input_key: variable_name_in_context }
        self.output_variable = output_variable or ""

    @classmethod
    def from_dict(cls, data):
        return cls(
            call_id=data.get("call_id"),
            title=data.get("title", "Untitled Function"),
            code=data.get("code", ""),
            input_variables=data.get("input_variables", {}),
            output_variable=data.get("output_variable", "")
        )

    def to_dict(self):
        return {
            "call_id": self.call_id,
            "title": self.title,
            "code": self.code,
            "input_variables": self.input_variables,
            "output_variable": self.output_variable
        }

class WorkflowStep:
    def __init__(self, step_id=None, title="", description="", inputs="", calls=None, functions=None):
        self.step_id = step_id or str(uuid.uuid4())
        self.title = title
        self.description = description
        self.inputs = inputs
        self.calls = calls or []
        self.functions = functions or []

    @classmethod
    def from_dict(cls, data):
        calls = [StepCall.from_dict(c) for c in data.get("calls", [])]
        functions = [FunctionCall.from_dict(f) for f in data.get("functions", [])]
        return cls(
            step_id=data.get("step_id"),
            title=data.get("title", ""),
            description=data.get("description", ""),
            inputs=data.get("inputs", ""),
            calls=calls,
            functions=functions
        )

    def to_dict(self):
        return {
            "step_id": self.step_id,
            "title": self.title,
            "description": self.description,
            "inputs": self.inputs,
            "calls": [c.to_dict() for c in self.calls],
            "functions": [f.to_dict() for f in self.functions]
        }

class WorkflowManager:
    def __init__(self, workflow_id, name, steps=None, variables=None, workflow_description=""):
        self.workflow_id = workflow_id
        self.name = name
        self.steps = steps or []
        self.variables = variables or {}
        self.workflow_description = workflow_description

    @classmethod
    def from_dict(cls, data):
        steps = [WorkflowStep.from_dict(s) for s in data.get("steps", [])]
        return cls(
            workflow_id=data.get("workflow_id"),
            name=data.get("name", ""),
            steps=steps,
            variables=data.get("variables", {}),
            workflow_description=data.get("workflow_description", "")
        )

    def to_dict(self):
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "workflow_description": self.workflow_description,
            "steps": [s.to_dict() for s in self.steps],
            "variables": self.variables
        }
    
    def reorder_steps(self, new_order):
        step_dict = {step.step_id: step for step in self.steps}
        self.steps = [step_dict[step_id] for step_id in new_order if step_id in step_dict]

    def add_step(self, step):
        self.steps.append(step)

    def remove_step(self, step_id):
        original_count = len(self.steps)
        self.steps = [step for step in self.steps if step.step_id != step_id]
        return len(self.steps) < original_count
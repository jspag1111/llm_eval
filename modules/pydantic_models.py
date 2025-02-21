# modules/pydantic_models.py

from pydantic import BaseModel, Field
from typing import Optional

# Example Pydantic Models
class UserModel(BaseModel):
    name: str
    age: int
    email: Optional[str] = None

class AnotherModel(BaseModel):
    foo: str
    bar: int
    

class Evidence(BaseModel):
    reasoning: str = Field(..., description="Provide at least four sentences explaining the score for evidence assessment.")
    score: int = Field(..., ge=0, le=3, description="Numerical score for evidence assessment (0-3).")

class Suggestion(BaseModel):
    reasoning: str = Field(..., description="Provide at least four sentences explaining the score for suggestion assessment.")
    score: int = Field(..., ge=0, le=1, description="Numerical score for suggestion assessment (0-1).")

class Connection(BaseModel):
    reasoning: str = Field(..., description="Provide at least four sentences explaining the score for connection assessment.")
    score: int = Field(..., ge=0, le=1, description="Numerical score for connection assessment (0-1).")

class Evaluation(BaseModel):
    evidence: Evidence = Field(..., description="An evidence object containing reasoning and a numerical score.")
    suggestion: Suggestion = Field(..., description="A suggestion object containing reasoning and a numerical score.")
    connection: Connection = Field(..., description="A connection object describing the link between evidence and suggestion, with a numerical score.")



# A lookup so we can dynamically fetch the model by name
PYDANTIC_MODELS = {
    "UserModel": UserModel,
    "AnotherModel": AnotherModel,
    "Evaluation": Evaluation
}


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



print(generate_json_schema(Evaluation.model_json_schema()))
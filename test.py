from pydantic import BaseModel, Field

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

# Example usage
example_evaluation = Evaluation(
    evidence=Evidence(reasoning="The evaluator provided a detailed account of the resident's performance, noting specific examples that support the assessment.", score=3),
    suggestion=Suggestion(reasoning="The evaluator suggested that the resident focus on improving communication skills during patient handoffs.", score=1),
    connection=Connection(reasoning="The suggestion to improve communication skills is directly linked to the identified need for clearer patient handoffs, as described in the evaluation.", score=1)
)

# Print the expected output
print("Expected JSON Output:")
print(example_evaluation.model_dump_json(indent=4))


schema = Evaluation.model_json_schema()
print(schema)

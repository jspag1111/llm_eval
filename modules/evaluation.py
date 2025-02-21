def evaluate_outputs(all_outputs):
    """
    Evaluate the LLM outputs using custom metrics.
    For demonstration, we measure length. 
    Returns p_value and CI as placeholders if you have real stats later.
    """
    evaluations = []
    for step_result in all_outputs:
        response_content = step_result["response"]
        length_score = len(response_content)
        evaluations.append({
            "call_id": step_result["call_id"],
            "model_name": step_result["model_name"],
            "score_length": length_score,
            # Placeholder stats
            "p_value": None,
            "confidence_interval": None
        })

    average_length = sum(e["score_length"] for e in evaluations) / len(evaluations) if evaluations else 0
    return {
        "evaluation_details": evaluations,
        "summary": {
            "average_response_length": average_length
        }
    }
"""Evaluation Service — quality assessment for generated diagrams/plots.
Ported from PaperBanana's utils/eval_toolkits.py.

Implements a two-tier decision system:
  Tier 1: Faithfulness + Readability → if decisive, use as overall
  Tier 2: Conciseness + Aesthetics → tiebreaker when Tier 1 is tied
"""

import asyncio
import logging
import re
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

VALID_WINNERS = ["Human", "Model", "Both are good", "Both are bad"]
EVAL_DIMENSIONS = ["faithfulness", "conciseness", "readability", "aesthetics"]


def _extract_winner_with_fallback(text: str, dim: str, valid: list[str]) -> str:
    """Try to extract winner from raw text using regex fallback."""
    for w in valid:
        if w.lower() in text.lower():
            return w
    return "Unknown"


def _determine_tier_outcome(outcome_a: str, outcome_b: str) -> str:
    """Determine tier outcome from two dimension outcomes (PaperBanana logic).

    Rules:
    - If both agree on a winner -> that winner
    - If one says Model/Human and other is tied -> the decisive one wins
    - If both tied -> Tie (escalate to next tier)
    - Otherwise -> Tie
    """
    tied_values = {"Both are good", "Both are bad", "Tie", "Unknown", "N/A", "Error"}

    a_is_tied = outcome_a in tied_values
    b_is_tied = outcome_b in tied_values

    if a_is_tied and b_is_tied:
        return "Both are good"  # Default tie

    if not a_is_tied and not b_is_tied:
        if outcome_a == outcome_b:
            return outcome_a
        else:
            return "Both are good"  # Disagreement = tie

    # One is decisive, one is tied
    if not a_is_tied:
        return outcome_a
    return outcome_b


async def run_single_eval(
    chat_lb,
    task_type: str,
    dimension: str,
    content: str,
    visual_intent: str,
    gt_image_base64: str,
    model_image_base64: str,
) -> tuple[str, dict]:
    """Run a single evaluation dimension.

    Args:
        chat_lb: Chat load balancer for LLM calls
        task_type: "diagram" or "plot"
        dimension: One of EVAL_DIMENSIONS
        content: Methodology section / raw data
        visual_intent: Caption / visual intent
        gt_image_base64: Ground truth image (base64)
        model_image_base64: Model-generated image (base64)

    Returns:
        (dimension_name, result_dict) with keys: comparison_reasoning, winner
    """
    from app.prompts.eval_prompts import get_eval_prompt

    sys_prompt = get_eval_prompt(task_type, dimension)
    if not sys_prompt:
        return dimension, {"comparison_reasoning": "No prompt available", "winner": "Unknown"}

    # Build multimodal content
    if task_type == "diagram":
        if dimension == "faithfulness":
            text_part = f"Methodology Section: {content}\nDiagram Caption: {visual_intent}\n\nHuman-drawn Diagram (Human): "
        else:
            text_part = f"Diagram Caption: {visual_intent}\n\nHuman-drawn Diagram (Human): "
    else:
        if dimension == "faithfulness":
            text_part = f"Plot Brief Description: {visual_intent}\nRaw Data: {content}\n\nHuman-Drawn Plot (Human): "
        else:
            text_part = f"Plot Brief Description: {visual_intent}\n\nHuman-Drawn Plot (Human): "

    contents = [
        text_part,
        {"type": "image_base64", "data": gt_image_base64, "media_type": "image/jpeg"},
        f"\nModel-generated {'Diagram' if task_type == 'diagram' else 'Plot'} (Model): ",
        {"type": "image_base64", "data": model_image_base64, "media_type": "image/jpeg"},
    ]

    try:
        response = await chat_lb.chat_with_images(
            contents=contents,
            temperature=1.0,
            system_prompt=sys_prompt,
        )

        import json_repair
        clean_json = response.replace("```json", "").replace("```", "").strip()
        res_obj = json_repair.loads(clean_json)

        if not isinstance(res_obj, dict):
            res_obj = {
                "comparison_reasoning": clean_json,
                "winner": _extract_winner_with_fallback(clean_json, dimension, VALID_WINNERS),
            }
        elif "winner" not in res_obj:
            res_obj["winner"] = _extract_winner_with_fallback(clean_json, dimension, VALID_WINNERS)
        if "comparison_reasoning" not in res_obj:
            res_obj["comparison_reasoning"] = clean_json

        return dimension, res_obj

    except Exception as e:
        logger.error(f"Evaluation failed for {dimension}: {e}")
        return dimension, {"comparison_reasoning": str(e), "winner": "Error"}


async def evaluate_generation(
    chat_lb,
    task_type: str,
    content: str,
    visual_intent: str,
    gt_image_base64: str,
    model_image_base64: str,
) -> Dict[str, Any]:
    """Run full evaluation across all dimensions with two-tier decision.

    Returns dict with keys:
        - faithfulness_reasoning, faithfulness_outcome
        - conciseness_reasoning, conciseness_outcome
        - readability_reasoning, readability_outcome
        - aesthetics_reasoning, aesthetics_outcome
        - overall_outcome, overall_reasoning
    """
    # Run all 4 dimensions in parallel
    tasks = [
        run_single_eval(chat_lb, task_type, dim, content, visual_intent, gt_image_base64, model_image_base64)
        for dim in EVAL_DIMENSIONS
    ]

    results = await asyncio.gather(*tasks)

    eval_results: Dict[str, Any] = {}
    for dim, res_obj in results:
        eval_results[f"{dim}_reasoning"] = res_obj.get("comparison_reasoning", "")
        eval_results[f"{dim}_outcome"] = res_obj.get("winner", "Unknown")

    # Two-tier decision (PaperBanana logic)
    faithfulness = eval_results.get("faithfulness_outcome", "Unknown")
    readability = eval_results.get("readability_outcome", "Unknown")
    conciseness = eval_results.get("conciseness_outcome", "Unknown")
    aesthetics = eval_results.get("aesthetics_outcome", "Unknown")

    # Tier 1: Faithfulness + Readability
    tier1_outcome = _determine_tier_outcome(faithfulness, readability)

    if tier1_outcome in ("Model", "Human"):
        overall_outcome = tier1_outcome
        decision_path = f"Tier1({faithfulness}, {readability}) -> {tier1_outcome} [Decided at Tier 1]"
    else:
        # Tier 2: Conciseness + Aesthetics
        tier2_outcome = _determine_tier_outcome(conciseness, aesthetics)
        overall_outcome = tier2_outcome
        decision_path = f"Tier1({faithfulness}, {readability}) -> Tie; Tier2({conciseness}, {aesthetics}) -> {tier2_outcome} [Decided at Tier 2]"

    eval_results["overall_outcome"] = overall_outcome
    eval_results["overall_reasoning"] = f"Rule-based calculation: {decision_path}"

    return eval_results


async def evaluate_standalone(
    chat_lb,
    task_type: str,
    content: str,
    visual_intent: str,
    model_image_base64: str,
) -> Dict[str, Any]:
    """Standalone evaluation without ground truth (single-image quality assessment).

    Uses the model image alone and returns quality scores per dimension.
    This is a simplified version for when no ground truth is available.
    """
    from app.prompts.eval_prompts import get_eval_prompt

    # For standalone eval, we use a simplified prompt that evaluates a single image
    dimensions_results: Dict[str, Any] = {}

    for dim in ["readability", "aesthetics"]:
        sys_prompt = get_eval_prompt(task_type, dim)
        if not sys_prompt:
            dimensions_results[f"{dim}_score"] = None
            continue

        standalone_prompt = f"""Evaluate the quality of this {'diagram' if task_type == 'diagram' else 'plot'} on the dimension of {dim}.
Rate it on a scale of 1-10 where 10 is publication-ready quality.
Visual Intent: {visual_intent}

Provide your response in JSON: {{"score": <1-10>, "reasoning": "<brief explanation>"}}"""

        contents = [
            standalone_prompt,
            {"type": "image_base64", "data": model_image_base64, "media_type": "image/png"},
        ]

        try:
            response = await chat_lb.chat_with_images(
                contents=contents, temperature=0.7, system_prompt=sys_prompt,
            )
            import json_repair
            clean = response.replace("```json", "").replace("```", "").strip()
            parsed = json_repair.loads(clean)
            if isinstance(parsed, dict):
                dimensions_results[f"{dim}_score"] = parsed.get("score")
                dimensions_results[f"{dim}_reasoning"] = parsed.get("reasoning", "")
        except Exception as e:
            logger.error(f"Standalone eval {dim} failed: {e}")
            dimensions_results[f"{dim}_score"] = None

    # Compute average score
    scores = [v for k, v in dimensions_results.items() if k.endswith("_score") and v is not None]
    dimensions_results["overall_score"] = sum(scores) / len(scores) if scores else None

    return dimensions_results

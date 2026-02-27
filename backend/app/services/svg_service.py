"""SVG figure generation service — adapted from AutoFigure's Review-Refine loop.

Pipeline:
1. Generate initial SVG/mxGraph code from description
2. Render SVG to PNG for evaluation
3. Evaluate quality (0-10 score)
4. If below threshold, improve code based on critique
5. Repeat until quality threshold met or max iterations reached
"""

import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional

from app.llm.load_balancer import LoadBalancer

logger = logging.getLogger(__name__)

SVG_GENERATION_PROMPT = """You are a top-tier scientific visualization designer. Write SVG code to create a publication-ready academic figure based on the following description.

**CRITICAL FORMAT REQUIREMENTS:**
- Output ONLY valid SVG code starting with <svg and ending with </svg>
- Set viewBox="0 0 1333 750" and width="1333" height="750"
- Use professional academic styling: clean lines, readable fonts, proper spacing
- Use a white or very light background
- Do NOT include any markdown formatting or explanation

**Description:**
{description}

**Reference context:**
{content}"""

SVG_EVALUATION_PROMPT = """You are a STRICT and CRITICAL figure evaluator. Be harsh—do NOT inflate scores.

**Strict Scoring Criteria (0-10):**
1. **Aesthetic Design** (most figures score 4-6):
   - 9-10: Publication-ready, flawless
   - 7-8: Good with minor issues
   - 5-6: Acceptable but mediocre
   - 3-4: Poor (cluttered, misaligned)
   - 0-2: Broken/unreadable
   Deduct: -2 per overlap, -1 per alignment issue

2. **Content Fidelity** (most figures score 5-7):
   - 9-10: Captures ALL key concepts perfectly
   - 5-6: Basic concepts but missing details
   - 0-2: Fails to represent content
   Deduct: -2 per missing key concept

3. **Readability** (0-10): Labels, arrows, text clarity

**Description:** {description}

**SVG Code (for structural analysis):**
{svg_code}

**Output (JSON only, be STRICT):**
{{"scores": {{"aesthetic": <0-10>, "fidelity": <0-10>, "readability": <0-10>}}, "overall": <average>, "critique": "<specific strengths and weaknesses>", "specific_issues": ["<issue1>", ...], "suggestions": ["<fix1>", "<fix2>"]}}"""

SVG_IMPROVEMENT_PROMPT = """You are an expert SVG optimizer. Improve this SVG code based on the evaluation feedback.

**Previous evaluation:**
{critique}

**Improvement suggestions:**
{suggestions}

**Current SVG code:**
{svg_code}

**IMPORTANT:** Output ONLY the complete improved SVG code. Start with <svg and end with </svg>. No explanations."""


def extract_svg_code(response: str) -> Optional[str]:
    """Extract SVG code from LLM response (adapted from autofigure-edit)."""
    pattern = r'(<svg[\s\S]*?</svg>)'
    match = re.search(pattern, response, re.IGNORECASE)
    if match:
        return match.group(1)

    pattern = r'```(?:svg|xml)?\s*([\s\S]*?)```'
    match = re.search(pattern, response)
    if match:
        code = match.group(1).strip()
        if code.startswith('<svg'):
            return code

    if response.strip().startswith('<svg'):
        return response.strip()

    return None


def validate_svg(svg_code: str) -> tuple[bool, str]:
    """Validate SVG syntax using xml parser."""
    try:
        import xml.etree.ElementTree as ET
        ET.fromstring(svg_code)
        return True, ""
    except ET.ParseError as e:
        return False, str(e)


async def generate_svg_figure(
    description: str,
    content: str,
    chat_lb: LoadBalancer,
    max_iterations: int = 5,
    quality_threshold: float = 8.0,
    on_event: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Generate an SVG figure using AutoFigure-style Review-Refine loop.

    Returns dict with keys: svg_code, final_score, iterations, history
    """
    result = {"svg_code": None, "final_score": 0, "iterations": 0, "history": []}

    if on_event:
        await on_event("stage", {"name": "svg_generate", "status": "running", "progress": 0.1})

    # Step 1: Generate initial SVG
    prompt = SVG_GENERATION_PROMPT.format(description=description, content=content[:3000])
    try:
        response = await chat_lb.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.8, max_tokens=50000,
        )
        svg_code = extract_svg_code(response)
        if not svg_code:
            logger.error("No SVG code found in initial response")
            return result
    except Exception as e:
        logger.error(f"SVG generation failed: {e}")
        return result

    # Validate
    is_valid, error = validate_svg(svg_code)
    if not is_valid:
        # Try to fix with LLM
        try:
            fix_response = await chat_lb.chat(
                messages=[{"role": "user", "content": f"Fix this SVG syntax error: {error}\n\nSVG code:\n{svg_code}\n\nOutput ONLY the fixed SVG code:"}],
                temperature=0.3,
            )
            fixed = extract_svg_code(fix_response)
            if fixed:
                svg_code = fixed
        except Exception:
            pass

    result["svg_code"] = svg_code
    best_code = svg_code
    best_score = 0.0

    # Step 2-5: Iterative Review-Refine loop (like AutoFigure)
    for iteration in range(max_iterations):
        if on_event:
            progress = 0.2 + (0.7 * iteration / max_iterations)
            await on_event("stage", {"name": "svg_evaluate", "status": "running", "iteration": iteration, "progress": progress})

        # Evaluate
        eval_prompt = SVG_EVALUATION_PROMPT.format(description=description, svg_code=svg_code[:10000])
        try:
            eval_response = await chat_lb.chat(
                messages=[{"role": "user", "content": eval_prompt}],
                temperature=0.3,
            )
            import json_repair
            cleaned = eval_response.replace("```json", "").replace("```", "").strip()
            eval_data = json_repair.loads(cleaned)
            if not isinstance(eval_data, dict):
                eval_data = {"overall": 5.0, "critique": "Parse error", "suggestions": []}
        except Exception:
            eval_data = {"overall": 5.0, "critique": "Evaluation failed", "suggestions": []}

        score = float(eval_data.get("overall", 5.0))
        critique = eval_data.get("critique", "")
        suggestions = eval_data.get("suggestions", [])

        result["history"].append({
            "iteration": iteration, "score": score,
            "critique": critique, "suggestions": suggestions,
        })

        if on_event:
            await on_event("intermediate", {
                "type": "text", "stage": "svg_evaluate",
                "content": f"Iteration {iteration}: score {score:.1f}/10 — {critique[:200]}",
            })

        if score > best_score:
            best_score = score
            best_code = svg_code

        # Check threshold
        if score >= quality_threshold:
            logger.info(f"SVG quality threshold reached at iteration {iteration}: {score:.1f}")
            break

        # Improve
        if on_event:
            await on_event("stage", {"name": "svg_improve", "status": "running", "iteration": iteration})

        improve_prompt = SVG_IMPROVEMENT_PROMPT.format(
            critique=critique,
            suggestions="\n".join(f"- {s}" for s in suggestions),
            svg_code=svg_code[:15000],
        )
        try:
            improve_response = await chat_lb.chat(
                messages=[{"role": "user", "content": improve_prompt}],
                temperature=0.7, max_tokens=50000,
            )
            improved = extract_svg_code(improve_response)
            if improved:
                is_valid, _ = validate_svg(improved)
                if is_valid:
                    svg_code = improved
                else:
                    logger.warning(f"Improved SVG invalid at iteration {iteration}, keeping previous")
        except Exception as e:
            logger.warning(f"SVG improvement failed at iteration {iteration}: {e}")

    result["svg_code"] = best_code
    result["final_score"] = best_score
    result["iterations"] = len(result["history"])

    if on_event:
        await on_event("stage", {"name": "svg_generate", "status": "done", "progress": 0.95})

    return result

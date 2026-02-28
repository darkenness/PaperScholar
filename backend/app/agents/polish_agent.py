"""Polish Agent — refines/upscales generated images based on style guidelines.
Adapted from PaperBanana's polish_agent.py."""

import base64
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from app.agents.base_agent import BaseAgent

DIAGRAM_SUGGESTION_SYSTEM = """
You are a senior art director for NeurIPS 2025. Your task is to critique a diagram against a provided style guide.
Provide up to 10 concise, actionable improvement suggestions. Focus on aesthetics (color, layout, fonts, icons).
Directly list the suggestions. Do not use filler phrases like "Based on the style guide...".
If the diagram is substantially compliant, output "No changes needed".
"""

PLOT_SUGGESTION_SYSTEM = """
You are a senior data visualization expert for NeurIPS 2025. Your task is to critique a plot against a provided style guide.
Provide up to 10 concise, actionable improvement suggestions. Focus on aesthetics (color, layout, fonts).
Directly list the suggestions. Do not use filler phrases like "Based on the style guide...".
If the plot is substantially compliant, output "No changes needed".
"""

DIAGRAM_POLISH_SYSTEM = """
## ROLE
You are a professional diagram polishing expert for top-tier AI conferences (e.g., NeurIPS 2025).

## TASK
You are given an existing diagram image and a list of specific improvement suggestions. Your task is to generate a polished version of this diagram by applying these suggestions while preserving the semantic logic and structure of the original diagram.

## OUTPUT
Generate a polished diagram image that maintains the original content while applying the improvement suggestions.
"""

PLOT_POLISH_SYSTEM = """
## ROLE
You are a professional plot polishing expert for top-tier AI conferences (e.g., NeurIPS 2025).

## TASK
You are given an existing statistical plot image and a list of specific improvement suggestions. Your task is to generate a polished version of this plot by applying these suggestions while preserving all the data and quantitative information.

**Important Instructions:**
1. **Preserve Data:** Do NOT alter any data points, values, or quantitative information in the plot.
2. **Apply Suggestions:** Enhance the visual aesthetics according to the provided suggestions (colors, fonts, layout, etc.).
3. **Maintain Accuracy:** Ensure all numerical values and relationships remain accurate.
4. **Professional Quality:** Ensure the output meets publication standards for top-tier conferences.

## OUTPUT
Generate a polished plot image that maintains the original data while applying the improvement suggestions.
"""

_STYLE_GUIDE_DIR = Path(__file__).parent / "style_guides"


def _load_style_guide(task_type: str) -> str:
    """Load style guide from file based on task type (diagram or plot)."""
    filename = f"neurips2025_{task_type}_style_guide.md"
    filepath = _STYLE_GUIDE_DIR / filename
    try:
        return filepath.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


class PolishAgent(BaseAgent):
    """Refines images using style-guided suggestions + image regeneration."""

    async def process(self, data: Dict[str, Any], on_event: Optional[Callable] = None) -> Dict[str, Any]:
        task_type = data.get("task_type", "diagram")
        image_b64 = data.get("image_base64")

        if not image_b64:
            await self.emit(on_event, "stage", {"name": "polish", "status": "skipped", "detail": "no image"})
            return data

        await self.emit(on_event, "stage", {"name": "polish", "status": "running", "progress": 0.85})

        style_guide = _load_style_guide(task_type)
        suggestion_system = DIAGRAM_SUGGESTION_SYSTEM if task_type == "diagram" else PLOT_SUGGESTION_SYSTEM

        # Step 1: Generate suggestions
        await self.emit(on_event, "intermediate", {"type": "text", "stage": "polish", "content": "Analyzing image against style guide..."})

        try:
            suggestions = await self.chat_lb.chat_with_images(
                contents=[
                    f"Style Guide:\n{style_guide}\n\nAnalyze the image and list up to 10 specific improvement suggestions:",
                    {"type": "image_base64", "data": image_b64, "media_type": "image/png"},
                ],
                temperature=0.7,
                system_prompt=suggestion_system,
            )
        except Exception:
            suggestions = await self.chat_lb.chat(
                messages=[
                    {"role": "system", "content": suggestion_system},
                    {"role": "user", "content": f"Style Guide:\n{style_guide}\n\nBased on the style guide, suggest 10 improvements for a {task_type}."},
                ],
                temperature=0.7,
            )

        data["polish_suggestions"] = suggestions
        await self.emit(on_event, "intermediate", {"type": "text", "stage": "polish", "content": f"Suggestions: {suggestions[:300]}..."})

        if "No changes needed" in suggestions:
            await self.emit(on_event, "stage", {"name": "polish", "status": "done", "progress": 0.95, "detail": "no changes needed"})
            return data

        # Step 2: Generate polished image (pass original image to model)
        await self.emit(on_event, "intermediate", {"type": "text", "stage": "polish", "content": "Generating polished image..."})

        polish_system = DIAGRAM_POLISH_SYSTEM if task_type == "diagram" else PLOT_POLISH_SYSTEM
        polish_prompt = f"Please polish this image based on the following suggestions:\n\n{suggestions}\n\nPolished Image:"
        polished_bytes = None

        aspect_ratio = data.get("aspect_ratio", "16:9")
        image_size = data.get("image_size", "1k")

        # Try image-to-image first (passes original image to model)
        try:
            polished_bytes = await self.image_lb.generate_image_with_images(
                prompt=polish_prompt,
                images=[{"b64": image_b64, "media_type": "image/png"}],
                aspect_ratio=aspect_ratio,
                image_size=image_size,
            )
        except (AttributeError, NotImplementedError):
            pass
        except Exception as e:
            print(f"[Polish] Image-to-image generation failed: {e}")

        # Fallback: text-only image generation (loses original image context)
        if not polished_bytes:
            try:
                polished_bytes = await self.image_lb.generate_image(
                    prompt=polish_prompt,
                    aspect_ratio=aspect_ratio,
                    image_size=image_size,
                )
            except Exception as e:
                print(f"[Polish] Text-only image generation failed: {e}")

        if polished_bytes:
            data["polished_image_base64"] = base64.b64encode(polished_bytes).decode()
            await self.emit(on_event, "intermediate", {"type": "image_ready", "stage": "polish"})

        await self.emit(on_event, "stage", {"name": "polish", "status": "done", "progress": 0.95})
        return data

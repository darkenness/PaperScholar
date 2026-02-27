"""Polish Agent — refines/upscales generated images based on style guidelines.
Adapted from PaperBanana's polish_agent.py."""

import base64
import os
from typing import Any, Callable, Dict, Optional

from app.agents.base_agent import BaseAgent

DIAGRAM_SUGGESTION_SYSTEM = """You are a senior art director for NeurIPS 2025. Critique a diagram against the style guide.
Provide up to 10 concise, actionable improvement suggestions focusing on aesthetics (color, layout, fonts, icons).
If the diagram is substantially compliant, output "No changes needed"."""

PLOT_SUGGESTION_SYSTEM = """You are a senior data visualization expert for NeurIPS 2025. Critique a plot against the style guide.
Provide up to 10 concise, actionable improvement suggestions focusing on aesthetics (color, layout, fonts).
If the plot is substantially compliant, output "No changes needed"."""

POLISH_SYSTEM = """You are a professional figure polishing expert for top-tier AI conferences. Given an existing image and improvement suggestions, generate a polished version that:
1. Preserves semantic logic and structure
2. Applies the aesthetic improvements
3. Maintains all data accuracy (for plots)
4. Meets publication quality standards"""

STYLE_GUIDE_DIAGRAM = """### NeurIPS 2025 Diagram Style Guide (Summary)
- **Color**: Soft Tech & Scientific Pastels. Light desaturated backgrounds (#F5F5DC, #E6F3FF, #E0F2F1). Medium saturation for active modules. Warm=trainable, Cool=frozen.
- **Shapes**: Rounded Rectangles (radius 5-10px) for processes. 3D cuboids for tensors. Cylinders for memory/databases.
- **Lines**: Orthogonal for architectures, curved for system logic. Solid=data flow, dashed=auxiliary flow.
- **Typography**: Sans-serif for labels (Arial/Roboto). Serif italic for math variables.
- **Icons**: Fire/lightning=trainable, snowflake/padlock=frozen, gear=processing."""

STYLE_GUIDE_PLOT = """### NeurIPS 2025 Plot Style Guide (Summary)
- **Color**: Use colorblind-friendly palettes. Avoid fully saturated colors. Use muted tones with one accent.
- **Layout**: Tight layout, no wasted space. Legend inside plot when possible.
- **Typography**: Sans-serif labels (10-12pt). Axis titles bold. Tick labels regular.
- **Grid**: Light gray grid lines. No heavy borders.
- **Markers**: Distinct shapes for different series. Consistent line widths (1.5-2pt)."""


class PolishAgent(BaseAgent):
    """Refines images using style-guided suggestions + image regeneration."""

    async def process(self, data: Dict[str, Any], on_event: Optional[Callable] = None) -> Dict[str, Any]:
        task_type = data.get("task_type", "diagram")
        image_b64 = data.get("image_base64")

        if not image_b64:
            await self.emit(on_event, "stage", {"name": "polish", "status": "skipped", "detail": "no image"})
            return data

        await self.emit(on_event, "stage", {"name": "polish", "status": "running", "progress": 0.85})

        style_guide = STYLE_GUIDE_DIAGRAM if task_type == "diagram" else STYLE_GUIDE_PLOT
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

        polish_prompt = f"Polish this image based on these suggestions:\n\n{suggestions}\n\nGenerate an improved version:"
        polished_bytes = None

        # Try image-to-image first (passes original image to model)
        try:
            polished_bytes = await self.image_lb.generate_image_with_images(
                prompt=polish_prompt,
                images=[{"b64": image_b64, "media_type": "image/png"}],
                aspect_ratio=data.get("aspect_ratio", "1:1"),
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
                    aspect_ratio=data.get("aspect_ratio", "1:1"),
                )
            except Exception as e:
                print(f"[Polish] Text-only image generation failed: {e}")

        if polished_bytes:
            data["polished_image_base64"] = base64.b64encode(polished_bytes).decode()
            await self.emit(on_event, "intermediate", {"type": "image_ready", "stage": "polish"})

        await self.emit(on_event, "stage", {"name": "polish", "status": "done", "progress": 0.95})
        return data

"""Polish Agent — refines/upscales generated images based on style guidelines.
Adapted from PaperBanana's polish_agent.py."""

import base64
import io
from PIL import Image
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from app.agents.base_agent import BaseAgent
from app.agents.quality import choose_revision
from app.services.cost_service import BudgetExceededError
from app.llm.image_validation import validate_image_bytes

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
        if task_type=="plot":
            return await self._skip(data,on_event,"统计图保留代码渲染，不通过图像模型改写数据")

        if not image_b64:
            await self.emit(on_event, "stage", {"name": "polish", "status": "skipped", "detail": "no image"})
            return data

        try:
            source_bytes = base64.b64decode(image_b64, validate=True)
            validate_image_bytes(source_bytes)
            with Image.open(io.BytesIO(source_bytes)) as source_image:
                source_mime = Image.MIME.get(source_image.format, "image/png")
        except Exception:
            return await self._skip(data, on_event, "原图不是有效图片，未发起精修")

        await self.emit(on_event, "stage", {"name": "polish", "status": "running", "progress": 0.85})

        style_guide = _load_style_guide(task_type)
        suggestion_system = DIAGRAM_SUGGESTION_SYSTEM if task_type == "diagram" else PLOT_SUGGESTION_SYSTEM

        # Step 1: Generate suggestions
        await self.emit(on_event, "intermediate", {"type": "text", "stage": "polish", "content": "Analyzing image against style guide..."})

        try:
            suggestions = await self.chat_lb.chat_with_images(
                contents=[
                    f"Style Guide:\n{style_guide}\n\nAnalyze the image and list up to 10 specific improvement suggestions:",
                    {"type": "image_base64", "data": image_b64, "media_type": source_mime},
                ],
                temperature=0.7,
                system_prompt=suggestion_system,
            )
        except BudgetExceededError:
            raise
        except Exception:
            return await self._skip(data, on_event, "视觉检查失败，已保留原图；未改用无图检查")
        if not isinstance(suggestions, str) or not suggestions.strip():
            return await self._skip(data, on_event, "视觉检查未返回有效建议，已保留原图")

        data["polish_suggestions"] = suggestions
        await self.emit(on_event, "intermediate", {"type": "text", "stage": "polish", "content": f"Suggestions: {suggestions[:300]}..."})

        if suggestions.strip().rstrip(".!").lower() == "no changes needed":
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
                images=[{"b64": image_b64, "media_type": source_mime}],
                aspect_ratio=aspect_ratio,
                image_size=image_size,
                system_instruction=polish_system,
            )
        except BudgetExceededError:
            raise
        except (AttributeError, NotImplementedError):
            pass
        except Exception as e:
            print(f"[Polish] Image-to-image generation failed: {e}")

        # Editing must keep its image condition. A failed edit is not a text-to-image task.
        if not polished_bytes:
            return await self._skip(data, on_event, "带图编辑失败，已保留原图；未自动重新构图")
        try:
            validate_image_bytes(polished_bytes)
        except Exception:
            return await self._skip(data, on_event, "精修返回无效图片，已保留原图")

        candidate=base64.b64encode(polished_bytes).decode()
        await self.emit(on_event,"intermediate",{"type":"image_ready","stage":"polish","round":data.get("_render_round",0)+1,"image_base64":candidate,"description":data.get("stylist_description") or data.get("planner_description")})
        accept,reason=True,"精修完成"
        if data.get("quality_guard",True):
            accept,reason=await choose_revision(self.chat_lb,image_b64,candidate,data)
        await self.emit(on_event,"selection",{"stage":"polish","accepted":accept,"reason":reason})
        if accept:
            data["polished_image_base64"]=candidate

        await self.emit(on_event, "stage", {"name": "polish", "status": "done", "progress": 0.95})
        return data

    async def _skip(self, data, on_event, reason):
        data.pop("polished_image_base64", None)
        data["metadata"] = {**(data.get("metadata") or {}), "polish": {"status": "skipped", "reason": reason}}
        await self.emit(on_event, "stage", {"name": "polish", "status": "skipped", "detail": reason, "progress": 0.95})
        return data

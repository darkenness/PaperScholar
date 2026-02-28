import asyncio
import base64
import io
import logging
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from app.agents.base_agent import BaseAgent
from app.llm.load_balancer import LoadBalancer

logger = logging.getLogger(__name__)

# ── System Prompts (adapted from PaperBanana) ──

DIAGRAM_PLANNER_SYSTEM = """I am working on a task: given the 'Methodology' section of a paper, and the caption of the desired figure, automatically generate a corresponding illustrative diagram. I will input the text of the 'Methodology' section, the figure caption, and your output should be a detailed description of an illustrative figure that effectively represents the methods described in the text.

To help you understand the task better, and grasp the principles for generating such figures, I will also provide you with several examples. You should learn from these examples to provide your figure description.

** IMPORTANT: **
Your description should be as detailed as possible. Semantically, clearly describe each element and their connections. Formally, include various details such as background style (typically pure white or very light pastel), colors, line thickness, icon styles, etc. Remember: vague or unclear specifications will only make the generated figure worse, not better."""

PLOT_PLANNER_SYSTEM = """I am working on a task: given the raw data (typically in tabular or json format) and a visual intent of the desired plot, automatically generate a corresponding statistical plot that are both accurate and aesthetically pleasing. I will input the raw data and the plot visual intent, and your output should be a detailed description of an illustrative plot that effectively represents the data. Note that your description should include all the raw data points to be plotted.

To help you understand the task better, and grasp the principles for generating such plots, I will also provide you with several examples. You should learn from these examples to provide your plot description.

** IMPORTANT: **
Your description should be as detailed as possible. For content, explain the precise mapping of variables to visual channels (x, y, hue) and explicitly enumerate every raw data point's coordinate to be drawn to ensure accuracy. For presentation, specify the exact aesthetic parameters, including specific HEX color codes, font sizes for all labels, line widths, marker dimensions, legend placement, and grid styles. You should learn from the examples' content presentation and aesthetic design (e.g., color schemes)."""

DIAGRAM_STYLIST_SYSTEM = """
## ROLE
You are a Lead Visual Designer for top-tier AI conferences (e.g., NeurIPS 2025).

## TASK
Our goal is to generate high-quality, publication-ready diagrams, given the methodology section and the caption of the desired diagram. The diagram should illustrate the logic of the methodology section, while adhering to the scope defined by the caption. Before you, a planner agent has already generated a preliminary description of the target diagram. However, this description may lack specific aesthetic details, such as element shapes, color palettes, and background styling. Your task is to refine and enrich this description based on the provided [NeurIPS 2025 Style Guidelines] to ensure the final generated image is a high-quality, publication-ready diagram that adheres to the NeurIPS 2025 aesthetic standards where appropriate.

## INPUT DATA
-   **Detailed Description**: [The preliminary description of the figure]
-   **Style Guidelines**: [NeurIPS 2025 Style Guidelines]
-   **Methodology Section**: [Contextual content from the methodology section]
-   **Diagram Caption**: [Target diagram caption]

Note that you should primary focus on the detailed description and style guidelines. The methodology section and diagram caption are provided for context only, there's no need to regenerate a description from scratch, solely based on them, while ignoring the detailed description we already have.

**Crucial Instructions:**
1.  **Preserve Semantic Content:** Do NOT alter the semantic content, logic, or structure of the diagram. Your job is purely aesthetic refinement, not content editing. However, if you find some phrases or descriptions too verbose, you may simplify them appropriately while referencing the original methodology section to ensure semantic accuracy.
2.  **Preserve High-Quality Aesthetics and Intervene Only When Necessary:** First, evaluate the aesthetic quality implied by the input description. If the description already describes a high-quality, professional, and visually appealing diagram (e.g., nice 3D icons, rich textures, good color harmony), **PRESERVE IT**. Only apply strict Style Guide adjustments if the current description lacks detail, looks outdated, or is visually cluttered. Your goal is specific refinement, not blind standardization.
3.  **Respect Diversity:** Different domains have different styles. If the input describes a specific style (e.g., illustrative for agents) that works well, keep it.
4.  **Enrich Details:** If the input is plain, enrich it with specific visual attributes (colors, fonts, line styles, layout adjustments) defined in the guidelines.
5.  **Handle Icons with Care:** Be cautious when modifying icons as they may carry specific semantic meanings. Some icons have conventional technical meanings (e.g., snowflake = frozen/non-trainable, flame = trainable) - when encountering such icons, reference the original methodology section to verify their intent before making changes. However, purely decorative or symbolic icons can be freely enhanced and beautified. For examples, agent papers often use cute 2D robot avatars to represent agents.

## OUTPUT
Output ONLY the final polished Detailed Description. Do not include any conversational text or explanations.
"""

PLOT_STYLIST_SYSTEM = """
## ROLE
You are a Lead Visual Designer for top-tier AI conferences (e.g., NeurIPS 2025).

## TASK
You are provided with a preliminary description of a statistical plot to be generated. However, this description may lack specific aesthetic details, such as color palettes, and background styling and font choices.

Your task is to refine and enrich this description based on the provided [NeurIPS 2025 Style Guidelines] to ensure the final generated image is a high-quality, publication-ready plot that strictly adheres to the NeurIPS 2025 aesthetic standards.

**Crucial Instructions:**
1.  **Enrich Details:** Focus on specifying visual attributes (colors, fonts, line styles, layout adjustments) defined in the guidelines.
2.  **Preserve Content:** Do NOT alter the semantic content, logic, or quantitative results of the plot. Your job is purely aesthetic refinement, not content editing.
3.  **Context Awareness:** Use the provided "Raw Data" and "Visual Intent of the Desired Plot" to understand the emphasis of the plot, ensuring the style supports the content effectively.

## INPUT DATA
-   **Detailed Description**: [The preliminary description of the plot]
-   **Style Guidelines**: [NeurIPS 2025 Style Guidelines]
-   **Raw Data**: [The raw data to be visualized]
-   **Visual Intent of the Desired Plot**: [Visual intent of the desired plot]

## OUTPUT
Output ONLY the final polished Detailed Description. Do not include any conversational text or explanations.
"""

DIAGRAM_CRITIC_SYSTEM = """
## ROLE
You are a Lead Visual Designer for top-tier AI conferences (e.g., NeurIPS 2025).

## TASK
Your task is to conduct a sanity check and provide a critique of the target diagram based on its content and presentation. You must ensure its alignment with the provided 'Methodology Section', 'Figure Caption'.

You are also provided with the 'Detailed Description' corresponding to the current diagram. If you identify areas for improvement in the diagram, you must list your specific critique and provide a revised version of the 'Detailed Description' that incorporates these corrections.

## CRITIQUE & REVISION RULES

1. Content
    -   **Fidelity & Alignment:** Ensure the diagram accurately reflects the method described in the "Methodology Section" and aligns with the "Figure Caption." Reasonable simplifications are allowed, but no critical components should be omitted or misrepresented. Also, the diagram should not contain any hallucinated content. Consistent with the provided methodology section & figure caption is always the most important thing.
    -   **Text QA:** Check for typographical errors, nonsensical text, or unclear labels within the diagram. Suggest specific corrections.
    -   **Validation of Examples:** Verify the accuracy of illustrative examples. If the diagram includes specific examples to aid understanding (e.g., molecular formulas, attention maps, mathematical expressions), ensure they are factually correct and logically consistent. If an example is incorrect, provide the correct version.
    -   **Caption Exclusion:** Ensure the figure caption text (e.g., "Figure 1: Overview...") is **not** included within the image visual itself. The caption should remain separate.

2. Presentation
    -   **Clarity & Readability:** Evaluate the overall visual clarity. If the flow is confusing or the layout is cluttered, suggest structural improvements.
    -   **Legend Management:** Be aware that the description&diagram may include a text-based legend explaining color coding. Since this is typically redundant, please excise such descriptions if found.

** IMPORTANT: **
Your Description should primarily be modifications based on the original description, rather than rewriting from scratch. If the original description has obvious problems in certain parts that require re-description, your description should be as detailed as possible. Semantically, clearly describe each element and their connections. Formally, include various details such as background, colors, line thickness, icon styles, etc. Remember: vague or unclear specifications will only make the generated figure worse, not better.

## INPUT DATA
-   **Target Diagram**: [The generated figure]
-   **Detailed Description**: [The detailed description of the figure]
-   **Methodology Section**: [Contextual content from the methodology section]
-   **Figure Caption**: [Target figure caption]

## OUTPUT
Provide your response strictly in the following JSON format.

```json
{
    "critic_suggestions": "Insert your detailed critique and specific suggestions for improvement here. If the diagram is perfect, write 'No changes needed.'",
    "revised_description": "Insert the fully revised detailed description here, incorporating all your suggestions. If no changes are needed, write 'No changes needed.'",
}
```
"""

PLOT_CRITIC_SYSTEM = """
## ROLE
You are a Lead Visual Designer for top-tier AI conferences (e.g., NeurIPS 2025).

## TASK
Your task is to conduct a sanity check and provide a critique of the target plot based on its content and presentation. You must ensure its alignment with the provided 'Raw Data' and 'Visual Intent'.

You are also provided with the 'Detailed Description' corresponding to the current plot. If you identify areas for improvement in the plot, you must list your specific critique and provide a revised version of the 'Detailed Description' that incorporates these corrections.

## CRITIQUE & REVISION RULES

1. Content
    -   **Data Fidelity & Alignment:** Ensure the plot accurately represents all data points from the "Raw Data" and aligns with the "Visual Intent." All quantitative values must be correct. No data should be hallucinated, omitted, or misrepresented.
    -   **Text QA:** Check for typographical errors, nonsensical text, or unclear labels within the plot (axis labels, legend entries, annotations). Suggest specific corrections.
    -   **Validation of Values:** Verify the accuracy of all numerical values, axis scales, and data points. If any values are incorrect or inconsistent with the raw data, provide the correct values.
    -   **Caption Exclusion:** Ensure the figure caption text (e.g., "Figure 1: Performance comparison...") is **not** included within the image visual itself. The caption should remain separate.

2. Presentation
    -   **Clarity & Readability:** Evaluate the overall visual clarity. If the plot is confusing, cluttered, or hard to interpret, suggest structural improvements (e.g., better axis labeling, clearer legend, appropriate plot type).
    -   **Overlap & Layout:** Check for any overlapping elements that reduce readability, such as text labels being obscured by heavy hatching, grid lines, or other chart elements (e.g., pie chart labels inside dark slices). If overlaps exist, suggest adjusting element positions (e.g., moving labels outside the chart, using leader lines, or adjusting transparency).
    -   **Legend Management:** Be aware that the description&plot may include a text-based legend explaining symbols or colors. Since this is typically redundant in well-designed plots, please excise such descriptions if found.

3. Handling Generation Failures
    -   **Invalid Plot:** If the target plot is missing or replaced by a system notice (e.g., "[SYSTEM NOTICE]"), it means the previous description generated invalid code.
    -   **Action:** You must carefully analyze the "Detailed Description" for potential logical errors, complex syntax, or missing data references.
    -   **Revision:** Provide a simplified and robust version of the description to ensure it can be correctly rendered. Do not just repeat the same description.

## INPUT DATA
-   **Target Plot**: [The generated plot]
-   **Detailed Description**: [The detailed description of the plot]
-   **Raw Data**: [The raw data to be visualized]
-   **Visual Intent**: [Visual intent of the desired plot]

## OUTPUT
Provide your response strictly in the following JSON format.

```json
{
    "critic_suggestions": "Insert your detailed critique and specific suggestions for improvement here. If the plot is perfect, write 'No changes needed.'",
    "revised_description": "Insert the fully revised detailed description here, incorporating all your suggestions. If no changes are needed, write 'No changes needed.'",
}
```
"""


DIAGRAM_VISUALIZER_SYSTEM = """You are an expert scientific diagram illustrator. Generate high-quality scientific diagrams based on user requests."""

PLOT_VISUALIZER_SYSTEM = """You are an expert statistical plot illustrator. Write code to generate high-quality statistical plots based on user requests."""

DIAGRAM_VANILLA_SYSTEM = """
## ROLE
You are a Lead Visual Designer for top-tier AI conferences (e.g., NeurIPS 2025).

## TASK
You will be provided with a "Method Section" and a "Diagram Caption". Your task is to generate a high-quality scientific diagram that effectively illustrates the method described in the text, as the caption requires, and adhering strictly to modern academic visualization standards.

**CRITICAL INSTRUCTION ON CAPTION:**
The "Diagram Caption" is provided solely to describe the visual content and logic you need to draw. **DO NOT render, write, or include the caption text itself (e.g., "Figure 1: ...") inside the generated image.**

## INPUT DATA
-   **Method Section**: [Content of method section]
-   **Diagram Caption**: [Diagram caption]
## OUTPUT
Generate a single, high-resolution image that visually explains the method and aligns well with the caption.
"""

PLOT_VANILLA_SYSTEM = """
## ROLE
You are an expert statistical plot illustrator for top-tier AI conferences (e.g., NeurIPS 2025).

## TASK
You will be provided with "Plot Raw Data" and a "Visual Intent of the Desired Plot". Your task is to write matplotlib code to generate a high-quality statistical plot that effectively visualizes the data according to the visual intent, adhering strictly to modern academic visualization standards.

## INPUT DATA
-   **Plot Raw Data**: [Raw data to be visualized]
-   **Visual Intent of the Desired Plot**: [Description of what the plot should convey]

## OUTPUT
Write Python matplotlib code to generate the plot. Only provide the code without any explanations.
"""


class PlannerAgent(BaseAgent):
    """Planner Agent with in-context learning from retrieved reference examples.
    Adapted from PaperBanana's planner_agent.py."""

    async def process(self, data: Dict[str, Any], on_event: Optional[Callable] = None) -> Dict[str, Any]:
        await self.emit(on_event, "stage", {"name": "planner", "status": "running", "progress": 0.2})

        task_type = data.get("task_type", "diagram")
        content = data.get("content", "")
        caption = data.get("visual_intent", "")
        examples = data.get("retrieved_examples", [])

        system_prompt = DIAGRAM_PLANNER_SYSTEM if task_type == "diagram" else PLOT_PLANNER_SYSTEM
        content_label = "Methodology Section" if task_type == "diagram" else "Plot Raw Data"
        intent_label = "Diagram Caption" if task_type == "diagram" else "Visual Intent of the Desired Plot"

        # Build multimodal content with in-context examples (like PaperBanana)
        contents: list[Any] = []

        top_k = data.get("retriever_top_k", 10)
        if examples:
            for idx, item in enumerate(examples[:top_k]):
                item_content = item.get("content", "")
                if isinstance(item_content, (dict, list)):
                    import json
                    item_content = json.dumps(item_content)

                example_text = f"Example {idx+1}:\n{content_label}: {str(item_content)}\n{intent_label}: {item.get('visual_intent', '')}\nReference {task_type.capitalize()}: "
                contents.append(example_text)

                # If example has a reference image, include it
                ref_image_b64 = item.get("image_base64")
                if ref_image_b64:
                    contents.append({"type": "image_base64", "data": ref_image_b64, "media_type": "image/jpeg"})

            await self.emit(on_event, "intermediate", {
                "type": "text", "stage": "planner",
                "content": f"Using {len(examples)} reference examples for in-context learning",
            })

        # Append the actual target
        target_text = f"Now, based on the following {content_label.lower()} and {intent_label.lower()}, provide a detailed description for the figure to be generated.\n"
        target_text += f"{content_label}: {content}\n{intent_label}: {caption}\n"
        target_text += "Detailed description of the target figure to be generated"
        if task_type == "diagram":
            target_text += " (do not include figure titles)"
        target_text += ":"
        contents.append(target_text)

        # Use multimodal call if we have images, otherwise plain chat
        if any(isinstance(c, dict) for c in contents):
            description = await self.chat_lb.chat_with_images(contents=contents, temperature=1.0, system_prompt=system_prompt)
        else:
            full_prompt = "\n".join(str(c) for c in contents)
            messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": full_prompt}]
            description = await self.chat_lb.chat(messages=messages, temperature=1.0)

        data["planner_description"] = description.strip()

        await self.emit(on_event, "intermediate", {"type": "text", "stage": "planner", "content": description[:500]})
        await self.emit(on_event, "stage", {"name": "planner", "status": "done", "progress": 0.3})
        return data


_STYLE_GUIDE_DIR = Path(__file__).parent / "style_guides"


def _load_style_guide(task_type: str) -> str:
    """Load style guide from file based on task type (diagram or plot)."""
    filename = f"neurips2025_{task_type}_style_guide.md"
    filepath = _STYLE_GUIDE_DIR / filename
    try:
        return filepath.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning(f"Style guide not found: {filepath}")
        return ""


class StylistAgent(BaseAgent):
    """Stylist Agent adapted from PaperBanana — applies style guide refinement.
    Injects full style guide content into the prompt (like PaperBanana reads from file)."""

    async def process(self, data: Dict[str, Any], on_event: Optional[Callable] = None) -> Dict[str, Any]:
        await self.emit(on_event, "stage", {"name": "stylist", "status": "running", "progress": 0.35})

        task_type = data.get("task_type", "diagram")
        desc = data.get("planner_description", "")
        content = data.get("content", "")
        caption = data.get("visual_intent", "")

        system_prompt = DIAGRAM_STYLIST_SYSTEM if task_type == "diagram" else PLOT_STYLIST_SYSTEM
        content_label = "Methodology Section" if task_type == "diagram" else "Raw Data"
        intent_label = "Diagram Caption" if task_type == "diagram" else "Visual Intent"

        # Load style guide from file based on task_type (like PaperBanana)
        style_guide = _load_style_guide(task_type)

        prompt = f"Detailed Description: {desc}\nStyle Guidelines: {style_guide}\n{content_label}: {content}\n{intent_label}: {caption}\nYour Output:"
        messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}]

        refined = await self.chat_lb.chat(messages=messages, temperature=0.8)
        data["stylist_description"] = refined.strip()

        await self.emit(on_event, "intermediate", {"type": "text", "stage": "stylist", "content": refined[:500]})
        await self.emit(on_event, "stage", {"name": "stylist", "status": "done", "progress": 0.4})
        return data


def _execute_plot_code(code: str) -> Optional[str]:
    """Execute matplotlib code in a subprocess and return base64 PNG.
    Adapted from PaperBanana's Visualizer plot code execution."""
    try:
        match = re.search(r"```python(.*?)```", code, re.DOTALL)
        clean_code = match.group(1).strip() if match else code.strip()
        # Wrap code to save figure to bytes
        wrapper = f"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import io, base64, sys

try:
{chr(10).join('    ' + line for line in clean_code.split(chr(10)))}
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='jpeg', dpi=300, bbox_inches='tight', pil_kwargs={{'quality': 95}})
    plt.close('all')
    buf.seek(0)
    print(base64.b64encode(buf.getvalue()).decode(), end='')
except Exception as e:
    print(f'ERROR: {{e}}', file=sys.stderr)
    sys.exit(1)
"""
        result = subprocess.run(
            [sys.executable, "-c", wrapper],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        else:
            logger.warning(f"Plot code execution failed: {result.stderr[:200]}")
            return None
    except Exception as e:
        logger.warning(f"Plot code execution error: {e}")
        return None


def _convert_png_to_jpg_b64(png_bytes: bytes, quality: int = 95) -> Optional[str]:
    """Convert PNG bytes to JPG base64 string (P2-3)."""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(png_bytes))
        if img.mode in ('RGBA', 'LA', 'P'):
            img = img.convert('RGB')
        buf = io.BytesIO()
        img.save(buf, format='JPEG', quality=quality)
        return base64.b64encode(buf.getvalue()).decode()
    except Exception as e:
        logger.warning(f"PNG to JPG conversion failed: {e}")
        return base64.b64encode(png_bytes).decode()


class VisualizerAgent(BaseAgent):
    """Visualizer Agent with dual mode: Image generation (diagram) or Code execution (plot).
    Adapted from PaperBanana's visualizer_agent.py."""

    async def process(self, data: Dict[str, Any], on_event: Optional[Callable] = None) -> Dict[str, Any]:
        # Use dynamic progress hints from critic loop if available, otherwise default
        vis_progress_start = data.pop("_vis_progress_start", 0.45)
        vis_progress_end = data.pop("_vis_progress_end", 0.6)

        await self.emit(on_event, "stage", {"name": "visualizer", "status": "running", "progress": vis_progress_start})

        task_type = data.get("task_type", "diagram")
        desc = data.get("stylist_description") or data.get("planner_description", "")

        # P2-3: Smart skip — if critic says no changes needed, reuse previous image
        critic_round = data.get("critic_round")
        if critic_round is not None and critic_round > 0:
            prev_suggestions = data.get(f"critic_suggestions_{critic_round}", "")
            if prev_suggestions.strip() == "No changes needed." and data.get("image_base64"):
                logger.info(f"Visualizer: skipping re-generation (no changes needed at round {critic_round})")
                await self.emit(on_event, "stage", {"name": "visualizer", "status": "done", "progress": vis_progress_end})
                return data

        if task_type == "plot":
            # Plot mode: generate matplotlib code then execute (like PaperBanana)
            prompt = f"Use python matplotlib to generate a statistical plot based on the following detailed description: {desc}\n Only provide the code without any explanations. Code:"
            messages = [{"role": "system", "content": PLOT_VISUALIZER_SYSTEM}, {"role": "user", "content": prompt}]
            code = await self.chat_lb.chat(messages=messages, temperature=0.8)
            data["plot_code"] = code

            await self.emit(on_event, "intermediate", {"type": "text", "stage": "visualizer", "content": f"Generated plot code ({len(code)} chars), executing..."})

            # Execute code in subprocess
            loop = asyncio.get_running_loop()
            b64_result = await loop.run_in_executor(None, _execute_plot_code, code)

            if b64_result:
                data["image_base64"] = b64_result
                await self.emit(on_event, "intermediate", {"type": "image_ready", "stage": "visualizer"})
            else:
                data["image_base64"] = None
                logger.warning("Plot code execution failed")
                await self.emit(on_event, "intermediate", {"type": "text", "stage": "visualizer", "content": "Plot code execution failed, will retry in critic loop"})
        else:
            # Diagram mode: use Image generation model directly (with system prompt like PaperBanana)
            aspect_ratio = data.get("aspect_ratio", "16:9")
            prompt = f"Render an image based on the following detailed description: {desc}\n Note that do not include figure titles in the image."
            # Inject aspect ratio into prompt for OpenAI-compat models (like PaperBanana does)
            prompt += f"\n\nIMPORTANT: The output image MUST have an aspect ratio of {aspect_ratio}."
            prompt += " Diagram: "
            image_bytes = None

            # Primary: native image generation (Gemini image models)
            try:
                image_bytes = await self.image_lb.generate_image(
                    prompt=prompt,
                    aspect_ratio=aspect_ratio,
                    image_size=data.get("image_size", "1k"),
                    system_instruction=DIAGRAM_VISUALIZER_SYSTEM,
                )
            except Exception as e:
                logger.warning(f"Visualizer generate_image failed: {e}")

            # Fallback: generate image via chat (for OpenAI-compat or chat-based image models)
            if not image_bytes:
                try:
                    image_bytes = await self.image_lb.generate_image_from_chat(
                        contents=[prompt],
                        aspect_ratio=aspect_ratio,
                        image_size=data.get("image_size", "1k"),
                    )
                except (AttributeError, NotImplementedError):
                    pass
                except Exception as e:
                    logger.warning(f"Visualizer generate_image_from_chat fallback failed: {e}")

            if image_bytes:
                # P2-3: Convert PNG to JPG for consistency
                loop = asyncio.get_running_loop()
                jpg_b64 = await loop.run_in_executor(None, _convert_png_to_jpg_b64, image_bytes)
                data["image_base64"] = jpg_b64
                await self.emit(on_event, "intermediate", {"type": "image_ready", "stage": "visualizer"})
            else:
                data["image_base64"] = None
                logger.warning("Visualizer failed to generate image via all methods")

        await self.emit(on_event, "stage", {"name": "visualizer", "status": "done", "progress": vis_progress_end})
        return data


class CriticAgent(BaseAgent):
    """Critic Agent with source-aware round tracking and proper fallback logic.
    Adapted from PaperBanana's critic_agent.py."""

    async def process(self, data: Dict[str, Any], on_event: Optional[Callable] = None, source: str = "stylist") -> Dict[str, Any]:
        task_type = data.get("task_type", "diagram")
        round_idx = data.get("critic_round", 0)
        # Use dynamic progress hints from critic loop if available
        critic_progress_start = data.pop("_critic_progress_start", 0.65 + round_idx * 0.1)
        critic_progress_end = data.pop("_critic_progress_end", 0.7 + round_idx * 0.1)
        await self.emit(on_event, "stage", {"name": "critic", "status": "running", "round": round_idx, "progress": critic_progress_start})

        system_prompt = DIAGRAM_CRITIC_SYSTEM if task_type == "diagram" else PLOT_CRITIC_SYSTEM
        content_labels = (["Methodology Section", "Figure Caption"] if task_type == "diagram" else ["Raw Data", "Visual Intent"])

        # Determine which description/image to use based on round and source (like PaperBanana)
        if round_idx == 0:
            if source == "stylist" and data.get("stylist_description"):
                detailed_description = data["stylist_description"]
            else:
                detailed_description = data.get("planner_description", "")
        else:
            # Use previous round's revised description
            prev_desc = data.get(f"critic_revised_desc_{round_idx - 1}")
            detailed_description = prev_desc if prev_desc else (data.get("stylist_description") or data.get("planner_description", ""))

        content_raw = data.get("content", "")
        if isinstance(content_raw, (dict, list)):
            import json
            content_raw = json.dumps(content_raw)

        caption = data.get("visual_intent", "")
        image_b64 = data.get("image_base64")

        # Build multimodal content (image + text context) like PaperBanana
        critique_target = f"Target {'Diagram' if task_type == 'diagram' else 'Plot'} for Critique:"
        contents: list[Any] = [critique_target]

        if image_b64 and len(image_b64) > 100:
            contents.append({"type": "image_base64", "data": image_b64, "media_type": "image/png"})
        else:
            contents.append("[SYSTEM NOTICE] The image could not be generated. Please check the description for errors and provide a revised version.")

        contents.append(f"Detailed Description: {detailed_description}\n{content_labels[0]}: {content_raw}\n{content_labels[1]}: {caption}\nYour Output:")

        try:
            response = await self.chat_lb.chat_with_images(contents=contents, temperature=0.7, system_prompt=system_prompt)
        except Exception:
            fallback_prompt = f"{critique_target}\n\nDetailed Description: {detailed_description}\n{content_labels[0]}: {content_raw}\n{content_labels[1]}: {caption}\nYour Output:"
            response = await self.chat_lb.chat(
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": fallback_prompt}],
                temperature=0.7,
            )

        data[f"critic_feedback_{round_idx}"] = response
        await self.emit(on_event, "intermediate", {"type": "text", "stage": "critic", "round": round_idx, "content": response[:500]})

        # Parse response (like PaperBanana: clean markdown, use json_repair)
        import json_repair
        cleaned = response.replace("```json", "").replace("```", "").strip()
        parse_failed = False
        try:
            parsed = json_repair.loads(cleaned)
            if not isinstance(parsed, dict):
                parsed = {}
                parse_failed = True
        except Exception:
            parsed = {}
            parse_failed = True

        suggestions = parsed.get("critic_suggestions", "No changes needed.")
        revised_description = parsed.get("revised_description", "No changes needed.")

        # S5 fix: if JSON parse completely failed, mark this round as invalid
        # so _run_critic_loop can skip the visualizer re-generation
        if parse_failed:
            data[f"critic_parse_failed_{round_idx}"] = True
            suggestions = "No changes needed."
            revised_description = "No changes needed."
            logger.warning(f"Critic round {round_idx}: JSON parse failed, treating as no-op")

        data[f"critic_suggestions_{round_idx}"] = suggestions
        data["critic_suggestions"] = suggestions

        # Key fix: if revised_description is "No changes needed.", keep the current description
        # (from PaperBanana's logic at line 146-147)
        if revised_description.strip() == "No changes needed.":
            data[f"critic_revised_desc_{round_idx}"] = detailed_description
        else:
            data[f"critic_revised_desc_{round_idx}"] = revised_description
            # Update the description for the next visualizer pass
            data["stylist_description"] = revised_description

        await self.emit(on_event, "stage", {"name": "critic", "status": "done", "round": round_idx, "progress": critic_progress_end})
        return data


class PipelineEngine:
    """Orchestrates the multi-agent pipeline with SSE event emission.

    Supports:
    - Retriever → Planner → Stylist → Visualizer → Critic → Polish (full)
    - Multiple pipeline modes (vanilla, planner, planner_stylist, planner_critic, full)
    - Parallel candidate generation via asyncio.gather
    """

    def __init__(self, chat_lb: LoadBalancer, image_lb: LoadBalancer, dataset_path: Optional[str] = None):
        from app.agents.retriever_agent import RetrieverAgent
        from app.agents.polish_agent import PolishAgent

        self.retriever = RetrieverAgent(chat_lb=chat_lb, dataset_path=dataset_path)
        self.planner = PlannerAgent(chat_lb=chat_lb)
        self.stylist = StylistAgent(chat_lb=chat_lb)
        self.visualizer = VisualizerAgent(chat_lb=chat_lb, image_lb=image_lb)
        self.critic = CriticAgent(chat_lb=chat_lb, image_lb=image_lb)
        self.polish = PolishAgent(chat_lb=chat_lb, image_lb=image_lb)

    async def run(
        self,
        data: Dict[str, Any],
        mode: str = "dev_full",
        max_critic_rounds: int = 3,
        num_candidates: int = 1,
        on_event: Optional[Callable] = None,
    ) -> Dict[str, Any]:
        import time as _time
        pipeline_start = _time.monotonic()
        await self._emit(on_event, "stage", {"name": "pipeline", "status": "started", "mode": mode, "progress": 0.0})

        # Run retriever first for modes that need references
        if mode in ("dev_full", "demo_full", "dev_planner", "dev_planner_stylist", "dev_planner_critic", "demo_planner_critic", "dev_retriever"):
            t0 = _time.monotonic()
            data = await self.retriever.process(data, on_event)
            logger.info(f"[Pipeline] Retriever completed in {_time.monotonic() - t0:.1f}s")

        if num_candidates > 1:
            # Parallel candidate generation
            data = await self._run_parallel_candidates(data, mode, max_critic_rounds, num_candidates, on_event)
        else:
            # Single candidate
            data = await self._run_single(data, mode, max_critic_rounds, on_event)

        total = _time.monotonic() - pipeline_start
        logger.info(f"[Pipeline] Total pipeline completed in {total:.1f}s (mode={mode})")
        await self._emit(on_event, "stage", {"name": "pipeline", "status": "completed", "progress": 1.0})
        return data

    async def _run_single(self, data: Dict[str, Any], mode: str, max_critic_rounds: int, on_event: Optional[Callable]) -> Dict[str, Any]:
        if mode == "vanilla":
            # P1-4: Vanilla mode — direct generation with PaperBanana prompts, no planner/stylist/critic
            task_type = data.get("task_type", "diagram")
            content_raw = data.get("content", "")
            if isinstance(content_raw, (dict, list)):
                import json as _json
                content_raw = _json.dumps(content_raw)
            visual_intent = data.get("visual_intent", "")

            if task_type == "diagram":
                system_prompt = DIAGRAM_VANILLA_SYSTEM
                aspect_ratio = data.get("aspect_ratio", "1:1")
                prompt_text = f"**Method Section**: {content_raw}\n**Diagram Caption**: {visual_intent}\nNote that do not include figure titles in the image.\n\nIMPORTANT: The output image MUST have an aspect ratio of {aspect_ratio}."
            else:
                system_prompt = PLOT_VANILLA_SYSTEM
                prompt_text = f"**Plot Raw Data**: {content_raw}\n**Visual Intent of the Desired Plot**: {visual_intent}\nUse python matplotlib to generate a statistical plot based on the above information. Only provide the code without any explanations. Code:"

            if task_type == "diagram":
                # Use image generation directly
                image_bytes = None
                try:
                    image_bytes = await self.visualizer.image_lb.generate_image(
                        prompt=prompt_text,
                        aspect_ratio=data.get("aspect_ratio", "1:1"),
                        image_size=data.get("image_size", "1k"),
                        system_instruction=system_prompt,
                    )
                except Exception as e:
                    logger.warning(f"Vanilla generate_image failed: {e}")

                # Fallback: generate image via chat
                if not image_bytes:
                    try:
                        image_bytes = await self.visualizer.image_lb.generate_image_from_chat(
                            contents=[prompt_text],
                            aspect_ratio=data.get("aspect_ratio", "1:1"),
                            image_size=data.get("image_size", "1k"),
                        )
                    except (AttributeError, NotImplementedError):
                        pass
                    except Exception as e:
                        logger.warning(f"Vanilla generate_image_from_chat fallback failed: {e}")

                if image_bytes:
                    data["image_base64"] = base64.b64encode(image_bytes).decode()
            else:
                # Generate code then execute
                messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt_text}]
                code = await self.visualizer.chat_lb.chat(messages=messages, temperature=0.8)
                data["plot_code"] = code
                loop = asyncio.get_running_loop()
                b64_result = await loop.run_in_executor(None, _execute_plot_code, code)
                if b64_result:
                    data["image_base64"] = b64_result

            await self._emit(on_event, "stage", {"name": "visualizer", "status": "done", "progress": 0.6})
        elif mode == "dev_polish":
            # P1-5: dev_polish mode — directly polish an existing image
            data = await self.polish.process(data, on_event)
        elif mode == "dev_retriever":
            # P1-5: dev_retriever mode — only run retriever, return references
            await self._emit(on_event, "stage", {"name": "retriever", "status": "done", "progress": 1.0})
        elif mode == "dev_planner":
            data = await self.planner.process(data, on_event)
            data = await self.visualizer.process(data, on_event)
        elif mode == "dev_planner_stylist":
            data = await self.planner.process(data, on_event)
            data = await self.stylist.process(data, on_event)
            data = await self.visualizer.process(data, on_event)
        elif mode in ("dev_planner_critic", "demo_planner_critic"):
            data = await self.planner.process(data, on_event)
            data = await self.visualizer.process(data, on_event)
            data = await self._run_critic_loop(data, max_critic_rounds, on_event, source="planner")
        elif mode in ("dev_full", "demo_full"):
            import time as _time
            t0 = _time.monotonic()
            data = await self.planner.process(data, on_event)
            logger.info(f"[Pipeline] Planner completed in {_time.monotonic() - t0:.1f}s")

            t0 = _time.monotonic()
            data = await self.stylist.process(data, on_event)
            logger.info(f"[Pipeline] Stylist completed in {_time.monotonic() - t0:.1f}s")

            t0 = _time.monotonic()
            data = await self.visualizer.process(data, on_event)
            logger.info(f"[Pipeline] Visualizer completed in {_time.monotonic() - t0:.1f}s")

            t0 = _time.monotonic()
            data = await self._run_critic_loop(data, max_critic_rounds, on_event, source="stylist")
            logger.info(f"[Pipeline] Critic loop completed in {_time.monotonic() - t0:.1f}s")

            if mode == "dev_full":
                t0 = _time.monotonic()
                data = await self.polish.process(data, on_event)
                logger.info(f"[Pipeline] Polish completed in {_time.monotonic() - t0:.1f}s")
        else:
            raise ValueError(f"Unknown pipeline mode: {mode}")
        return data

    async def _run_parallel_candidates(
        self,
        data: Dict[str, Any],
        mode: str,
        max_critic_rounds: int,
        num_candidates: int,
        on_event: Optional[Callable],
    ) -> Dict[str, Any]:
        """Run pipeline for multiple candidates in parallel (like PaperBanana's batch processing)."""
        await self._emit(on_event, "intermediate", {
            "type": "text", "stage": "pipeline",
            "content": f"Generating {num_candidates} candidates in parallel...",
        })

        # First run shared steps: retriever is already done, run planner once
        data = await self.planner.process(data, on_event)
        if mode in ("dev_planner_stylist", "dev_full", "demo_full"):
            data = await self.stylist.process(data, on_event)

        # Now fork: run visualizer + critic for each candidate in parallel
        async def generate_one(candidate_idx: int) -> Dict[str, Any]:
            cdata = {**data, "candidate_index": candidate_idx}
            cdata = await self.visualizer.process(cdata, on_event)
            if mode in ("dev_planner_critic", "demo_planner_critic"):
                cdata = await self._run_critic_loop(cdata, max_critic_rounds, on_event, source="planner")
            elif mode in ("dev_full", "demo_full"):
                cdata = await self._run_critic_loop(cdata, max_critic_rounds, on_event, source="stylist")
            if mode == "dev_full":
                cdata = await self.polish.process(cdata, on_event)
            return cdata

        sem = asyncio.Semaphore(min(num_candidates, 10))

        async def limited(idx: int) -> Dict[str, Any]:
            async with sem:
                return await generate_one(idx)

        results = await asyncio.gather(*[limited(i) for i in range(num_candidates)], return_exceptions=True)

        # Collect results
        candidates = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                logger.error(f"Candidate {i} failed: {r}")
                continue
            candidates.append(r)

        data["candidates"] = candidates
        data["num_candidates_completed"] = len(candidates)

        # Use the first successful candidate as the primary result
        if candidates:
            primary = candidates[0]
            data["image_base64"] = primary.get("image_base64") or primary.get("polished_image_base64")
            data["planner_description"] = primary.get("planner_description", data.get("planner_description"))
            data["stylist_description"] = primary.get("stylist_description", data.get("stylist_description"))

        await self._emit(on_event, "intermediate", {
            "type": "text", "stage": "pipeline",
            "content": f"Completed {len(candidates)}/{num_candidates} candidates",
        })

        return data

    async def _run_critic_loop(self, data: Dict[str, Any], max_rounds: int, on_event: Optional[Callable], source: str = "stylist") -> Dict[str, Any]:
        """Run critic iterations with rollback mechanism (like PaperBanana's _run_critic_iterations).
        Tracks current_best_image and rolls back on visualization failure."""
        # Track the best image so far for rollback
        current_best_image = data.get("image_base64")

        # Early exit: if no image was generated at all, skip critic loop entirely
        if not current_best_image or len(str(current_best_image)) < 100:
            logger.warning("Critic loop: no image available, skipping all critic rounds")
            await self._emit(on_event, "intermediate", {
                "type": "text", "stage": "critic",
                "content": "No image available for critique — skipping critic loop",
            })
            return data

        # Progress range for critic loop: 0.6 → 0.85
        # Each round covers [round_start, round_end) with critic in first half, visualizer in second
        LOOP_START, LOOP_END = 0.6, 0.85
        round_size = (LOOP_END - LOOP_START) / max(max_rounds, 1)

        for i in range(max_rounds):
            round_start = LOOP_START + i * round_size
            round_mid = round_start + round_size * 0.5
            round_end = LOOP_START + (i + 1) * round_size

            data["critic_round"] = i
            data["_critic_progress_start"] = round(round_start, 3)
            data["_critic_progress_end"] = round(round_mid, 3)
            data = await self.critic.process(data, on_event, source=source)

            suggestions = data.get("critic_suggestions", "").strip()

            # If critic says no changes needed, stop iteration
            if suggestions == "No changes needed.":
                logger.info(f"Critic round {i}: no changes needed, stopping")
                break

            # Early exit: if suggestions are very short, likely minor — skip re-generation
            if len(suggestions) < 50 and i > 0:
                logger.info(f"Critic round {i}: minor suggestions ({len(suggestions)} chars), stopping early")
                break

            # S5 fix: if JSON parse failed, skip visualizer (would waste a round)
            if data.get(f"critic_parse_failed_{i}"):
                logger.info(f"Critic round {i}: parse failed, skipping visualizer")
                continue

            # Re-generate image with revised description (pass dynamic progress hints)
            data["_vis_progress_start"] = round(round_mid, 3)
            data["_vis_progress_end"] = round(round_end, 3)
            data = await self.visualizer.process(data, on_event)

            # P0-4: Rollback mechanism — if visualizer failed, restore previous best
            new_image = data.get("image_base64")
            if new_image and len(str(new_image)) > 100:
                current_best_image = new_image
                logger.info(f"Critic round {i}: visualization SUCCESS, updated best image")
            else:
                # Rollback to previous best image
                if current_best_image:
                    data["image_base64"] = current_best_image
                    logger.warning(f"Critic round {i}: visualization FAILED, rolled back to previous best")
                    await self._emit(on_event, "intermediate", {
                        "type": "text", "stage": "critic",
                        "content": f"Round {i}: Image generation failed, rolling back to previous best image",
                    })
                else:
                    logger.warning(f"Critic round {i}: visualization FAILED, no previous best to rollback to")
                break  # Stop iteration on failure (like PaperBanana)

        return data

    async def _emit(self, on_event: Optional[Callable], event_type: str, event_data: dict):
        if on_event:
            await on_event(event_type, event_data)

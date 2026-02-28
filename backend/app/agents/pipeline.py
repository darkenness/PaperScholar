import asyncio
import base64
import io
import logging
import subprocess
import sys
import tempfile
from typing import Any, Callable, Dict, List, Optional

from app.agents.base_agent import BaseAgent
from app.llm.load_balancer import LoadBalancer

logger = logging.getLogger(__name__)

# ── System Prompts (adapted from PaperBanana) ──

DIAGRAM_PLANNER_SYSTEM = """I am working on a task: given the 'Methodology' section of a paper, and the caption of the desired figure, automatically generate a corresponding illustrative diagram. I will input the text of the 'Methodology' section, the figure caption, and your output should be a detailed description of an illustrative figure that effectively represents the methods described in the text.

To help you understand the task better, I will also provide you with several examples. You should learn from these examples to provide your figure description.

** IMPORTANT: **
Your description should be as detailed as possible. Semantically, clearly describe each element and their connections. Formally, include various details such as background style (typically pure white or very light pastel), colors, line thickness, icon styles, etc. Remember: vague or unclear specifications will only make the generated figure worse, not better."""

PLOT_PLANNER_SYSTEM = """I am working on a task: given the raw data (typically in tabular or json format) and a visual intent of the desired plot, automatically generate a corresponding statistical plot that are both accurate and aesthetically pleasing. Your output should be a detailed description of an illustrative plot that effectively represents the data. Note that your description should include all the raw data points to be plotted.

** IMPORTANT: **
Your description should be as detailed as possible. For content, explain the precise mapping of variables to visual channels (x, y, hue) and explicitly enumerate every raw data point's coordinate. For presentation, specify the exact aesthetic parameters, including specific HEX color codes, font sizes for all labels, line widths, marker dimensions, legend placement, and grid styles."""

DIAGRAM_STYLIST_SYSTEM = """You are a Lead Visual Designer for top-tier AI conferences (e.g., NeurIPS 2025).
Your task is to refine and enrich a preliminary diagram description based on style guidelines to ensure the final image is publication-ready.

**Crucial Instructions:**
1. **Preserve Semantic Content:** Do NOT alter the semantic content, logic, or structure.
2. **Preserve High-Quality Aesthetics:** If the description already describes a high-quality diagram, PRESERVE IT. Only apply adjustments if the current description lacks detail.
3. **Enrich Details:** If the input is plain, enrich with specific visual attributes (HEX colors, fonts, line styles, layout adjustments).
4. **Handle Icons with Care:** Some icons have conventional technical meanings (snowflake = frozen, flame = trainable).

Output ONLY the final polished Detailed Description. No conversational text."""

PLOT_STYLIST_SYSTEM = """You are a Lead Visual Designer specializing in publication-quality statistical plots.
Refine the plot description to ensure NeurIPS 2025 aesthetic standards. Preserve all data values. Enrich with specific HEX colors, font sizes, line styles, and layout details.
Output ONLY the refined description."""

DIAGRAM_CRITIC_SYSTEM = """You are a strict academic figure critic. Given the generated image, the detailed description, methodology section, and figure caption, evaluate the quality of the diagram.

Output a JSON object with exactly these fields:
{
    "critic_suggestions": "<specific issues and how to fix them, or 'No changes needed.' if the image is satisfactory>",
    "revised_description": "<improved description that addresses the issues, or 'No changes needed.' if the image is satisfactory>"
}

Be STRICT but fair. Only output "No changes needed." if the image is truly publication-ready."""

PLOT_CRITIC_SYSTEM = """You are a strict statistical plot evaluator. Given the generated plot, the detailed description, raw data, and visual intent, check data accuracy, visual mapping correctness, and aesthetics.

Output a JSON object:
{
    "critic_suggestions": "<specific issues or 'No changes needed.'>",
    "revised_description": "<improved description or 'No changes needed.'>"
}"""


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

        if examples:
            for idx, item in enumerate(examples[:10]):
                item_content = item.get("content", "")
                if isinstance(item_content, (dict, list)):
                    import json
                    item_content = json.dumps(item_content)

                example_text = f"Example {idx+1}:\n{content_label}: {str(item_content)[:1500]}\n{intent_label}: {item.get('visual_intent', '')}\nReference {task_type.capitalize()}: "
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


STYLE_GUIDE_CONTENT = """### NeurIPS 2025 Style Guide (Key Points)
**Colors:** Soft pastels for backgrounds (#F5F5DC cream, #E6F3FF ice blue, #E0F2F1 mint). Medium saturation for active modules. Warm=trainable, Cool=frozen.
**Shapes:** Rounded rectangles (5-10px radius) for processes. 3D cuboids for tensors. Cylinders for databases.
**Lines:** Orthogonal for architectures, curved for system logic. Solid=data flow, dashed=auxiliary (gradients, skip connections).
**Typography:** Sans-serif (Arial/Roboto) for labels. Serif italic for math variables.
**Icons:** Fire/lightning=trainable, snowflake/padlock=frozen, gear=processing.
**Layout:** "Macro-Micro" pattern—global container with zoomed-in breakout boxes. Light backgrounds to organize complexity.
**Pitfalls to avoid:** PowerPoint defaults, font mixing, inconsistent 2D/3D, saturated backgrounds, ambiguous arrows."""


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

        # Inject style guide content (like PaperBanana loads from neurips2025_*_style_guide.md)
        prompt = f"Detailed Description: {desc}\nStyle Guidelines: {STYLE_GUIDE_CONTENT}\n{content_label}: {content}\n{intent_label}: {caption}\nYour Output:"
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
        clean_code = code.replace("```python", "").replace("```", "").strip()
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
    plt.savefig(buf, format='png', dpi=300, bbox_inches='tight')
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


class VisualizerAgent(BaseAgent):
    """Visualizer Agent with dual mode: Image generation (diagram) or Code execution (plot).
    Adapted from PaperBanana's visualizer_agent.py."""

    async def process(self, data: Dict[str, Any], on_event: Optional[Callable] = None) -> Dict[str, Any]:
        await self.emit(on_event, "stage", {"name": "visualizer", "status": "running", "progress": 0.45})

        task_type = data.get("task_type", "diagram")
        desc = data.get("stylist_description") or data.get("planner_description", "")

        if task_type == "plot":
            # Plot mode: generate matplotlib code then execute (like PaperBanana)
            prompt = f"Use python matplotlib to generate a statistical plot based on the following detailed description: {desc}\n Only provide the code without any explanations. Code:"
            messages = [{"role": "user", "content": prompt}]
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
            # Diagram mode: use Image generation model directly
            prompt = f"Render an image based on the following detailed description: {desc}\n Note that do not include figure titles in the image. Diagram: "
            image_bytes = await self.image_lb.generate_image(
                prompt=prompt,
                aspect_ratio=data.get("aspect_ratio", "1:1"),
                image_size=data.get("image_size", "1k"),
            )

            if image_bytes:
                data["image_base64"] = base64.b64encode(image_bytes).decode()
                await self.emit(on_event, "intermediate", {"type": "image_ready", "stage": "visualizer"})
            else:
                data["image_base64"] = None
                logger.warning("Visualizer failed to generate image")

        await self.emit(on_event, "stage", {"name": "visualizer", "status": "done", "progress": 0.6})
        return data


class CriticAgent(BaseAgent):
    """Critic Agent with source-aware round tracking and proper fallback logic.
    Adapted from PaperBanana's critic_agent.py."""

    async def process(self, data: Dict[str, Any], on_event: Optional[Callable] = None, source: str = "stylist") -> Dict[str, Any]:
        task_type = data.get("task_type", "diagram")
        round_idx = data.get("critic_round", 0)
        await self.emit(on_event, "stage", {"name": "critic", "status": "running", "round": round_idx, "progress": 0.65 + round_idx * 0.1})

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
        try:
            parsed = json_repair.loads(cleaned)
            if not isinstance(parsed, dict):
                parsed = {}
        except Exception:
            parsed = {}

        suggestions = parsed.get("critic_suggestions", "No changes needed.")
        revised_description = parsed.get("revised_description", "No changes needed.")

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

        await self.emit(on_event, "stage", {"name": "critic", "status": "done", "round": round_idx, "progress": 0.7 + round_idx * 0.1})
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
        await self._emit(on_event, "stage", {"name": "pipeline", "status": "started", "mode": mode, "progress": 0.0})

        # Run retriever first for modes that need references
        if mode in ("dev_full", "demo_full", "dev_planner", "dev_planner_stylist", "dev_planner_critic", "demo_planner_critic"):
            data = await self.retriever.process(data, on_event)

        if num_candidates > 1:
            # Parallel candidate generation
            data = await self._run_parallel_candidates(data, mode, max_critic_rounds, num_candidates, on_event)
        else:
            # Single candidate
            data = await self._run_single(data, mode, max_critic_rounds, on_event)

        await self._emit(on_event, "stage", {"name": "pipeline", "status": "completed", "progress": 1.0})
        return data

    async def _run_single(self, data: Dict[str, Any], mode: str, max_critic_rounds: int, on_event: Optional[Callable]) -> Dict[str, Any]:
        if mode == "vanilla":
            data["planner_description"] = data.get("content", "")
            data = await self.visualizer.process(data, on_event)
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
            data = await self.planner.process(data, on_event)
            data = await self.stylist.process(data, on_event)
            data = await self.visualizer.process(data, on_event)
            data = await self._run_critic_loop(data, max_critic_rounds, on_event, source="stylist")
            if mode == "dev_full":
                data = await self.polish.process(data, on_event)
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
        for i in range(max_rounds):
            data["critic_round"] = i
            data = await self.critic.process(data, on_event, source=source)

            if data.get("critic_suggestions", "").strip() == "No changes needed.":
                logger.info(f"Critic round {i}: no changes needed, stopping")
                break

            data = await self.visualizer.process(data, on_event)

        return data

    async def _emit(self, on_event: Optional[Callable], event_type: str, event_data: dict):
        if on_event:
            await on_event(event_type, event_data)

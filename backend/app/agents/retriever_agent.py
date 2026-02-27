"""Retriever Agent — selects relevant reference examples from the dataset.
Adapted from PaperBanana's retriever_agent.py logic."""

import json
import random
from typing import Any, Callable, Dict, List, Optional

from app.agents.base_agent import BaseAgent

DIAGRAM_RETRIEVER_SYSTEM = """You are a professional academic diagram retriever. Given a target diagram's caption and methodology section, and a candidate pool of reference diagrams, select the Top 10 most relevant diagrams that can serve as in-context examples.

Relevance criteria:
1. Structural similarity (flow charts vs. architecture diagrams vs. comparison tables)
2. Domain proximity (same field or similar methodology type)
3. Visual complexity match

Output a valid JSON object: {"top10_diagrams": ["id1", "id2", ...]}"""

PLOT_RETRIEVER_SYSTEM = """You are a professional statistical plot retriever. Given a target plot's visual intent and raw data, and a candidate pool of reference plots, select the Top 10 most relevant plots.

Relevance criteria:
1. Chart type similarity (bar, line, scatter, heatmap, etc.)
2. Data structure match (categorical vs. continuous, single vs. multi-series)
3. Visual style similarity

Output a valid JSON object: {"top10_plots": ["id1", "id2", ...]}"""


class RetrieverAgent(BaseAgent):
    """Retrieves relevant reference examples from the dataset for in-context learning."""

    def __init__(self, dataset_path: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.dataset_path = dataset_path
        self._candidate_pool: Optional[List[Dict]] = None

    def _load_candidates(self, task_type: str) -> List[Dict]:
        """Load reference candidates from dataset file."""
        if self._candidate_pool is not None:
            return self._candidate_pool

        if not self.dataset_path:
            return []

        import os
        ref_path = os.path.join(self.dataset_path, task_type, "ref.json")
        if not os.path.exists(ref_path):
            return []

        try:
            with open(ref_path, "r", encoding="utf-8") as f:
                self._candidate_pool = json.load(f)
            return self._candidate_pool
        except Exception as e:
            print(f"[Retriever] Failed to load candidates: {e}")
            return []

    def _load_reference_images(self, examples: List[Dict], task_type: str) -> List[Dict]:
        """Load reference images into examples (like PaperBanana's planner_agent).
        This is critical for in-context learning quality."""
        import base64

        if not self.dataset_path:
            return examples

        for item in examples:
            if item.get("image_base64"):
                continue  # Already loaded
            image_rel_path = item.get("path_to_gt_image")
            if not image_rel_path:
                continue
            import os
            image_path = os.path.join(self.dataset_path, task_type, image_rel_path)
            if os.path.exists(image_path):
                try:
                    with open(image_path, "rb") as f:
                        item["image_base64"] = base64.b64encode(f.read()).decode("utf-8")
                except Exception as e:
                    print(f"[Retriever] Failed to load image {image_path}: {e}")

        return examples

    async def process(self, data: Dict[str, Any], on_event: Optional[Callable] = None) -> Dict[str, Any]:
        task_type = data.get("task_type", "diagram")
        retrieval_setting = data.get("retrieval_setting", "auto")

        await self.emit(on_event, "stage", {"name": "retriever", "status": "running", "progress": 0.05})

        candidates = self._load_candidates(task_type)

        if retrieval_setting == "none" or not candidates:
            data["top10_references"] = []
            data["retrieved_examples"] = []
            await self.emit(on_event, "stage", {"name": "retriever", "status": "done", "progress": 0.1, "detail": "skipped"})
            return data

        if retrieval_setting == "random":
            sample_size = min(10, len(candidates))
            selected = random.sample(candidates, sample_size)
            # Load reference images for in-context learning
            selected = self._load_reference_images(selected, task_type)
            data["top10_references"] = [item["id"] for item in selected]
            data["retrieved_examples"] = selected
            await self.emit(on_event, "intermediate", {"type": "text", "stage": "retriever", "content": f"Randomly selected {sample_size} references"})
            await self.emit(on_event, "stage", {"name": "retriever", "status": "done", "progress": 0.1})
            return data

        # Auto retrieval using LLM
        if not self.chat_lb:
            data["top10_references"] = []
            data["retrieved_examples"] = []
            await self.emit(on_event, "stage", {"name": "retriever", "status": "done", "progress": 0.1, "detail": "no LLM"})
            return data

        content = str(data.get("content", ""))
        visual_intent = data.get("visual_intent", "")

        if task_type == "plot":
            system_prompt = PLOT_RETRIEVER_SYSTEM
            target_labels = ["Visual Intent", "Raw Data"]
            candidate_labels = ["Plot ID", "Visual Intent", "Raw Data"]
            output_key = "top10_plots"
        else:
            system_prompt = DIAGRAM_RETRIEVER_SYSTEM
            target_labels = ["Caption", "Methodology section"]
            candidate_labels = ["Diagram ID", "Caption", "Methodology section"]
            output_key = "top10_diagrams"

        # Build prompt with candidate pool (limit to 200)
        pool = candidates[:200]
        user_prompt = f"**Target Input**\n- {target_labels[0]}: {visual_intent}\n- {target_labels[1]}: {content[:2000]}\n\n**Candidate Pool**\n"

        for idx, item in enumerate(pool):
            item_content = str(item.get("content", ""))[:200]
            user_prompt += f"Candidate {idx+1}:\n- {candidate_labels[0]}: {item['id']}\n- {candidate_labels[1]}: {item.get('visual_intent', '')}\n- {candidate_labels[2]}: {item_content}\n\n"

        user_prompt += f"Select the Top 10 most relevant {task_type}s. Output JSON only."

        try:
            response = await self.chat_lb.chat(
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.7,
            )

            import json_repair
            parsed = json_repair.loads(response)
            ref_ids = parsed.get(output_key, [])

            id_to_item = {item["id"]: item for item in candidates}
            retrieved = [id_to_item[rid] for rid in ref_ids if rid in id_to_item]
            # Load reference images for in-context learning
            retrieved = self._load_reference_images(retrieved, task_type)

            data["top10_references"] = ref_ids
            data["retrieved_examples"] = retrieved
            await self.emit(on_event, "intermediate", {"type": "text", "stage": "retriever", "content": f"Retrieved {len(retrieved)} references: {ref_ids[:5]}..."})

        except Exception as e:
            print(f"[Retriever] LLM retrieval failed: {e}, falling back to random")
            sample_size = min(10, len(candidates))
            selected = random.sample(candidates, sample_size) if candidates else []
            selected = self._load_reference_images(selected, task_type)
            data["top10_references"] = [item["id"] for item in selected]
            data["retrieved_examples"] = selected

        await self.emit(on_event, "stage", {"name": "retriever", "status": "done", "progress": 0.1})
        return data

"""Retriever Agent — locally ranks relevant reference examples for generation."""

import json
import random
import math
import re
from collections import Counter
from typing import Any, Callable, Dict, List, Optional

from app.agents.base_agent import BaseAgent

DIAGRAM_RETRIEVER_SYSTEM = """
# Background & Goal
We are building an **AI system to automatically generate method diagrams for academic papers**. Given a paper's methodology section and a figure caption, the system needs to create a high-quality illustrative diagram that visualizes the described method.

To help the AI learn how to generate appropriate diagrams, we use a **few-shot learning approach**: we provide it with reference examples of similar diagrams. The AI will learn from these examples to understand what kind of diagram to create for the target.

# Your Task
**You are the Retrieval Agent.** Your job is to select the most relevant reference diagrams from a candidate pool that will serve as few-shot examples for the diagram generation model.

You will receive:
- **Target Input:** The methodology section and caption of the diagram we need to generate
- **Candidate Pool:** ~200 existing diagrams (each with methodology and caption)

You must select the **Top 10 candidates** that would be most helpful as examples for teaching the AI how to draw the target diagram.

# Selection Logic (Topic + Intent)

Your goal is to find examples that match the Target in both **Domain** and **Diagram Type**.

**1. Match Research Topic (Use Methodology & Caption):**
* What is the domain? (e.g., Agent & Reasoning, Vision & Perception, Generative & Learning, Science & Applications).
* Select candidates that belong to the **same research domain**.
* *Why?* Similar domains share similar terminology (e.g., "Actor-Critic" in RL).

**2. Match Visual Intent (Use Caption & Keywords):**
* What type of diagram is implied? (e.g., "Framework", "Pipeline", "Detailed Module", "Performance Chart").
* Select candidates with **similar visual structures**.
* *Why?* A "Framework" diagram example is useless for drawing a "Performance Bar Chart", even if they are in the same domain.

**Ranking Priority:**
1.  **Best Match:** Same Topic AND Same Visual Intent (e.g., Target is "Agent Framework" -> Candidate is "Agent Framework", Target is "Dataset Construction Pipeline" -> Candidate is "Dataset Construction Pipeline").
2.  **Second Best:** Same Visual Intent (e.g., Target is "Agent Framework" -> Candidate is "Vision Framework"). *Structure is more important than Topic for drawing.*
3.  **Avoid:** Different Visual Intent (e.g., Target is "Pipeline" -> Candidate is "Bar Chart").

# Input Data

## Target Input
-   **Caption:** [Caption of the target diagram]
-   **Methodology section:** [Methodology section of the target paper]

## Candidate Pool
List of candidate diagrams, each structured as follows:

Candidate Diagram i:
-   **Diagram ID:** [ID of the candidate diagram (ref_1, ref_2, ...)]
-   **Caption:** [Caption of the candidate diagram]
-   **Methodology section:** [Methodology section of the candidate's paper]

# Output Format
Provide your output strictly in the following JSON format, containing only the **exact IDs** of the Top 10 selected diagrams (use the exact IDs from the Candidate Pool, such as "ref_1", "ref_25", "ref_100", etc.):
```json
{
  "top10_diagrams": [
    "ref_1",
    "ref_25",
    "ref_100",
    "ref_42",
    "ref_7",
    "ref_156",
    "ref_89",
    "ref_3",
    "ref_201",
    "ref_67"
  ]
}
```
"""

PLOT_RETRIEVER_SYSTEM = """
# Background & Goal
We are building an **AI system to automatically generate statistical plots**. Given a plot's raw data and the visual intent, the system needs to create a high-quality visualization that effectively presents the data.

To help the AI learn how to generate appropriate plots, we use a **few-shot learning approach**: we provide it with reference examples of similar plots. The AI will learn from these examples to understand what kind of plot to create for the target data.

# Your Task
**You are the Retrieval Agent.** Your job is to select the most relevant reference plots from a candidate pool that will serve as few-shot examples for the plot generation model.

You will receive:
- **Target Input:** The raw data and visual intent of the plot we need to generate
- **Candidate Pool:** Reference plots (each with raw data and visual intent)

You must select the **Top 10 candidates** that would be most helpful as examples for teaching the AI how to create the target plot.

# Selection Logic (Data Type + Visual Intent)

Your goal is to find examples that match the Target in both **Data Characteristics** and **Plot Type**.

**1. Match Data Characteristics (Use Raw Data & Visual Intent):**
* What type of data is it? (e.g., categorical vs numerical, single series vs multi-series, temporal vs comparative).
* What are the data dimensions? (e.g., 1D, 2D, 3D).
* Select candidates with **similar data structures and characteristics**.
* *Why?* Different data types require different visualization approaches.

**2. Match Visual Intent (Use Visual Intent):**
* What type of plot is implied? (e.g., "bar chart", "scatter plot", "line chart", "pie chart", "heatmap", "radar chart").
* Select candidates with **similar plot types**.
* *Why?* A "bar chart" example is more useful for generating another bar chart than a "scatter plot" example, even if the data domains are similar.

**Ranking Priority:**
1.  **Best Match:** Same Data Type AND Same Plot Type (e.g., Target is "multi-series line chart" -> Candidate is "multi-series line chart").
2.  **Second Best:** Same Plot Type with compatible data (e.g., Target is "bar chart with 5 categories" -> Candidate is "bar chart with 6 categories").
3.  **Avoid:** Different Plot Type (e.g., Target is "bar chart" -> Candidate is "pie chart"), unless there are no more candidates with the same plot type.

# Input Data

## Target Input
-   **Visual Intent:** [Visual intent of the target plot]
-   **Raw Data:** [Raw data to be visualized]

## Candidate Pool
List of candidate plots, each structured as follows:

Candidate Plot i:
-   **Plot ID:** [ID of the candidate plot (ref_0, ref_1, ...)]
-   **Visual Intent:** [Visual intent of the candidate plot]
-   **Raw Data:** [Raw data of the candidate plot]

# Output Format
Provide your output strictly in the following JSON format, containing only the **exact Plot IDs** of the Top 10 selected plots (use the exact IDs from the Candidate Pool, such as "ref_0", "ref_25", "ref_100", etc.):
```json
{
  "top10_plots": [
    "ref_0",
    "ref_25",
    "ref_100",
    "ref_42",
    "ref_7",
    "ref_156",
    "ref_89",
    "ref_3",
    "ref_201",
    "ref_67"
  ]
}
```
"""


class RetrieverAgent(BaseAgent):
    """Retrieves relevant reference examples from the dataset for in-context learning."""

    def __init__(self, dataset_path: Optional[str] = None, **kwargs):
        super().__init__(**kwargs)
        self.dataset_path = dataset_path
        self._candidate_pools: Dict[str, List[Dict]] = {}

    def _load_candidates(self, task_type: str) -> List[Dict]:
        """Load reference candidates from dataset file."""
        if task_type in self._candidate_pools:
            return self._candidate_pools[task_type]

        if not self.dataset_path:
            return []

        import os
        ref_path = os.path.join(self.dataset_path, task_type, "ref.json")
        if not os.path.exists(ref_path):
            return []

        try:
            with open(ref_path, "r", encoding="utf-8") as f:
                self._candidate_pools[task_type] = json.load(f)
            return self._candidate_pools[task_type]
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

    @staticmethod
    def _vector_tokens(value: Any) -> List[str]:
        """Create lightweight local tokens without a remote embedding call.

        Latin words are kept as terms and contiguous CJK text is represented by
        character bigrams so Chinese queries can be matched as well.
        """
        text = str(value or "").lower()
        tokens: List[str] = []
        for chunk in re.findall(r"[\u4e00-\u9fff]+|[a-z0-9_]+", text):
            if re.fullmatch(r"[\u4e00-\u9fff]+", chunk):
                tokens.extend(chunk[i:i + 2] for i in range(max(1, len(chunk) - 1)))
            else:
                tokens.append(chunk)
        return tokens

    def _local_vector_search(self, query: str, candidates: List[Dict], top_k: int) -> List[Dict]:
        """Rank candidates locally with a TF-IDF cosine score.

        This intentionally stays dependency-free: the reference library is
        small enough for an in-process sparse vector pass and no LLM call is
        needed merely to select examples.
        """
        if not candidates or top_k <= 0:
            return []
        query_tokens = self._vector_tokens(query)
        if not query_tokens:
            return candidates[:top_k]
        documents = [self._vector_tokens(
            f"{item.get('visual_intent', '')} {item.get('caption', '')} {item.get('content', '')}"
        ) for item in candidates]
        df = Counter(token for doc in documents for token in set(doc))
        total_docs = len(documents) + 1

        def weights(tokens: List[str]) -> Dict[str, float]:
            counts = Counter(tokens)
            return {token: (1.0 + math.log(count)) * math.log(total_docs / (1 + df[token])) for token, count in counts.items()}

        query_vector = weights(query_tokens)
        query_norm = math.sqrt(sum(value * value for value in query_vector.values())) or 1.0
        ranked = []
        for index, doc in enumerate(documents):
            vector = weights(doc)
            dot = sum(query_vector.get(token, 0.0) * value for token, value in vector.items())
            norm = math.sqrt(sum(value * value for value in vector.values())) or 1.0
            ranked.append((dot / (query_norm * norm), index))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [candidates[index] for score, index in ranked[:min(top_k, len(candidates))]]

    async def process(self, data: Dict[str, Any], on_event: Optional[Callable] = None) -> Dict[str, Any]:
        task_type = data.get("task_type", "diagram")
        retrieval_setting = data.get("retrieval_setting", "auto")

        await self.emit(on_event, "stage", {"name": "retriever", "status": "running", "progress": 0.05})

        if data.get("retrieved_examples"):
            data["top10_references"]=[item["id"] for item in data["retrieved_examples"]]
            await self.emit(on_event,"stage",{"name":"retriever","status":"done","progress":.1,"detail":f"使用 {len(data['retrieved_examples'])} 张用户参考图"})
            return data
        candidates = self._load_candidates(task_type)
        if not candidates and retrieval_setting!="none":
            await self.emit(on_event,"intermediate",{"type":"text","stage":"retriever","content":"参考库未安装或为空，本次使用原有风格指南；可上传自己的参考图。"})

        if retrieval_setting == "none" or not candidates:
            data["top10_references"] = []
            data["retrieved_examples"] = []
            await self.emit(on_event, "stage", {"name": "retriever", "status": "done", "progress": 0.1, "detail": "skipped"})
            return data

        if retrieval_setting == "random":
            top_k = data.get("retriever_top_k", 10)
            sample_size = min(top_k, len(candidates))
            selected = random.sample(candidates, sample_size)
            # Load reference images for in-context learning
            selected = self._load_reference_images(selected, task_type)
            data["top10_references"] = [item["id"] for item in selected]
            data["retrieved_examples"] = selected
            await self.emit(on_event, "intermediate", {"type": "text", "stage": "retriever", "content": f"Randomly selected {sample_size} references"})
            await self.emit(on_event, "stage", {"name": "retriever", "status": "done", "progress": 0.1})
            return data

        content = str(data.get("content", ""))
        visual_intent = data.get("visual_intent", "")
        top_k = data.get("retriever_top_k", 10)
        pool_size = data.get("retriever_pool_size")
        pool = candidates if not pool_size else candidates[:pool_size]
        query = f"{visual_intent}\n{content}"
        retrieved = self._local_vector_search(query, pool, top_k)
        retrieved = self._load_reference_images(retrieved, task_type)
        await self.emit(on_event, "intermediate", {
            "type": "text", "stage": "retriever",
            "content": f"本地向量检索：从 {len(pool)} 个候选中选取 {len(retrieved)} 个相关参考，未调用模型重排",
        })
        data["top10_references"] = [item["id"] for item in retrieved]
        data["retrieved_examples"] = retrieved
        await self.emit(on_event, "intermediate", {"type": "text", "stage": "retriever", "content": f"已选取 {len(retrieved)} 个本地向量最相关参考"})

        await self.emit(on_event, "stage", {"name": "retriever", "status": "done", "progress": 0.1})
        return data

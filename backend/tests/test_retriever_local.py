import pytest

from app.agents.retriever_agent import RetrieverAgent


class NoChat:
    async def chat(self, *args, **kwargs):
        raise AssertionError("local retrieval must not call the chat model")


@pytest.mark.asyncio
async def test_auto_retrieval_uses_local_vector_results_without_llm():
    agent = RetrieverAgent(chat_lb=NoChat())
    agent._candidate_pools["diagram"] = [
        {"id": "ref_irrelevant", "content": "medical image segmentation", "visual_intent": "clinical"},
        {"id": "ref_match", "content": "retrieval augmented generation pipeline with encoder and decoder", "visual_intent": "method pipeline"},
        {"id": "ref_other", "content": "robot grasping trajectory planning", "visual_intent": "robotics"},
    ]

    result = await agent.process({
        "task_type": "diagram",
        "retrieval_setting": "auto",
        "retriever_top_k": 1,
        "content": "Our retrieval augmented generation pipeline uses an encoder and decoder.",
        "visual_intent": "method pipeline",
    })

    assert [item["id"] for item in result["retrieved_examples"]] == ["ref_match"]
    assert result["top10_references"] == ["ref_match"]


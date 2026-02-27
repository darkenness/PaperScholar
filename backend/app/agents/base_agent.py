from abc import ABC, abstractmethod
from typing import Any, Callable, Coroutine, Dict, Optional

from app.llm.load_balancer import LoadBalancer


class BaseAgent(ABC):
    """Base class for all pipeline agents."""

    def __init__(self, chat_lb: Optional[LoadBalancer] = None, image_lb: Optional[LoadBalancer] = None):
        self.chat_lb = chat_lb
        self.image_lb = image_lb

    @abstractmethod
    async def process(self, data: Dict[str, Any], on_event: Optional[Callable] = None) -> Dict[str, Any]:
        """Process input data and return updated data dict.

        Args:
            data: Pipeline data dictionary passed between agents.
            on_event: Optional async callback for SSE events.
                      Signature: on_event(event_type: str, event_data: dict)
        """

    async def emit(self, on_event: Optional[Callable], event_type: str, event_data: dict):
        """Helper to safely emit an SSE event."""
        if on_event:
            await on_event(event_type, event_data)

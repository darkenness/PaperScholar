import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from app.llm.base_client import BaseLLMClient
from app.llm.client_factory import LLMClientFactory

logger = logging.getLogger(__name__)


@dataclass
class ClientConfig:
    provider: str
    api_key: str
    base_url: Optional[str] = None
    model: str = ""
    priority: int = 0
    api_key_id: Optional[int] = None  # DB id for usage logging


@dataclass
class ClientState:
    client: BaseLLMClient
    config: ClientConfig
    failures: int = 0
    is_disabled: bool = False


class LoadBalancer:
    """Round-robin load balancer with automatic failover for multiple LLM clients."""

    def __init__(self, configs: list[ClientConfig], usage_callback=None):
        self._usage_callback = usage_callback  # async fn(provider, model, api_key_id, success, error_msg, latency_ms)
        self._states: list[ClientState] = []
        self._index: int = 0
        self._lock = asyncio.Lock()

        sorted_configs = sorted(configs, key=lambda c: c.priority, reverse=True)
        for cfg in sorted_configs:
            client = LLMClientFactory.create(
                provider=cfg.provider,
                api_key=cfg.api_key,
                base_url=cfg.base_url,
                model=cfg.model,
            )
            self._states.append(ClientState(client=client, config=cfg))

    @property
    def client_count(self) -> int:
        return len(self._states)

    def _next_available(self) -> Optional[ClientState]:
        """Get next available client in round-robin order."""
        n = len(self._states)
        for _ in range(n):
            state = self._states[self._index % n]
            self._index += 1
            if not state.is_disabled:
                return state
        return None

    async def call(self, method: str, max_retries: int = 2, **kwargs) -> Any:
        """Call a method on the next available client with automatic failover and exponential backoff retry."""
        if not self._states:
            raise RuntimeError("No LLM clients configured")

        last_error = None
        tried = 0

        for _ in range(len(self._states)):
            async with self._lock:
                state = self._next_available()

            if state is None:
                break

            tried += 1
            # Exponential backoff retry per client
            for retry in range(max_retries + 1):
                try:
                    result = await getattr(state.client, method)(**kwargs)
                    # Reset failure count on success
                    state.failures = 0
                    return result
                except Exception as e:
                    last_error = e
                    if retry < max_retries:
                        backoff = min(2 ** retry, 8)  # 1s, 2s, 4s, max 8s
                        logger.warning(
                            f"LLM client {state.config.provider}({state.config.model}) "
                            f"retry {retry + 1}/{max_retries} after {backoff}s: {e}"
                        )
                        await asyncio.sleep(backoff)
                    else:
                        state.failures += 1
                        logger.warning(
                            f"LLM client {state.config.provider}({state.config.model}) "
                            f"failed after {max_retries + 1} attempts (consecutive: {state.failures}): {e}"
                        )
                        # Disable after 3 consecutive failures
                        if state.failures >= 3:
                            state.is_disabled = True
                            logger.error(
                                f"LLM client {state.config.provider}({state.config.model}) "
                                f"disabled after {state.failures} consecutive failures"
                            )

        raise RuntimeError(
            f"All {tried} LLM clients failed. Last error: {last_error}"
        )

    async def chat(self, messages: list[dict], **kwargs) -> str:
        return await self.call("chat", messages=messages, **kwargs)

    async def chat_with_images(self, contents: list[Any], **kwargs) -> str:
        return await self.call("chat_with_images", contents=contents, **kwargs)

    async def generate_image(self, prompt: str, **kwargs) -> Optional[bytes]:
        return await self.call("generate_image", prompt=prompt, **kwargs)

    async def generate_image_with_images(self, prompt: str, images: list[dict], **kwargs) -> Optional[bytes]:
        return await self.call("generate_image_with_images", prompt=prompt, images=images, **kwargs)

    async def generate_image_from_chat(self, contents: list[Any], **kwargs) -> Optional[bytes]:
        return await self.call("generate_image_from_chat", contents=contents, **kwargs)

    def reset_all(self):
        """Reset all client states (re-enable disabled clients)."""
        for state in self._states:
            state.failures = 0
            state.is_disabled = False
        self._index = 0

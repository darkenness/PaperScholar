import asyncio
import hashlib
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, Optional, TYPE_CHECKING

from app.llm.base_client import BaseLLMClient
from app.llm.image_validation import InvalidModelOutputError, validate_image_bytes
from app.llm.client_factory import LLMClientFactory
from app.services.cost_service import BudgetExceededError, CostTracker

if TYPE_CHECKING:
    from app.services.key_pool_service import KeyPoolManager

logger = logging.getLogger(__name__)

_GLOBAL_KEY_COOLDOWNS: dict[str, float] = {}
_GLOBAL_KEY_IN_FLIGHT: dict[str, int] = {}
_GLOBAL_POOL_LOCK = asyncio.Lock()
_MAX_IN_FLIGHT_PER_KEY = 1


@dataclass
class ClientConfig:
    provider: str
    api_key: str
    base_url: Optional[str] = None
    model: str = ""
    priority: int = 0
    api_key_id: Optional[int] = None  # DB id for usage logging
    api_options: dict = field(default_factory=dict)


@dataclass
class ClientState:
    client: BaseLLMClient
    config: ClientConfig
    failures: int = 0
    is_disabled: bool = False
    cooldown_until: float = 0.0


class LoadBalancer:
    """Round-robin load balancer with automatic failover for multiple LLM clients."""

    def __init__(
        self,
        configs: list[ClientConfig],
        usage_callback=None,
        wait_callback=None,
        cost_tracker: Optional[CostTracker] = None,
        key_pool_manager: Optional["KeyPoolManager"] = None,
        start_index: int = 0,
        max_queue_wait_seconds: float = 300.0,
        before_call=None,
    ):
        self._before_call = before_call
        self._usage_callback = usage_callback  # async fn(provider, model, api_key_id, success, error_msg, latency_ms)
        self._wait_callback = wait_callback
        self._cost_tracker = cost_tracker
        self._key_pool_manager = key_pool_manager
        self._max_queue_wait_seconds = max_queue_wait_seconds
        self._states: list[ClientState] = []
        self._index: int = max(0, start_index)
        self._lock = asyncio.Lock()

        sorted_configs = sorted(configs, key=lambda c: c.priority, reverse=True)
        for cfg in sorted_configs:
            client = LLMClientFactory.create(
                provider=cfg.provider,
                api_key=cfg.api_key,
                base_url=cfg.base_url,
                model=cfg.model,
                api_options=cfg.api_options,
            )
            self._states.append(ClientState(client=client, config=cfg))

    @property
    def client_count(self) -> int:
        return len(self._states)

    def _next_available(self, now: Optional[float] = None) -> Optional[ClientState]:
        """Get next available client in round-robin order (lock-free read)."""
        now = now if now is not None else time.monotonic()
        n = len(self._states)
        for _ in range(n):
            idx = self._index % n
            self._index += 1
            state = self._states[idx]
            if self._is_state_available(state, now):
                return state
        return None

    def _key_identity(self, state: ClientState) -> str:
        fingerprint = hashlib.sha256(state.config.api_key.encode("utf-8")).hexdigest()
        return f"{(state.config.base_url or state.config.provider).rstrip('/')}:{fingerprint}"

    def _is_state_available(self, state: ClientState, now: float) -> bool:
        if state.is_disabled:
            return False
        key = self._key_identity(state)
        cooldown_until = max(state.cooldown_until, _GLOBAL_KEY_COOLDOWNS.get(key, 0.0))
        if cooldown_until > now:
            return False
        return _GLOBAL_KEY_IN_FLIGHT.get(key, 0) < state.config.api_options.get("max_concurrency",_MAX_IN_FLIGHT_PER_KEY)

    def _next_availability_delay(self) -> Optional[float]:
        now = time.monotonic()
        delays = []
        has_busy_key = False
        for state in self._states:
            if state.is_disabled:
                continue
            key = self._key_identity(state)
            cooldown_until = max(state.cooldown_until, _GLOBAL_KEY_COOLDOWNS.get(key, 0.0))
            if cooldown_until > now:
                delays.append(cooldown_until - now)
            elif _GLOBAL_KEY_IN_FLIGHT.get(key, 0) >= state.config.api_options.get("max_concurrency",_MAX_IN_FLIGHT_PER_KEY):
                has_busy_key = True
        if has_busy_key:
            delays.append(1.0)
        return max(0.0, min(delays)) if delays else None

    async def _acquire_state(self) -> Optional[ClientState]:
        async with _GLOBAL_POOL_LOCK:
            async with self._lock:
                state = self._next_available()
            if state is not None:
                key = self._key_identity(state)
                _GLOBAL_KEY_IN_FLIGHT[key] = _GLOBAL_KEY_IN_FLIGHT.get(key, 0) + 1
            return state

    async def _release_state(self, state: ClientState):
        async with _GLOBAL_POOL_LOCK:
            key = self._key_identity(state)
            count = _GLOBAL_KEY_IN_FLIGHT.get(key, 0)
            if count <= 1:
                _GLOBAL_KEY_IN_FLIGHT.pop(key, None)
            else:
                _GLOBAL_KEY_IN_FLIGHT[key] = count - 1

    def _set_cooldown(self, state: ClientState, seconds: float):
        cooldown_until = time.monotonic() + seconds
        state.cooldown_until = cooldown_until
        _GLOBAL_KEY_COOLDOWNS[self._key_identity(state)] = cooldown_until

    def set_wait_callback(self, wait_callback):
        self._wait_callback = wait_callback

    def set_cost_tracker(self, cost_tracker: Optional[CostTracker]):
        self._cost_tracker = cost_tracker

    async def _emit_wait(self, delay: float, method: str, round_index: int, max_rounds: int):
        if not self._wait_callback:
            return
        try:
            await self._wait_callback({
                "name": "模型排队",
                "status": f"模型通道繁忙，等待 {int(delay + 0.5)} 秒后自动重试",
                "wait_seconds": round(delay, 1),
                "method": method,
                "round": round_index,
                "max_rounds": max_rounds,
            })
        except Exception as e:
            logger.warning("LoadBalancer wait callback failed: %s", e)

    @staticmethod
    def _status_code(error: Exception) -> Optional[int]:
        response = getattr(error, "response", None)
        for value in (getattr(response, "status_code", None), getattr(error, "status_code", None), getattr(error, "code", None)):
            if isinstance(value, int) and 100 <= value <= 599:
                return value
        return None

    @staticmethod
    def _retry_after_seconds(error: Exception) -> Optional[float]:
        response = getattr(error, "response", None)
        headers = getattr(response, "headers", None)
        if not headers:
            return None
        retry_after = headers.get("retry-after")
        if not retry_after:
            return None
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            return None

    def _cooldown_seconds(self, error: Exception, round_index: int) -> tuple[float, bool]:
        """Return cooldown seconds and whether the error is retryable."""
        status = self._status_code(error)
        retry_after = self._retry_after_seconds(error)
        jitter = random.uniform(0.0, 3.0)

        if status == 429:
            return (retry_after or min(30.0 * round_index, 90.0)) + jitter, True
        if status is not None:
            if 500 <= status <= 599:
                return (retry_after or min(20.0 * round_index, 60.0)) + jitter, True
            return 0.0, False

        err_str = str(error).lower()
        if any(token in err_str for token in ("disconnect", "timed out", "timeout", "connection")):
            return min(10.0 * round_index, 30.0) + jitter, True
        return min(3.0 * round_index, 10.0) + jitter, True

    async def call(self, method: str, max_retries: int = 3, **kwargs) -> Any:
        """Call a method on the next available client with retry.

        429/5xx/network errors cool down the current key and immediately fail
        over to the next key. If every key is cooling down, wait for the soonest
        one before starting the next round.
        """
        if not self._states:
            raise RuntimeError("No LLM clients configured")

        last_error = None
        tried = 0
        max_rounds = max_retries + 1

        busy_wait_started: Optional[float] = None
        round_index = 1
        while round_index <= max_rounds:
            if self._before_call:
                await self._before_call()
            attempted_this_round = 0
            for _ in range(len(self._states)):
                state = await self._acquire_state()

                if state is None:
                    break

                attempted_this_round += 1
                tried += 1
                call_started = time.monotonic()
                try:
                    if self._before_call:
                        await self._before_call()
                    if self._cost_tracker:
                        await self._cost_tracker.check_before_call(
                            state.config.provider,
                            state.config.model,
                            method,
                            kwargs,
                        )
                    result = await getattr(state.client, method)(**kwargs)
                    if method in {"generate_image", "generate_image_with_images", "generate_image_from_chat"}:
                        await asyncio.to_thread(validate_image_bytes, result)
                    elif method in {"chat", "chat_with_images"} and (not isinstance(result, str) or not result.strip()):
                        raise InvalidModelOutputError("Text provider returned no usable text")
                    latency_ms = int((time.monotonic() - call_started) * 1000)
                    usage_entry = None
                    if self._cost_tracker:
                        usage_entry = await self._cost_tracker.record_call(
                            state.config.provider,
                            state.config.model,
                            method,
                            kwargs,
                            result,
                            api_key_id=state.config.api_key_id,
                        )
                    if self._usage_callback:
                        await self._safe_callback(self._usage_callback,
                            provider=state.config.provider,
                            model=state.config.model,
                            api_key_id=state.config.api_key_id,
                            success=True,
                            error_message=None,
                            input_tokens=usage_entry.input_tokens if usage_entry else None,
                            output_tokens=usage_entry.output_tokens if usage_entry else None,
                            total_tokens=(
                                usage_entry.input_tokens + usage_entry.output_tokens
                                if usage_entry else None
                            ),
                            latency_ms=latency_ms,
                        )
                    # Record success in key pool manager
                    if self._key_pool_manager and state.config.api_key_id:
                        await self._safe_callback(self._key_pool_manager.record_call,
                            key_id=state.config.api_key_id,
                            success=True,
                            latency_ms=latency_ms,
                        )
                    state.failures = 0
                    state.cooldown_until = 0.0
                    return result
                except (AttributeError, NotImplementedError, TypeError) as e:
                    last_error = e
                    state.failures += 1
                    state.is_disabled = True
                    logger.error(
                        "LLM client %s(%s, key=%s) permanent error on '%s': %s",
                        state.config.provider,
                        state.config.model,
                        state.config.api_key_id,
                        method,
                        e,
                    )
                except BudgetExceededError:
                    raise
                except Exception as e:
                    last_error = e
                    latency_ms = int((time.monotonic() - call_started) * 1000)
                    if self._usage_callback:
                        await self._safe_callback(self._usage_callback,
                            provider=state.config.provider,
                            model=state.config.model,
                            api_key_id=state.config.api_key_id,
                            success=False,
                            error_message=str(e),
                            input_tokens=None,
                            output_tokens=None,
                            total_tokens=None,
                            latency_ms=latency_ms,
                        )
                    cooldown, retryable = self._cooldown_seconds(e, round_index)
                    if retryable:
                        state.failures += 1
                        self._set_cooldown(state, cooldown)
                        # Record failure in key pool manager
                        error_type = "429" if self._status_code(e) == 429 else "other"
                        if self._key_pool_manager and state.config.api_key_id:
                            await self._safe_callback(self._key_pool_manager.record_call,
                                key_id=state.config.api_key_id,
                                success=False,
                                latency_ms=latency_ms,
                                error_type=error_type,
                            )
                        logger.warning(
                            "LLM client %s(%s, key=%s) failed on '%s' round %s/%s; "
                            "cooling down %.1fs and trying next key: %s",
                            state.config.provider,
                            state.config.model,
                            state.config.api_key_id,
                            method,
                            round_index,
                            max_rounds,
                            cooldown,
                            e,
                        )
                    else:
                        state.failures += 1
                        state.is_disabled = True
                        logger.error(
                            "LLM client %s(%s, key=%s) non-retryable error on '%s': %s",
                            state.config.provider,
                            state.config.model,
                            state.config.api_key_id,
                            method,
                            e,
                        )
                finally:
                    if self._cost_tracker and hasattr(self._cost_tracker,"release_reservation"):
                        self._cost_tracker.release_reservation()
                    await self._release_state(state)

            if attempted_this_round == 0:
                delay = self._next_availability_delay()
                if delay is not None:
                    now = time.monotonic()
                    if busy_wait_started is None:
                        busy_wait_started = now
                    if now + delay - busy_wait_started > self._max_queue_wait_seconds:
                        raise RuntimeError("模型通道正忙，请稍后重试")

                    await self._emit_wait(delay, method, round_index, max_rounds)
                    logger.warning(
                        "All LLM clients are busy or cooling down; waiting %.1fs before retrying round %s/%s",
                        delay,
                        round_index,
                        max_rounds,
                    )
                    await asyncio.sleep(delay)
                    continue

            busy_wait_started = None
            if round_index < max_rounds:
                delay = self._next_availability_delay()
                if delay is not None:
                    await self._emit_wait(delay, method, round_index + 1, max_rounds)
                    logger.warning(
                        "All LLM clients are cooling down; waiting %.1fs before retry round %s/%s",
                        delay,
                        round_index + 1,
                        max_rounds,
                    )
                    await asyncio.sleep(delay)
            round_index += 1

        raise RuntimeError(
            f"All {tried} LLM clients failed. Last error: {last_error}"
        )

    @staticmethod
    async def _safe_callback(callback, **kwargs):
        try:
            await callback(**kwargs)
        except Exception:
            logger.exception("Observer failed; model request will not be issued again")

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
            state.cooldown_until = 0.0
        self._index = 0

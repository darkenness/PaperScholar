"""Key pool management service for dynamic API key health monitoring and selection."""
import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.core.security import decrypt_api_key
from app.models.api_key import ApiKeyConfig

logger = logging.getLogger(__name__)


@dataclass
class KeyHealth:
    """Health status of an API key."""
    key_id: int
    provider: str
    model_name: str
    is_healthy: bool = True
    consecutive_failures: int = 0
    last_success_at: float = 0.0
    last_failure_at: float = 0.0
    cooldown_until: float = 0.0
    total_calls: int = 0
    total_failures: int = 0
    avg_latency_ms: float = 0.0
    rate_limit_hits: int = 0
    last_checked_at: float = field(default_factory=time.time)


class KeyPoolManager:
    """Manages a pool of API keys with health monitoring and automatic failover."""

    def __init__(self, check_interval: int = 60):
        self._health_status: Dict[int, KeyHealth] = {}
        self._check_interval = check_interval
        self._lock = asyncio.Lock()
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the key pool manager background monitor."""
        if self._running:
            return
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("KeyPoolManager started")

    async def stop(self):
        """Stop the key pool manager."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("KeyPoolManager stopped")

    async def _monitor_loop(self):
        """Background loop to monitor key health."""
        while self._running:
            try:
                await self._refresh_health_status()
                await asyncio.sleep(self._check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"KeyPoolManager monitor error: {e}")
                await asyncio.sleep(self._check_interval)

    async def _refresh_health_status(self):
        """Refresh health status from database."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ApiKeyConfig).where(ApiKeyConfig.is_enabled == True)
            )
            configs = result.scalars().all()

            async with self._lock:
                for cfg in configs:
                    if cfg.id not in self._health_status:
                        self._health_status[cfg.id] = KeyHealth(
                            key_id=cfg.id,
                            provider=cfg.provider,
                            model_name=cfg.model_name or "",
                        )

                    health = self._health_status[cfg.id]
                    health.last_checked_at = time.time()

                    # Auto-recover from cooldown
                    if health.cooldown_until > 0 and time.time() > health.cooldown_until:
                        health.cooldown_until = 0.0
                        health.consecutive_failures = 0
                        health.is_healthy = True
                        logger.info(f"Key {cfg.id} recovered from cooldown")

    async def record_call(
        self,
        key_id: int,
        success: bool,
        latency_ms: float,
        error_type: Optional[str] = None,
    ):
        """Record a call result for health tracking."""
        async with self._lock:
            if key_id not in self._health_status:
                return

            health = self._health_status[key_id]
            health.total_calls += 1

            if success:
                health.consecutive_failures = 0
                health.last_success_at = time.time()
                health.is_healthy = True
                # Update rolling average latency
                health.avg_latency_ms = (
                    health.avg_latency_ms * 0.9 + latency_ms * 0.1
                )
            else:
                health.consecutive_failures += 1
                health.total_failures += 1
                health.last_failure_at = time.time()

                if error_type == "429":
                    health.rate_limit_hits += 1
                    # Exponential backoff for rate limits
                    cooldown = min(60.0 * (2 ** health.consecutive_failures), 300.0)
                    health.cooldown_until = time.time() + cooldown
                    health.is_healthy = False
                    logger.warning(
                        f"Key {key_id} hit rate limit, cooling down for {cooldown}s"
                    )
                elif health.consecutive_failures >= 3:
                    # Mark unhealthy after 3 consecutive failures
                    health.is_healthy = False
                    health.cooldown_until = time.time() + 180.0
                    logger.warning(
                        f"Key {key_id} marked unhealthy after {health.consecutive_failures} failures"
                    )

    async def get_healthy_keys(
        self,
        provider: str,
        model_type: str,
        model_name: Optional[str] = None,
    ) -> List[int]:
        """Get list of healthy key IDs for given criteria."""
        async with self._lock:
            now = time.time()
            healthy = []

            for key_id, health in self._health_status.items():
                if not health.is_healthy:
                    continue
                if health.cooldown_until > now:
                    continue
                if health.provider != provider:
                    continue
                if model_name and health.model_name != model_name:
                    continue

                healthy.append(key_id)

            # Sort by health score (lower is better)
            healthy.sort(
                key=lambda kid: (
                    self._health_status[kid].consecutive_failures,
                    self._health_status[kid].rate_limit_hits,
                    self._health_status[kid].avg_latency_ms,
                )
            )

            return healthy

    async def get_health_summary(self) -> Dict:
        """Get summary of all key health status."""
        async with self._lock:
            return {
                "total_keys": len(self._health_status),
                "healthy_keys": sum(1 for h in self._health_status.values() if h.is_healthy),
                "keys": [
                    {
                        "key_id": h.key_id,
                        "provider": h.provider,
                        "model": h.model_name,
                        "is_healthy": h.is_healthy,
                        "consecutive_failures": h.consecutive_failures,
                        "total_calls": h.total_calls,
                        "total_failures": h.total_failures,
                        "success_rate": (
                            (h.total_calls - h.total_failures) / h.total_calls * 100
                            if h.total_calls > 0
                            else 0.0
                        ),
                        "avg_latency_ms": round(h.avg_latency_ms, 2),
                        "rate_limit_hits": h.rate_limit_hits,
                        "cooldown_remaining": max(0, h.cooldown_until - time.time()),
                    }
                    for h in self._health_status.values()
                ],
            }


# Global instance
_key_pool_manager: Optional[KeyPoolManager] = None


async def get_key_pool_manager() -> KeyPoolManager:
    """Get or create the global key pool manager."""
    global _key_pool_manager
    if _key_pool_manager is None:
        _key_pool_manager = KeyPoolManager()
        await _key_pool_manager.start()
    return _key_pool_manager

"""API usage logging service — records LLM calls to api_usage_logs table."""

import logging
import time
from typing import Optional

from app.core.database import AsyncSessionLocal
from app.models.system import ApiUsageLog

logger = logging.getLogger(__name__)


async def log_api_usage(
    user_id: int,
    task_id: Optional[str] = None,
    provider: Optional[str] = None,
    model: Optional[str] = None,
    api_key_id: Optional[int] = None,
    is_system_key: bool = False,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
    success: bool = True,
    error_message: Optional[str] = None,
    latency_ms: Optional[int] = None,
):
    """Record an API usage entry. Safe to call from background tasks."""
    try:
        async with AsyncSessionLocal() as db:
            log_entry = ApiUsageLog(
                user_id=user_id,
                task_id=task_id,
                provider=provider,
                model=model,
                api_key_id=api_key_id,
                is_system_key=is_system_key,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                success=success,
                error_message=error_message,
                latency_ms=latency_ms,
            )
            db.add(log_entry)
            await db.commit()
    except Exception as e:
        logger.warning(f"Failed to log API usage: {e}")

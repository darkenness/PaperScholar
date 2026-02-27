"""Cleanup service: removes expired uploaded references and their files."""

import asyncio
import logging
import os
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.database import AsyncSessionLocal
from app.models.generation import UploadedReference

logger = logging.getLogger(__name__)


async def cleanup_expired_references():
    """Delete expired reference files and mark DB records as deleted."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UploadedReference).where(
                UploadedReference.expires_at < datetime.now(timezone.utc),
                UploadedReference.is_deleted == False,
            )
        )
        expired = result.scalars().all()

        if not expired:
            return 0

        count = 0
        for ref in expired:
            abs_path = os.path.join(settings.UPLOAD_DIR, ref.file_path)
            try:
                if os.path.exists(abs_path):
                    os.remove(abs_path)
            except Exception as e:
                logger.warning(f"Failed to delete file {abs_path}: {e}")

            ref.is_deleted = True
            count += 1

        await db.commit()
        logger.info(f"Cleaned up {count} expired references")
        return count


async def cleanup_loop(interval_seconds: int = 3600):
    """Background loop that runs cleanup periodically."""
    while True:
        try:
            await cleanup_expired_references()
        except Exception as e:
            logger.error(f"Cleanup error: {e}")
        await asyncio.sleep(interval_seconds)

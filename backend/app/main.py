import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.core.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    try:
        await init_db()
        print(f"[PaperScholar] Database initialized successfully")
    except Exception as e:
        print(f"[PaperScholar] WARNING: Database init failed: {e}")
        print(f"[PaperScholar] Server will start but DB features won't work until DB is available")

    # Start background cleanup task
    import asyncio
    from app.services.cleanup_service import cleanup_loop
    cleanup_task = asyncio.create_task(cleanup_loop(interval_seconds=3600))

    print(f"[PaperScholar] Server started in {settings.APP_ENV} mode")
    yield
    # Shutdown
    cleanup_task.cancel()
    print("[PaperScholar] Server shutting down")


app = FastAPI(
    title=settings.APP_NAME,
    description="AI-powered academic illustration generation platform",
    version="0.1.0",
    lifespan=lifespan,
)

# Global exception handler
from app.core.middleware import GlobalExceptionMiddleware
app.add_middleware(GlobalExceptionMiddleware)

# Rate limiting
from app.core.rate_limit import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files (uploads)
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

# Register API routers
from app.api.auth import router as auth_router
from app.api.api_keys import router as api_keys_router, app_router as applications_router
from app.api.generate import router as generate_router
from app.api.admin import router as admin_router
from app.api.files import router as files_router
from app.api.edit import router as edit_router
from app.api.refine import router as refine_router
from app.api.evaluate import router as evaluate_router
from app.api.evolution import router as evolution_router

app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
app.include_router(api_keys_router, prefix=settings.API_V1_PREFIX)
app.include_router(applications_router, prefix=settings.API_V1_PREFIX)
app.include_router(generate_router, prefix=settings.API_V1_PREFIX)
app.include_router(admin_router, prefix=settings.API_V1_PREFIX)
app.include_router(files_router, prefix=settings.API_V1_PREFIX)
app.include_router(edit_router, prefix=settings.API_V1_PREFIX)
app.include_router(refine_router, prefix=settings.API_V1_PREFIX)
app.include_router(evaluate_router, prefix=settings.API_V1_PREFIX)
app.include_router(evolution_router, prefix=settings.API_V1_PREFIX)


@app.get("/api/health")
async def health_check():
    return {"status": "ok", "app": settings.APP_NAME, "version": "0.1.0"}


@app.get(f"{settings.API_V1_PREFIX}/announcements/active")
async def get_active_announcements():
    from sqlalchemy import select
    from app.core.database import AsyncSessionLocal
    from app.models.system import Announcement

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Announcement)
            .where(Announcement.is_active == True)
            .order_by(Announcement.id.desc())
            .limit(5)
        )
        items = result.scalars().all()
        return {
            "items": [
                {
                    "id": a.id,
                    "content": a.content,
                    "is_important": a.is_important,
                    "created_at": a.created_at.isoformat(),
                }
                for a in items
            ]
        }

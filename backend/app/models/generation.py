import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class GenerationTask(Base):
    __tablename__ = "generation_tasks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    task_type: Mapped[str] = mapped_column(String(30), nullable=False)  # diagram | plot | edit | refine
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    visual_intent: Mapped[str | None] = mapped_column(Text, nullable=True)
    pipeline_mode: Mapped[str | None] = mapped_column(String(30), nullable=True)
    retrieval_setting: Mapped[str | None] = mapped_column(String(20), nullable=True)
    num_candidates: Mapped[int] = mapped_column(Integer, default=1)
    aspect_ratio: Mapped[str | None] = mapped_column(String(10), nullable=True)
    max_critic_rounds: Mapped[int] = mapped_column(Integer, default=3)

    chat_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    chat_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    chat_key_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    image_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    image_key_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    current_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    user = relationship("User", back_populates="generation_tasks")
    results = relationship("GenerationResult", back_populates="task", cascade="all, delete-orphan")
    events = relationship("PipelineEvent", back_populates="task", cascade="all, delete-orphan")


class GenerationResult(Base):
    __tablename__ = "generation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("generation_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    candidate_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    svg_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    eval_details: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    planner_desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    stylist_desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    critic_feedback: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    is_favorited: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    task = relationship("GenerationTask", back_populates="results")


class PipelineEvent(Base):
    __tablename__ = "pipeline_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("generation_tasks.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    event_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    task = relationship("GenerationTask", back_populates="events")


class UploadedReference(Base):
    __tablename__ = "uploaded_references"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    task_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("generation_tasks.id", ondelete="SET NULL"), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

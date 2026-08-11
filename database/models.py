"""SQLAlchemy ORM models representing the Mediary database schema."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional
from sqlalchemy import (
    String,
    Text,
    Boolean,
    Integer,
    Float,
    Numeric,
    Date,
    DateTime,
    JSON,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative Base class for all ORM models."""
    pass


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    consent_scope: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    avatar_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Seoul")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    sessions: Mapped[List["DiarySession"]] = relationship(
        "DiarySession", back_populates="user", cascade="all, delete-orphan"
    )
    chats: Mapped[List["DiaryChat"]] = relationship("DiaryChat", back_populates="user")
    location_messages: Mapped[List["LocationMessage"]] = relationship(
        "LocationMessage", back_populates="user", cascade="all, delete-orphan"
    )
    counsel_sessions: Mapped[List["CounselSession"]] = relationship(
        "CounselSession", back_populates="user", cascade="all, delete-orphan"
    )


class DiarySession(Base):
    __tablename__ = "diary_sessions"

    session_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    diary_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, processing, completed, failed

    # Coordinates of the primary location of the day
    latitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 8), nullable=True)
    longitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(11, 8), nullable=True)
    location_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Constraints
    __table_args__ = (
        Index("ix_diary_sessions_user_status_date", "user_id", "status", "diary_date"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="sessions")
    chats: Mapped[List["DiaryChat"]] = relationship(
        "DiaryChat", back_populates="session", cascade="all, delete-orphan"
    )
    inputs: Mapped[List["DiaryInput"]] = relationship(
        "DiaryInput", back_populates="session", cascade="all, delete-orphan"
    )
    versions: Mapped[List["DiaryVersion"]] = relationship(
        "DiaryVersion", back_populates="session", cascade="all, delete-orphan"
    )
    location_messages: Mapped[List["LocationMessage"]] = relationship(
        "LocationMessage", back_populates="session"
    )


class DiaryChat(Base):
    __tablename__ = "diary_chats"

    chat_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[str] = mapped_column(String(50), ForeignKey("diary_sessions.session_id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant
    chat: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="chats")
    session: Mapped["DiarySession"] = relationship("DiarySession", back_populates="chats")


class DiaryInput(Base):
    __tablename__ = "diary_inputs"

    input_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(50), ForeignKey("diary_sessions.session_id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # image, voice, text
    storage_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    transcript: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Transcribed voice STT or OCR content
    captured_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    session: Mapped["DiarySession"] = relationship("DiarySession", back_populates="inputs")


class DiaryVersion(Base):
    __tablename__ = "diary_versions"
    __table_args__ = (
        Index(
            "ix_diary_versions_session_approved_created",
            "session_id",
            "approved",
            "created_at",
        ),
    )

    version_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(50), ForeignKey("diary_sessions.session_id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    emotion_tags: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    paragraphs: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    evidence_input_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    session: Mapped["DiarySession"] = relationship("DiarySession", back_populates="versions")
    video: Mapped[Optional["AvatarVideo"]] = relationship(
        "AvatarVideo", back_populates="version", cascade="all, delete-orphan"
    )
    narration_script: Mapped[Optional["NarrationScript"]] = relationship(
        "NarrationScript",
        back_populates="diary_version",
        cascade="all, delete-orphan",
        single_parent=True,
        uselist=False,
    )


class NarrationScript(Base):
    __tablename__ = "narration_scripts"
    __table_args__ = (
        Index(
            "ix_narration_scripts_version_status_created",
            "diary_version_id",
            "status",
            "created_at",
        ),
    )

    script_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    diary_version_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("diary_versions.version_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    narration_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    emotion: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    tone: Mapped[str] = mapped_column(String(50), default="따뜻한 회상")
    target_duration_seconds: Mapped[int] = mapped_column(Integer, default=30)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    llm_model: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    diary_version: Mapped["DiaryVersion"] = relationship(
        "DiaryVersion", back_populates="narration_script"
    )
    audios: Mapped[List["DiaryAudio"]] = relationship(
        "DiaryAudio", back_populates="script", cascade="all, delete-orphan"
    )


class DiaryAudio(Base):
    __tablename__ = "diary_audios"
    __table_args__ = (
        Index(
            "ix_diary_audios_script_status_created",
            "script_id",
            "status",
            "created_at",
        ),
    )

    audio_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    script_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("narration_scripts.script_id", ondelete="CASCADE"),
        nullable=False,
    )
    voice_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    object_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    audio_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    audio_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    audio_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    audio_mime_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    script: Mapped["NarrationScript"] = relationship(
        "NarrationScript", back_populates="audios"
    )


class AvatarVideo(Base):
    __tablename__ = "avatar_videos"

    video_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    version_id: Mapped[str] = mapped_column(String(50), ForeignKey("diary_versions.version_id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, processing, completed, failed
    storage_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # video length in seconds
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    version: Mapped["DiaryVersion"] = relationship("DiaryVersion", back_populates="video")


class LocationMessage(Base):
    __tablename__ = "location_messages"

    message_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(String(50), ForeignKey("diary_sessions.session_id", ondelete="SET NULL"), nullable=True)

    # Geography details
    latitude: Mapped[Decimal] = mapped_column(Numeric(10, 8), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(11, 8), nullable=False)
    radius: Mapped[float] = mapped_column(Float, default=100.0)  # Lock-unlock radius threshold in meters

    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    audio_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="location_messages")
    session: Mapped[Optional["DiarySession"]] = relationship("DiarySession", back_populates="location_messages")


class CounselSession(Base):
    __tablename__ = "counsel_sessions"

    counsel_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    referenced_diary_ids: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)  # List of diary session IDs referenced
    safety_level: Mapped[str] = mapped_column(String(20), default="safe")  # safe, restricted, crisis

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="counsel_sessions")


class AgentLog(Base):
    __tablename__ = "agent_logs"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    processing_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    result_code: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

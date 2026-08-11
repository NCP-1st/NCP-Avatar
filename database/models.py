"""SQLAlchemy ORM models representing the Mediary database schema."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional
from sqlalchemy import (
    String,
    Text,
    Boolean,
    BigInteger,
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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


# 운영은 PostgreSQL, 테스트는 SQLite 메모리 DB를 쓴다. JSONB와 BIGSERIAL은
# PG에만 있으므로 방언별로 갈라 둔다 — 그렇지 않으면 SQLite에서 create_all이
# 깨지고(JSONB 컴파일 불가), BIGINT PK는 자동증가가 되지 않는다.
JSONB_ = JSON().with_variant(JSONB(), "postgresql")
BIGINT_PK = BigInteger().with_variant(Integer(), "sqlite")


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
    inputs: Mapped[List["DiaryInput"]] = relationship(
        "DiaryInput", back_populates="session", cascade="all, delete-orphan"
    )
    versions: Mapped[List["DiaryVersion"]] = relationship(
        "DiaryVersion", back_populates="session", cascade="all, delete-orphan"
    )
    location_messages: Mapped[List["LocationMessage"]] = relationship(
        "LocationMessage", back_populates="session"
    )


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
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    diary_version: Mapped["DiaryVersion"] = relationship(
        "DiaryVersion",
        back_populates="narration_script",
    )
    audios: Mapped[List["DiaryAudio"]] = relationship(
        "DiaryAudio",
        back_populates="script",
        cascade="all, delete-orphan",
        passive_deletes=True,
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
    voice_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
    )

    object_key: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )
    audio_url: Mapped[Optional[str]] = mapped_column(
        String(512),
        nullable=True,
    )
    audio_hash: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    audio_size: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    audio_mime_type: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    duration_seconds: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )

    error_code: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
    )

    script: Mapped["NarrationScript"] = relationship(
        "NarrationScript",
        back_populates="audios",
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
    """상담 세션 하나. 대화 턴·근거·트레이스의 부모.

    - is_crisis      : store.mark_crisis / store.is_crisis 의 지속 저장소.
                       한 번 켜지면 세션 내내 유지된다.
    - safety_level   : 세션에서 도달한 가장 높은 등급의 롤업.
                       턴별 등급은 counsel_turn_traces 에 있다.
    - memory_*       : C-03 기억 제어 설정(사용자가 세션 단위로 조절).
    - last_active_at : 세션 목록·비활성 만료 판단.
    """

    __tablename__ = "counsel_sessions"

    counsel_id: Mapped[str] = mapped_column(String(50), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)

    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    is_crisis: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    safety_level: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="normal", default="normal"
    )  # normal, caution, crisis

    # C-03 기억 제어. MemoryScope(enabled/period_days/max_items) 지속 설정.
    memory_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )
    memory_period_days: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("30"), default=30
    )
    memory_max_items: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("5"), default=5
    )

    # 세션 단위 참조 일기 롤업(빠른 조회). 정규 소스는 counsel_evidences.
    referenced_diary_ids: Mapped[Optional[List[str]]] = mapped_column(JSONB_, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_counsel_sessions_user_active", "user_id", "last_active_at"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="counsel_sessions")
    turns: Mapped[List["CounselTurn"]] = relationship(
        "CounselTurn",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="CounselTurn.turn_id",
    )


class CounselTurn(Base):
    """상담 대화 한 줄(턴).

    - user_id 를 비정규화해 둔다. load_turns 가 counsel_id + user_id 로 소유권을
      거른다 — 남의 counsel_id 로 대화를 읽어가는 걸 저장소가 막는다.
    - stage 는 어시스턴트 턴에만 있다. _decide_stage 가 직전 어시스턴트 턴의
      stage 를 읽으므로 반드시 저장한다.
    """

    __tablename__ = "counsel_turns"

    turn_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    counsel_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("counsel_sessions.counsel_id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(String(50), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user, assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    stage: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True
    )  # opening, exploring, caring, closing (assistant only)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_counsel_turns_counsel_turn", "counsel_id", "turn_id"),
    )

    # Relationships
    session: Mapped["CounselSession"] = relationship("CounselSession", back_populates="turns")
    trace: Mapped[Optional["CounselTurnTrace"]] = relationship(
        "CounselTurnTrace",
        back_populates="turn",
        cascade="all, delete-orphan",
        uselist=False,
    )
    evidences: Mapped[List["CounselEvidence"]] = relationship(
        "CounselEvidence", back_populates="turn", cascade="all, delete-orphan"
    )


class CounselTurnTrace(Base):
    """어시스턴트 턴 1건의 트레이스(관측·안전 감사). CounselTrace 스키마 대응.

    어시스턴트 턴에만 존재하므로 counsel_turns 와 1:1(turn_id UNIQUE).
    근거 문장·사용자 원문은 저장하지 않는다(emotion 은 라벨만, error_detail 은
    사유 요약만). 사후 리뷰 큐는 result_code='crisis_redirect' 또는
    safety_level='crisis' 로 조회한다.
    """

    __tablename__ = "counsel_turn_traces"

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    turn_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("counsel_turns.turn_id", ondelete="CASCADE"),
        nullable=False,
    )

    trace_id: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    result_code: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # ok, crisis_redirect, guardrail_rewrite, guardrail_blocked, llm_failed
    safety_level: Mapped[str] = mapped_column(String(20), nullable=False)  # normal, caution, crisis
    stage: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    emotion: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # 대표 감정 라벨만

    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    knowledge_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    ontology_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )
    event_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), default=0
    )

    guardrail_hits: Mapped[Optional[List[str]]] = mapped_column(JSONB_, nullable=True)
    stage_ms: Mapped[Optional[dict[str, Any]]] = mapped_column(JSONB_, nullable=True)
    error_detail: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("turn_id", name="uq_counsel_trace_turn"),
        Index("ix_counsel_traces_trace_id", "trace_id"),
        Index("ix_counsel_traces_result_safety", "result_code", "safety_level"),
    )

    # Relationships
    turn: Mapped["CounselTurn"] = relationship("CounselTurn", back_populates="trace")


class CounselEvidence(Base):
    """어시스턴트 답변이 근거로 든 일기(H-02, C-01).

    diary_date 는 카드 표시용 스냅샷이다. 원본 일기가 지워져도 최소 근거는 남는다.
    지금은 counsel_flow 에 일기 검색 갈래가 없어 비어 있다. 검색이 붙을 때 이
    테이블에 쓰고, safety.review_past_claims 를 "검색 결과가 없을 때만" 걸도록
    되돌린다.
    """

    __tablename__ = "counsel_evidences"

    evidence_id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    turn_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"),
        ForeignKey("counsel_turns.turn_id", ondelete="CASCADE"),
        nullable=False,
    )
    diary_session_id: Mapped[Optional[str]] = mapped_column(
        String(50),
        ForeignKey("diary_sessions.session_id", ondelete="SET NULL"),
        nullable=True,
    )
    diary_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # 카드 스냅샷
    relevance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_counsel_evidences_turn", "turn_id"),
    )

    # Relationships
    turn: Mapped["CounselTurn"] = relationship("CounselTurn", back_populates="evidences")


class AgentLog(Base):
    __tablename__ = "agent_logs"

    log_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    trace_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(50), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    processing_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    result_code: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

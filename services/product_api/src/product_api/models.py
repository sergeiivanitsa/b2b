from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db.base import Base


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    inn: Mapped[str | None] = mapped_column(String(16))
    phone: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'legacy'"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id"), nullable=True
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(120))
    last_name: Mapped[str | None] = mapped_column(String(120))
    role: Mapped[str | None] = mapped_column(
        String(32),
        nullable=True,
    )
    is_superadmin: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("false"),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        server_default=text("true"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    joined_company_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AuthToken(Base):
    __tablename__ = "auth_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    session_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(120))
    last_name: Mapped[str | None] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'user'"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invited_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Ledger(Base):
    __tablename__ = "ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("messages.id"))
    delta: Mapped[int] = mapped_column(nullable=False)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"), nullable=False, index=True
    )
    parent_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id"), nullable=True
    )
    client_message_id: Mapped[str | None] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str | None] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(nullable=False)
    usage_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"), index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[int | None] = mapped_column()
    payload_json: Mapped[str] = mapped_column(nullable=False)
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class UserCreditLimit(Base):
    __tablename__ = "user_credit_limits"
    __table_args__ = (
        CheckConstraint(
            "remaining_credits >= 0",
            name="ck_user_credit_limits_remaining_credits_non_negative",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, unique=True)
    remaining_credits: Mapped[int] = mapped_column(
        nullable=False,
        server_default=text("0"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Claim(Base):
    __tablename__ = "claims"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'preview_ready', 'paid', 'in_review', 'sent')",
            name="ck_claims_status",
        ),
        CheckConstraint(
            "generation_state IN ('ready', 'manual_review_required', 'insufficient_data')",
            name="ck_claims_generation_state",
        ),
        CheckConstraint(
            "price_rub >= 0",
            name="ck_claims_price_rub_non_negative",
        ),
        CheckConstraint(
            "case_type IS NULL OR case_type IN ('supply', 'contract_work', 'services')",
            name="ck_claims_case_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'draft'"),
        nullable=False,
        index=True,
    )
    generation_state: Mapped[str] = mapped_column(
        String(32),
        server_default=text("'insufficient_data'"),
        nullable=False,
        index=True,
    )
    price_rub: Mapped[int] = mapped_column(nullable=False)
    edit_token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    client_email: Mapped[str | None] = mapped_column(String(320))
    client_phone: Mapped[str | None] = mapped_column(String(32))
    case_type: Mapped[str | None] = mapped_column(String(32))
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_data_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    generation_notes_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    allowed_blocks_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    blocked_blocks_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    risk_flags_json: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    generated_preview_text: Mapped[str | None] = mapped_column(Text)
    generated_full_text: Mapped[str | None] = mapped_column(Text)
    final_text: Mapped[str | None] = mapped_column(Text)
    summary_for_admin: Mapped[str | None] = mapped_column(Text)
    review_comment: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ClaimFile(Base):
    __tablename__ = "claim_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(512), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(255), nullable=False)
    file_role: Mapped[str] = mapped_column(String(32), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class ClaimEvent(Base):
    __tablename__ = "claim_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("claims.id"), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

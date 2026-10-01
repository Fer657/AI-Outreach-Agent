"""Outreach draft models (Phase 2 draft -> edited -> approved workflow)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class OutreachStatus(str, Enum):
    DRAFT = "DRAFT"
    EDITED = "EDITED"
    APPROVED = "APPROVED"


class OutreachChannel(str, Enum):
    EMAIL = "EMAIL"
    LINKEDIN = "LINKEDIN"


class OutreachDraft(BaseModel):
    id: int | None = None
    channel: OutreachChannel = OutreachChannel.EMAIL
    subject: str | None = None
    body: str
    status: OutreachStatus = OutreachStatus.DRAFT
    confidence: float = Field(default=5.0, ge=0.0, le=10.0)
    referenced_sources: list[str] = Field(
        default_factory=list, description="Evidence/knowledge URLs used"
    )

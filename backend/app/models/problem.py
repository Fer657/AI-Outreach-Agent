"""Inferred business-problem models.

A `Problem` is an *inference* derived from observed signals and internal
knowledge. It must always be phrased tentatively and cite the evidence it is
based on.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Problem(BaseModel):
    title: str
    description: str
    rationale: str = Field(
        default="", description="Why this problem is inferred from the evidence"
    )
    severity: Severity = Severity.MEDIUM
    confidence: float = Field(default=5.0, ge=0.0, le=10.0)
    related_signals: list[str] = Field(
        default_factory=list, description="Signal titles this problem relates to"
    )
    source_urls: list[str] = Field(
        default_factory=list, description="Evidence URLs supporting the inference"
    )

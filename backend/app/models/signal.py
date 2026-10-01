"""Business signal models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, field_validator


class SignalType(str, Enum):
    FUNDING = "FUNDING"
    HIRING = "HIRING"
    EXPANSION = "EXPANSION"
    PRODUCT_LAUNCH = "PRODUCT_LAUNCH"
    PARTNERSHIP = "PARTNERSHIP"
    ACQUISITION = "ACQUISITION"
    LEADERSHIP = "LEADERSHIP"
    TECHNOLOGY = "TECHNOLOGY"
    CUSTOMER = "CUSTOMER"
    OPERATIONAL = "OPERATIONAL"
    EXECUTIVE_STATEMENT = "EXECUTIVE_STATEMENT"
    OTHER = "OTHER"


class Signal(BaseModel):
    """A structured business signal extracted from public evidence.

    Every signal MUST retain the source it came from; sources are never
    fabricated.
    """

    signal_type: SignalType
    title: str
    description: str
    source_name: str
    source_url: str
    published_date: str | None = None
    retrieved_date: str
    evidence: str = Field(
        ..., description="Verbatim or near-verbatim supporting excerpt from the source"
    )
    recency_score: float = Field(default=0.0, ge=0.0, le=10.0)
    source_quality_score: float = Field(default=0.0, ge=0.0, le=10.0)
    relevance_score: float = Field(default=0.0, ge=0.0, le=10.0)

    @field_validator("signal_type", mode="before")
    @classmethod
    def _coerce_signal_type(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip().upper().replace(" ", "_").replace("-", "_")
            aliases = {
                "PRODUCT": "PRODUCT_LAUNCH",
                "LAUNCH": "PRODUCT_LAUNCH",
                "PRODUCTLAUNCH": "PRODUCT_LAUNCH",
                "EXECUTIVE": "EXECUTIVE_STATEMENT",
                "EXEC": "EXECUTIVE_STATEMENT",
                "HIRE": "HIRING",
                "INVESTMENT": "FUNDING",
                "RAISE": "FUNDING",
            }
            normalized = aliases.get(normalized, normalized)
            try:
                return SignalType(normalized)
            except ValueError:
                return SignalType.OTHER
        return value

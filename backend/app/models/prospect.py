"""Prospect input models."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class ProspectInput(BaseModel):
    """What the user submits on the Step 1 form."""

    prospect_name: str = Field(..., min_length=1, description="e.g. Alex Morgan")
    company: str = Field(..., min_length=1, description="e.g. HubSpot")
    job_title: str | None = Field(default=None, description="e.g. VP of Sales")
    company_url: str | None = Field(default=None, description="e.g. https://www.hubspot.com/")
    referral: str | None = Field(default=None, description="Optional referral context")
    # Optional public X/Twitter post or profile URL supplied by the user.
    # We never scrape X; this is only fetched if a URL is explicitly provided.
    x_post_url: str | None = Field(default=None)

    @field_validator("prospect_name", "company")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("job_title", "company_url", "referral", "x_post_url")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("company_url", "x_post_url")
    @classmethod
    def _require_scheme(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith(("http://", "https://")):
            raise ValueError("must be a full URL starting with http:// or https://")
        return value

    @property
    def company_slug(self) -> str:
        """URL/file friendly slug, e.g. 'HubSpot Inc.' -> 'hubspot-inc'."""
        import re

        slug = self.company.lower().strip()
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        return slug.strip("-")

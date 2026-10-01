"""SQLite persistence (prospects, research runs, generated messages).

Phase 1 stores enough to make runs reproducible and to support the Phase 2
draft -> edited -> approved workflow. No ORM; a tiny, explicit schema.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from app.errors import StorageError
from app.logging_config import get_logger
from app.models.prospect import ProspectInput
from app.models.research import ResearchBundle, utc_now_iso

logger = get_logger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS prospects (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_name TEXT NOT NULL,
    company       TEXT NOT NULL,
    company_slug  TEXT NOT NULL,
    job_title     TEXT,
    company_url   TEXT,
    referral      TEXT,
    x_post_url    TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id      INTEGER NOT NULL REFERENCES prospects(id),
    mode             TEXT NOT NULL,
    company          TEXT NOT NULL,
    generated_at     TEXT NOT NULL,
    bundle_json      TEXT NOT NULL,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS generated_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id     INTEGER NOT NULL REFERENCES prospects(id),
    research_run_id INTEGER REFERENCES research_runs(id),
    analysis_id     INTEGER REFERENCES analyses(id),
    channel         TEXT NOT NULL DEFAULT 'email',
    status          TEXT NOT NULL DEFAULT 'DRAFT',
    subject         TEXT,
    content         TEXT NOT NULL,
    confidence      REAL,
    referenced_sources TEXT,
    problem_title   TEXT,
    service         TEXT,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analyses (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    prospect_id      INTEGER NOT NULL REFERENCES prospects(id),
    research_run_id  INTEGER REFERENCES research_runs(id),
    mode             TEXT NOT NULL,
    engine           TEXT NOT NULL,
    generated_at     TEXT NOT NULL,
    bundle_json      TEXT NOT NULL,
    created_at       TEXT NOT NULL
);
"""

_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_research_runs_prospect
    ON research_runs (prospect_id, generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_prospect
    ON generated_messages (prospect_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_analysis
    ON generated_messages (analysis_id);
CREATE INDEX IF NOT EXISTS idx_analyses_prospect
    ON analyses (prospect_id, generated_at DESC);
"""

_MESSAGE_MIGRATIONS = (
    ("analysis_id", "INTEGER"),
    ("subject", "TEXT"),
    ("confidence", "REAL"),
    ("referenced_sources", "TEXT"),
    ("problem_title", "TEXT"),
    ("service", "TEXT"),
)

VALID_MESSAGE_STATUSES = ("DRAFT", "EDITED", "APPROVED")


class Database:
    """Thin SQLite wrapper. One connection per operation keeps it thread-safe."""

    def __init__(self, path: Path) -> None:
        self.path = path

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(str(self.path), timeout=10)
        except sqlite3.Error as exc:
            raise StorageError("Could not open the SQLite database.", detail=str(exc)) from exc

        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
            connection.commit()
        except sqlite3.Error as exc:
            connection.rollback()
            raise StorageError("SQLite operation failed.", detail=str(exc)) from exc
        finally:
            connection.close()

    def init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(_SCHEMA)
            self._migrate(connection)
            connection.executescript(_INDEXES)
        logger.info("Initialised SQLite schema at %s", self.path)

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        """Add Phase 2 columns to databases created by Phase 1."""
        existing = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(generated_messages)")
        }
        for column, column_type in _MESSAGE_MIGRATIONS:
            if column not in existing:
                connection.execute(
                    f"ALTER TABLE generated_messages ADD COLUMN {column} {column_type}"
                )

    # ----- prospects --------------------------------------------------------
    def save_prospect(self, prospect: ProspectInput) -> int:
        now = utc_now_iso()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO prospects
                    (prospect_name, company, company_slug, job_title,
                     company_url, referral, x_post_url, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prospect.prospect_name,
                    prospect.company,
                    prospect.company_slug,
                    prospect.job_title,
                    prospect.company_url,
                    prospect.referral,
                    prospect.x_post_url,
                    now,
                ),
            )
            prospect_id = int(cursor.lastrowid)
        logger.info("Saved prospect #%s (%s)", prospect_id, prospect.company)
        return prospect_id

    def get_prospect(self, prospect_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM prospects WHERE id = ?", (prospect_id,)
            ).fetchone()
        return dict(row) if row else None

    # ----- research runs ----------------------------------------------------
    def save_research_run(self, prospect_id: int, bundle: ResearchBundle) -> int:
        now = utc_now_iso()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO research_runs
                    (prospect_id, mode, company, generated_at, bundle_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    prospect_id,
                    bundle.mode,
                    bundle.company,
                    bundle.generated_at,
                    json.dumps(bundle.to_public_dict(), ensure_ascii=False),
                    now,
                ),
            )
            run_id = int(cursor.lastrowid)
        logger.info("Saved research run #%s for prospect #%s", run_id, prospect_id)
        return run_id

    def get_research_run(self, run_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM research_runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["bundle"] = json.loads(record.pop("bundle_json"))
        return record

    def list_research_runs(self, prospect_id: int, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, mode, company, generated_at, created_at
                FROM research_runs
                WHERE prospect_id = ?
                ORDER BY generated_at DESC
                LIMIT ?
                """,
                (prospect_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    # ----- analyses ---------------------------------------------------------
    def save_analysis(
        self,
        prospect_id: int,
        research_run_id: int | None,
        *,
        bundle: dict[str, Any],
        mode: str,
        engine: str,
    ) -> int:
        now = utc_now_iso()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO analyses
                    (prospect_id, research_run_id, mode, engine, generated_at,
                     bundle_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prospect_id,
                    research_run_id,
                    mode,
                    engine,
                    now,
                    json.dumps(bundle, ensure_ascii=False),
                    now,
                ),
            )
            analysis_id = int(cursor.lastrowid)
        logger.info("Saved analysis #%s for prospect #%s", analysis_id, prospect_id)
        return analysis_id

    def update_analysis_bundle(self, analysis_id: int, bundle: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "UPDATE analyses SET bundle_json = ? WHERE id = ?",
                (json.dumps(bundle, ensure_ascii=False), analysis_id),
            )

    def get_analysis(self, analysis_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM analyses WHERE id = ?", (analysis_id,)
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["bundle"] = json.loads(record.pop("bundle_json"))
        return record

    def get_latest_analysis(self, prospect_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM analyses
                WHERE prospect_id = ?
                ORDER BY generated_at DESC, id DESC
                LIMIT 1
                """,
                (prospect_id,),
            ).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["bundle"] = json.loads(record.pop("bundle_json"))
        return record

    def list_analyses(self, prospect_id: int, *, limit: int = 20) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, research_run_id, mode, engine, generated_at, created_at
                FROM analyses
                WHERE prospect_id = ?
                ORDER BY generated_at DESC
                LIMIT ?
                """,
                (prospect_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def link_messages_to_analysis(self, analysis_id: int, message_ids: list[int]) -> None:
        if not message_ids:
            return
        placeholders = ",".join("?" for _ in message_ids)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE generated_messages SET analysis_id = ? WHERE id IN ({placeholders})",
                (analysis_id, *message_ids),
            )

    # ----- generated messages (Phase 2 workflow) ----------------------------
    def save_message(
        self,
        prospect_id: int,
        content: str,
        *,
        research_run_id: int | None = None,
        analysis_id: int | None = None,
        channel: str = "email",
        status: str = "DRAFT",
        subject: str | None = None,
        confidence: float | None = None,
        referenced_sources: list[str] | None = None,
        problem_title: str | None = None,
        service: str | None = None,
    ) -> int:
        if status not in VALID_MESSAGE_STATUSES:
            raise StorageError(
                f"Invalid message status: {status!r}. "
                f"Expected one of {', '.join(VALID_MESSAGE_STATUSES)}."
            )
        now = utc_now_iso()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO generated_messages
                    (prospect_id, research_run_id, analysis_id, channel, status,
                     subject, content, confidence, referenced_sources,
                     problem_title, service, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    prospect_id,
                    research_run_id,
                    analysis_id,
                    channel,
                    status,
                    subject,
                    content,
                    confidence,
                    json.dumps(referenced_sources or [], ensure_ascii=False),
                    problem_title,
                    service,
                    now,
                    now,
                ),
            )
            message_id = int(cursor.lastrowid)
        return message_id

    @staticmethod
    def _message_row(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        record["referenced_sources"] = json.loads(record.get("referenced_sources") or "[]")
        return record

    def get_message(self, message_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM generated_messages WHERE id = ?", (message_id,)
            ).fetchone()
        return self._message_row(row) if row else None

    def update_message(
        self,
        message_id: int,
        *,
        content: str | None = None,
        subject: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        if status is not None and status not in VALID_MESSAGE_STATUSES:
            raise StorageError(
                f"Invalid message status: {status!r}. "
                f"Expected one of {', '.join(VALID_MESSAGE_STATUSES)}."
            )
        assignments: list[str] = []
        values: list[Any] = []
        if content is not None:
            assignments.append("content = ?")
            values.append(content)
        if subject is not None:
            assignments.append("subject = ?")
            values.append(subject)
        if status is not None:
            assignments.append("status = ?")
            values.append(status)
        if not assignments:
            existing = self.get_message(message_id)
            if existing is None:
                raise StorageError(f"Message #{message_id} not found.")
            return existing

        assignments.append("updated_at = ?")
        values.append(utc_now_iso())
        values.append(message_id)
        with self._connect() as connection:
            connection.execute(
                f"UPDATE generated_messages SET {', '.join(assignments)} WHERE id = ?",
                values,
            )
        result = self.get_message(message_id)
        if result is None:
            raise StorageError(f"Message #{message_id} not found.")
        return result

    def set_message_status(self, message_id: int, status: str) -> dict[str, Any]:
        return self.update_message(message_id, status=status)

    def update_message_generation(
        self,
        message_id: int,
        *,
        content: str,
        subject: str | None,
        confidence: float | None,
        referenced_sources: list[str] | None,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE generated_messages
                SET content = ?, subject = ?, confidence = ?,
                    referenced_sources = ?, status = 'DRAFT', updated_at = ?
                WHERE id = ?
                """,
                (
                    content,
                    subject,
                    confidence,
                    json.dumps(referenced_sources or [], ensure_ascii=False),
                    utc_now_iso(),
                    message_id,
                ),
            )
        result = self.get_message(message_id)
        if result is None:
            raise StorageError(f"Message #{message_id} not found.")
        return result

    def list_messages(self, prospect_id: int, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM generated_messages
                WHERE prospect_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (prospect_id, limit),
            ).fetchall()
        return [self._message_row(row) for row in rows]

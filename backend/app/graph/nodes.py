"""LangGraph nodes for the analysis pipeline.

Each node reads a slice of `AnalysisState` and returns the keys it produced.
Dependencies (settings, LLM, RAG, database) are bound on the node object so the
graph stays a plain, testable callable.
"""

from __future__ import annotations

from app.analysis.problem_eval import evaluate_problems
from app.analysis.solution_match import match_solutions
from app.config import Settings
from app.llm.base import LLMProvider
from app.logging_config import get_logger
from app.models.analysis import AnalysisBundle
from app.models.research import ResearchBundle
from app.rag.retriever import RagRetriever
from app.research.service import ResearchService
from app.storage.db import Database

logger = get_logger(__name__)


def _knowledge_query(bundle: ResearchBundle, job_title: str | None) -> str:
    parts = [bundle.company]
    if job_title:
        parts.append(job_title)
    parts.extend(signal.title for signal in bundle.signals[:5])
    return " | ".join(part for part in parts if part)


class AnalysisNodes:
    def __init__(
        self,
        *,
        settings: Settings,
        llm: LLMProvider | None,
        rag: RagRetriever,
        database: Database,
        prefer_llm: bool,
    ) -> None:
        self.settings = settings
        self.llm = llm
        self.rag = rag
        self.database = database
        self.prefer_llm = prefer_llm

    # -- nodes ---------------------------------------------------------------
    async def research(self, state: dict) -> dict:
        prospect = state["prospect"]
        bundle = await ResearchService(self.settings).run(prospect, self.llm)

        prospect_id = self.database.save_prospect(prospect)
        run_id = self.database.save_research_run(prospect_id, bundle)
        logger.info(
            "Analysis research node: prospect #%s run #%s (%s evidence)",
            prospect_id,
            run_id,
            len(bundle.evidence),
        )
        return {
            "prospect_id": prospect_id,
            "research_run_id": run_id,
            "research": bundle,
            "mode": self.settings.research_mode,
        }

    async def knowledge(self, state: dict) -> dict:
        bundle = state["research"]
        query = _knowledge_query(bundle, state["prospect"].job_title)
        chunks = await self.rag.retrieve(query)
        return {"knowledge": chunks}

    async def problems(self, state: dict) -> dict:
        problems, used_llm = await evaluate_problems(
            state["prospect"],
            state["research"],
            self.llm,
            prefer_llm=self.prefer_llm,
        )
        logger.info("Problem node produced %s problems (llm=%s)", len(problems), used_llm)
        return {"problems": problems, "problems_llm": used_llm}

    async def solutions(self, state: dict) -> dict:
        solutions, used_llm = await match_solutions(
            state["prospect"],
            state["problems"],
            state["knowledge"],
            self.llm,
            prefer_llm=self.prefer_llm,
        )
        logger.info("Solution node produced %s matches (llm=%s)", len(solutions), used_llm)
        return {"solutions": solutions, "solutions_llm": used_llm}

    async def persist(self, state: dict) -> dict:
        prospect = state["prospect"]
        drafts = list(state.get("outreach", []))
        flags = [
            state.get("problems_llm", False),
            state.get("solutions_llm", False),
        ]
        if all(flags):
            engine = "llm"
        elif any(flags):
            engine = "mixed"
        else:
            engine = "heuristic"

        mode = state.get("mode", self.settings.research_mode)

        # Save each draft as a message first so the bundle can carry message ids.
        message_ids: list[int] = []
        for draft in drafts:
            draft.id = self.database.save_message(
                state["prospect_id"],
                draft.body,
                research_run_id=state["research_run_id"],
                channel=draft.channel.value,
                status=draft.status.value,
                subject=draft.subject,
                confidence=draft.confidence,
                referenced_sources=draft.referenced_sources,
            )
            message_ids.append(draft.id)

        bundle = AnalysisBundle(
            prospect=prospect,
            mode=mode,
            engine=engine,
            research=state["research"],
            knowledge=state["knowledge"],
            problems=state["problems"],
            solutions=state["solutions"],
            outreach=drafts,
        )
        analysis_id = self.database.save_analysis(
            state["prospect_id"],
            state["research_run_id"],
            bundle=bundle.model_dump(mode="json"),
            mode=mode,
            engine=engine,
        )
        self.database.link_messages_to_analysis(analysis_id, message_ids)
        logger.info("Persisted analysis #%s (%s engine)", analysis_id, engine)
        return {
            "analysis": bundle,
            "analysis_id": analysis_id,
            "outreach": drafts,
            "engine": engine,
        }

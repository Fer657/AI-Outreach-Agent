"""Builds and runs the Phase 2 analysis graph.

Pipeline:
    research -> knowledge -> problems -> solutions -> persist

Outreach drafts are no longer generated automatically: the user selects a
problem and a solution, then calls /api/outreach/generate.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.config import Settings
from app.graph.nodes import AnalysisNodes
from app.graph.state import AnalysisState
from app.llm.base import LLMProvider
from app.models.prospect import ProspectInput
from app.rag.retriever import RagRetriever
from app.storage.db import Database


def build_analysis_graph(nodes: AnalysisNodes):
    """Compile the analysis pipeline into an executable graph."""
    graph = StateGraph(AnalysisState)
    graph.add_node("research_node", nodes.research)
    graph.add_node("knowledge_node", nodes.knowledge)
    graph.add_node("problem_eval", nodes.problems)
    graph.add_node("solution_match", nodes.solutions)
    graph.add_node("persist_node", nodes.persist)

    graph.add_edge(START, "research_node")
    graph.add_edge("research_node", "knowledge_node")
    graph.add_edge("knowledge_node", "problem_eval")
    graph.add_edge("problem_eval", "solution_match")
    graph.add_edge("solution_match", "persist_node")
    graph.add_edge("persist_node", END)

    return graph.compile()


async def run_analysis(
    *,
    settings: Settings,
    llm: LLMProvider | None,
    rag: RagRetriever,
    database: Database,
    prospect: ProspectInput,
) -> AnalysisState:
    """Execute the full analysis pipeline for a prospect."""
    nodes = AnalysisNodes(
        settings=settings,
        llm=llm,
        rag=rag,
        database=database,
        prefer_llm=settings.use_llm_analysis,
    )
    graph = build_analysis_graph(nodes)
    return await graph.ainvoke({"prospect": prospect})

"""Optional LLM, agentic, RAG, and vector-database analysis pipeline."""

import json
from typing import Any, TypedDict

from ..config import settings


class AgentState(TypedDict, total=False):
    resume: str
    target: str
    context: list[dict[str, Any]]
    insights: dict[str, Any]


def _disabled_result(reason: str) -> dict[str, Any]:
    return {"enabled": False, "status": "disabled", "reason": reason}


def _retrieve_documents(postings: list[Any], query: str) -> list[dict[str, Any]]:
    import chromadb

    client = chromadb.PersistentClient(path=settings.vector_db_path)
    collection = client.get_or_create_collection(
        name="job_postings",
        metadata={"hnsw:space": "cosine"},
    )

    documents = []
    ids = []
    metadatas = []
    for posting in postings:
        document_id = f"job-{posting.id}"
        ids.append(document_id)
        documents.append(posting.description)
        metadatas.append({
            "job_id": posting.id,
            "company": posting.company,
            "title": posting.title,
        })

    if ids:
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)

    if not ids:
        return []

    result = collection.query(
        query_texts=[query],
        n_results=min(settings.ai_top_k, len(ids)),
    )
    retrieved = []
    result_documents = result.get("documents", [[]])[0]
    result_metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    for document, metadata, distance in zip(result_documents, result_metadatas, distances):
        retrieved.append({
            "job_id": metadata.get("job_id"),
            "company": metadata.get("company"),
            "title": metadata.get("title"),
            "distance": round(float(distance), 4),
            "excerpt": document[:1200],
        })
    return retrieved


def _run_agent(resume_text: str, target_job: Any, postings: list[Any]) -> dict[str, Any]:
    from langgraph.graph import END, StateGraph
    from openai import OpenAI

    target_context = ""
    if target_job:
        target_context = (
            f"Target role: {target_job.title} at {target_job.company}\n"
            f"Target description:\n{target_job.description[:5000]}\n"
        )

    state: AgentState = {
        "resume": resume_text[:8000],
        "target": target_context,
    }

    def retrieve_node(current: dict[str, Any]) -> dict[str, Any]:
        query = f"{current['target']}\n{current['resume']}"
        return {"context": _retrieve_documents(postings, query)}

    def analyze_node(current: dict[str, Any]) -> dict[str, Any]:
        client = OpenAI(api_key=settings.openai_api_key)
        prompt = {
            "resume": current["resume"],
            "target": current["target"],
            "retrieved_job_context": current.get("context", []),
        }
        response = client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.1,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a careful resume reviewer. Use only the supplied resume "
                        "and retrieved job context. Return JSON with keys: summary, "
                        "strengths, gaps, recommendations, and confidence. "
                        "Each list must contain at most five concise strings."
                    ),
                },
                {"role": "user", "content": json.dumps(prompt)},
            ],
        )
        return {"insights": json.loads(response.choices[0].message.content or "{}")}

    def validate_node(current: dict[str, Any]) -> dict[str, Any]:
        insights = current.get("insights", {})
        for key in ("strengths", "gaps", "recommendations"):
            if not isinstance(insights.get(key), list):
                insights[key] = []
        if not isinstance(insights.get("summary"), str):
            insights["summary"] = ""
        if not isinstance(insights.get("confidence"), (int, float)):
            insights["confidence"] = 0
        return {"insights": insights}

    workflow = StateGraph(AgentState)
    workflow.add_node("retrieve", retrieve_node)
    workflow.add_node("analyze", analyze_node)
    workflow.add_node("validate", validate_node)
    workflow.set_entry_point("retrieve")
    workflow.add_edge("retrieve", "analyze")
    workflow.add_edge("analyze", "validate")
    workflow.add_edge("validate", END)
    result = workflow.compile().invoke(state)
    return {
        "enabled": True,
        "status": "complete",
        "model": settings.openai_model,
        "retrieved_jobs": result.get("context", []),
        "insights": result.get("insights", {}),
    }


def generate_ai_insights(
    resume_text: str,
    target_job: Any,
    postings: list[Any],
) -> dict[str, Any]:
    """Run AI enrichment without making the core analysis dependent on AI."""
    if not settings.ai_enabled:
        return _disabled_result("Set AI_ENABLED=true to enable the AI pipeline")
    if not settings.openai_api_key:
        return _disabled_result("OPENAI_API_KEY is not configured")

    try:
        return _run_agent(resume_text, target_job, postings)
    except Exception as exc:
        return {
            "enabled": False,
            "status": "error",
            "reason": f"AI enrichment unavailable: {type(exc).__name__}",
        }
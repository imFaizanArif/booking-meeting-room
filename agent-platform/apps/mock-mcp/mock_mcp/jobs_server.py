"""Demo Jobs MCP server: search_jobs, get_job, submit_proposal.

Run over stdio:            python -m mock_mcp.jobs_server
Run over Streamable HTTP:  python -m mock_mcp.jobs_server --http --port 8811
"""

from __future__ import annotations

import argparse
import hashlib
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations

from mock_mcp.common import idempotency_key, once

JOBS: list[dict[str, Any]] = [
    {"id": "job-101", "title": "Build a FastAPI backend for a logistics dashboard", "client": "Northwind Freight",
     "hourly_rate": 85, "hours_per_week": 20, "skills": ["python", "fastapi", "postgres"],
     "posted": "2026-10-01", "description": "Design REST endpoints, Postgres schema and background jobs for shipment tracking."},
    {"id": "job-102", "title": "React dashboard with real-time charts", "client": "Helios Energy",
     "hourly_rate": 70, "hours_per_week": 15, "skills": ["typescript", "react", "websockets"],
     "posted": "2026-10-02", "description": "Live telemetry dashboard for solar installations, strict accessibility requirements."},
    {"id": "job-103", "title": "LLM agent integrating MCP tools", "client": "Atlas Legal",
     "hourly_rate": 110, "hours_per_week": 25, "skills": ["python", "llm", "mcp"],
     "posted": "2026-10-03", "description": "Build a document review agent with human approval for every outbound action."},
    {"id": "job-104", "title": "WordPress theme tweaks", "client": "Bloom Bakery",
     "hourly_rate": 30, "hours_per_week": 5, "skills": ["php", "wordpress"],
     "posted": "2026-10-03", "description": "Small layout fixes and a seasonal banner."},
    {"id": "job-105", "title": "Data pipeline on Postgres and dbt", "client": "Cobalt Analytics",
     "hourly_rate": 95, "hours_per_week": 30, "skills": ["sql", "dbt", "postgres", "python"],
     "posted": "2026-10-04", "description": "Model event data, add tests, schedule nightly builds."},
    {"id": "job-106", "title": "Mobile app QA (manual)", "client": "Pocket Travel",
     "hourly_rate": 25, "hours_per_week": 10, "skills": ["qa"],
     "posted": "2026-10-04", "description": "Manual regression passes before each release."},
    {"id": "job-107", "title": "Next.js marketing site rebuild", "client": "Juniper Health",
     "hourly_rate": 75, "hours_per_week": 20, "skills": ["typescript", "nextjs", "react"],
     "posted": "2026-10-05", "description": "Rebuild with the App Router, improve Core Web Vitals."},
    {"id": "job-108", "title": "Kubernetes cost audit", "client": "Granite Cloud",
     "hourly_rate": 120, "hours_per_week": 10, "skills": ["kubernetes", "aws"],
     "posted": "2026-10-05", "description": "Find savings in a 40-node cluster and write a report."},
]

server = MCPServer("demo-jobs", version="1.0.0", instructions="Demo job board. Deterministic data.")


def _matches(job: dict[str, Any], query: str, skills: list[str]) -> bool:
    text = f"{job['title']} {job['description']}".lower()
    words = [w for w in query.lower().split() if w]
    by_query = not words or any(w in text or w in job["skills"] for w in words)
    by_skill = not skills or bool(set(s.lower() for s in skills) & set(job["skills"]))
    return by_query and by_skill


@server.tool(annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True))
def search_jobs(query: str = "", skills: list[str] | None = None, min_hourly_rate: int = 0, limit: int = 10) -> dict[str, Any]:
    """Search open job listings by keyword, skills and minimum hourly rate (USD)."""
    found = [j for j in JOBS if _matches(j, query, skills or []) and j["hourly_rate"] >= min_hourly_rate]
    return {"jobs": [{k: j[k] for k in ("id", "title", "client", "hourly_rate", "hours_per_week", "skills", "posted")}
                     for j in found[: max(1, min(limit, 50))]], "total": len(found)}


@server.tool(annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True))
def get_job(job_id: str) -> dict[str, Any]:
    """Get the full listing for one job id."""
    for job in JOBS:
        if job["id"] == job_id:
            return job
    raise ValueError(f"Unknown job id {job_id}")


@server.tool(annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=False, open_world_hint=True))
def submit_proposal(job_id: str, cover_letter: str, hourly_rate: int, ctx: Context) -> dict[str, Any]:
    """Submit a proposal for a job. This sends the proposal to the client and cannot be undone."""
    if not any(j["id"] == job_id for j in JOBS):
        raise ValueError(f"Unknown job id {job_id}")
    if len(cover_letter.strip()) < 20:
        raise ValueError("cover_letter must be at least 20 characters")

    def action() -> dict[str, Any]:
        digest = hashlib.sha256(f"{job_id}:{cover_letter}:{hourly_rate}".encode()).hexdigest()[:10]
        return {"proposal_id": f"prop-{digest}", "job_id": job_id, "hourly_rate": hourly_rate, "status": "submitted"}

    return once("jobs", idempotency_key(ctx), action)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true", help="serve Streamable HTTP instead of stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8811)
    args = parser.parse_args()
    if args.http:
        import uvicorn

        uvicorn.run(server.streamable_http_app(host=args.host), host=args.host, port=args.port, log_level="warning")
    else:
        server.run()


if __name__ == "__main__":
    main()

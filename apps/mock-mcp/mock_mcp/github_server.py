"""Demo GitHub MCP server (stdio): list_repositories, get_repository, create_issue."""

from __future__ import annotations

import argparse
import hashlib
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations

from mock_mcp.common import idempotency_key, once

REPOS: list[dict[str, Any]] = [
    {"name": "shipment-tracker", "language": "python", "topics": ["fastapi", "postgres", "celery"], "stars": 142,
     "description": "Real-time shipment tracking API with Postgres and background workers."},
    {"name": "mcp-review-agent", "language": "python", "topics": ["llm", "mcp", "agents"], "stars": 318,
     "description": "Document review agent with MCP tools and human-in-the-loop approvals."},
    {"name": "telemetry-ui", "language": "typescript", "topics": ["react", "websockets", "charts"], "stars": 77,
     "description": "Accessible real-time dashboards for IoT telemetry."},
    {"name": "dbt-events", "language": "sql", "topics": ["dbt", "postgres", "analytics"], "stars": 54,
     "description": "Event modelling with tests and incremental models."},
    {"name": "next-landing", "language": "typescript", "topics": ["nextjs", "react", "performance"], "stars": 39,
     "description": "App Router marketing site template scoring 100 on Lighthouse."},
]

server = MCPServer("demo-github", version="1.0.0")


@server.tool(annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True))
def list_repositories(topic: str = "", language: str = "") -> dict[str, Any]:
    """List the user's repositories, optionally filtered by topic or language."""
    repos = [r for r in REPOS
             if (not topic or topic.lower() in r["topics"] or topic.lower() == r["language"])
             and (not language or r["language"] == language.lower())]
    return {"repositories": [{k: r[k] for k in ("name", "language", "topics", "stars")} for r in repos]}


@server.tool(annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True))
def get_repository(name: str) -> dict[str, Any]:
    """Get one repository with its description."""
    for repo in REPOS:
        if repo["name"] == name:
            return repo
    raise ValueError(f"Unknown repository {name}")


@server.tool(annotations=ToolAnnotations(destructive_hint=False, idempotent_hint=False))
def create_issue(repository: str, title: str, body: str, ctx: Context) -> dict[str, Any]:
    """Open an issue on a repository."""
    if not any(r["name"] == repository for r in REPOS):
        raise ValueError(f"Unknown repository {repository}")

    def action() -> dict[str, Any]:
        number = int(hashlib.sha256(f"{repository}:{title}".encode()).hexdigest()[:4], 16) % 900 + 100
        return {"repository": repository, "number": number, "title": title, "state": "open"}

    return once("github", idempotency_key(ctx), action)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true")
    parser.add_argument("--port", type=int, default=8813)
    args = parser.parse_args()
    if args.http:
        import uvicorn

        uvicorn.run(server.streamable_http_app(), host="127.0.0.1", port=args.port, log_level="warning")
    else:
        server.run()


if __name__ == "__main__":
    main()

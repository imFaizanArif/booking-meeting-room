"""Demo Calendar MCP server (stdio): check_availability, create_event."""

from __future__ import annotations

import argparse
import hashlib
from datetime import date, timedelta
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.types import ToolAnnotations

from mock_mcp.common import idempotency_key, once

server = MCPServer("demo-calendar", version="1.0.0")
# Committed hours per weekday (Mon..Sun), deterministic.
BASE_COMMITTED = [3, 4, 2, 3, 2, 0, 0]


@server.tool(annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True))
def check_availability(hours_per_week: int, start_date: str = "2026-10-12", weeks: int = 4) -> dict[str, Any]:
    """Check whether a weekly commitment fits the calendar. Dates are ISO yyyy-mm-dd."""
    start = date.fromisoformat(start_date)
    capacity_per_week = 40
    schedule = []
    for w in range(max(1, min(weeks, 12))):
        week_start = start + timedelta(weeks=w)
        committed = sum(BASE_COMMITTED) + (w % 3) * 2
        free = capacity_per_week - committed
        schedule.append({"week_of": week_start.isoformat(), "committed_hours": committed, "free_hours": free,
                         "fits": free >= hours_per_week})
    return {"hours_requested": hours_per_week, "fits_all_weeks": all(s["fits"] for s in schedule),
            "weeks": schedule}


@server.tool(annotations=ToolAnnotations(destructive_hint=False, idempotent_hint=False))
def create_event(title: str, start: str, duration_minutes: int, ctx: Context) -> dict[str, Any]:
    """Create a calendar event. Visible to invitees."""
    def action() -> dict[str, Any]:
        digest = hashlib.sha256(f"{title}:{start}:{duration_minutes}".encode()).hexdigest()[:8]
        return {"event_id": f"evt-{digest}", "title": title, "start": start, "duration_minutes": duration_minutes}

    return once("calendar", idempotency_key(ctx), action)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--http", action="store_true")
    parser.add_argument("--port", type=int, default=8812)
    args = parser.parse_args()
    if args.http:
        import uvicorn

        uvicorn.run(server.streamable_http_app(), host="127.0.0.1", port=args.port, log_level="warning")
    else:
        server.run()


if __name__ == "__main__":
    main()

"""Tool discovery: upsert `mcp_tools` from a live listing and flag stale tools.

Safety defaults (annotations are untrusted hints):
* new tools start disabled;
* `requires_approval` is true unless the server marks the tool `readOnlyHint: true`;
* `is_destructive` mirrors `destructiveHint` (the MCP default for non-read-only tools is true);
* operator changes to flags are never overwritten by later discoveries.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import RiskLevel
from app.core.time import utcnow
from app.mcp.types import DiscoveredTool
from app.models import MCPServer, MCPTool


@dataclass
class DiscoveryReport:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    schema_changed: list[str] = field(default_factory=list)


def default_flags(tool: DiscoveredTool) -> dict[str, object]:
    ann = tool.annotations
    read_only = ann.get("readOnlyHint") is True
    destructive = (not read_only) and ann.get("destructiveHint", True) is not False
    risk = RiskLevel.low if read_only else (RiskLevel.high if destructive else RiskLevel.medium)
    return {
        "is_read_only": read_only,
        "is_destructive": destructive,
        "requires_approval": not read_only,
        "risk_level": risk,
    }


async def upsert_tools(session: AsyncSession, server: MCPServer, tools: list[DiscoveredTool]) -> DiscoveryReport:
    now = utcnow()
    report = DiscoveryReport()
    existing = {
        t.name: t
        for t in (await session.scalars(select(MCPTool).where(MCPTool.server_id == server.id))).all()
    }
    seen: set[str] = set()
    for tool in tools:
        seen.add(tool.name)
        row = existing.get(tool.name)
        digest = tool.schema_hash
        if row is None:
            session.add(MCPTool(
                workspace_id=server.workspace_id, server_id=server.id, name=tool.name, title=tool.title,
                description=tool.description, input_schema=tool.input_schema, output_schema=tool.output_schema,
                annotations=tool.annotations, schema_hash=digest, is_enabled=False, is_stale=False,
                last_discovered_at=now, **default_flags(tool),
            ))
            report.added.append(tool.name)
            continue
        changed = row.schema_hash != digest
        row.title, row.description = tool.title, tool.description
        row.input_schema, row.output_schema, row.annotations = tool.input_schema, tool.output_schema, tool.annotations
        row.schema_hash = digest
        row.is_stale = False
        row.last_discovered_at = now
        if changed:
            report.schema_changed.append(tool.name)
            report.updated.append(tool.name)
        else:
            report.unchanged.append(tool.name)
    for name, row in existing.items():
        if name not in seen and not row.is_stale:
            row.is_stale = True
            report.stale.append(name)
    server.last_discovered_at = now
    await session.flush()
    return report

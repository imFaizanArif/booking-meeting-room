"""`python -m app.db.migrate [--seed]`: apply migrations, set up checkpoint tables, close the platform's
tables to Supabase's Data API, seed demo data."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from alembic import command
from alembic.config import Config

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import dispose_engine, get_engine, session_factory
from app.db.supabase import lock_down
from app.workers.checkpointer import open_checkpointer


def upgrade() -> None:
    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent / "migrations"))
    command.upgrade(cfg, "head")


async def setup_checkpointer() -> None:
    async with open_checkpointer(max_size=1):
        pass


async def restrict_data_api() -> list[str]:
    async with get_engine().begin() as conn:
        tables = await lock_down(conn)
    await dispose_engine()
    return tables


async def seed(discover: bool) -> dict[str, object]:
    from app.seed.demo import seed_all

    async with session_factory()() as session:
        result = await seed_all(session, discover=discover)
    await dispose_engine()
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", action="store_true")
    parser.add_argument("--no-discover", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(settings.log_level, json=False)
    upgrade()
    asyncio.run(setup_checkpointer())
    tables = asyncio.run(restrict_data_api())
    print(f"Row Level Security on {len(tables)} tables; Data API roles revoked")
    if args.seed or settings.seed_demo:
        print(json.dumps(asyncio.run(seed(not args.no_discover)), indent=2))


if __name__ == "__main__":
    main()

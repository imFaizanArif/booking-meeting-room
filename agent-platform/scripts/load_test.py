"""Load test: start many demo executions at once, approve them, and report timings.

Usage (stack running): uv run python scripts/load_test.py --executions 50 --approve
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time

import httpx

TERMINAL = {"completed", "failed", "cancelled"}


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://localhost:8000")
    parser.add_argument("--executions", type=int, default=50)
    parser.add_argument("--approve", action="store_true", help="approve every gated call")
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args()

    async with httpx.AsyncClient(base_url=args.base, timeout=60) as client:
        login = await client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "admin-password"})
        login.raise_for_status()
        headers = {"x-csrf-token": login.json()["csrf_token"]}
        pipelines = (await client.get("/api/v1/pipelines")).json()
        pipeline = next(p for p in pipelines if p["slug"] == "job_application_assistant")

        started = time.perf_counter()
        runs = await asyncio.gather(*(
            client.post(f"/api/v1/pipelines/{pipeline['id']}/run", json={"input": {"query": "python"}}, headers=headers)
            for _ in range(args.executions)
        ))
        ids = {r.json()["id"]: time.perf_counter() for r in runs if r.status_code == 202}
        print(f"enqueued {len(ids)}/{args.executions} in {time.perf_counter() - started:.2f}s")

        done: dict[str, float] = {}
        paused_at: dict[str, float] = {}
        deadline = time.perf_counter() + args.timeout
        while len(done) < len(ids) and time.perf_counter() < deadline:
            await asyncio.sleep(1)
            for eid in [i for i in ids if i not in done]:
                status = (await client.get(f"/api/v1/executions/{eid}")).json()["execution"]["status"]
                if status == "paused_for_review" and eid not in paused_at:
                    paused_at[eid] = time.perf_counter()
                    if args.approve:
                        approvals = (await client.get("/api/v1/approvals", params={"execution_id": eid, "status": "pending"})).json()
                        for approval in approvals["items"]:
                            await client.post(f"/api/v1/approvals/{approval['id']}/decision", json={"action": "approve"},
                                              headers=headers)
                if status in TERMINAL or (status == "paused_for_review" and not args.approve):
                    done[eid] = time.perf_counter()
        to_pause = [paused_at[i] - ids[i] for i in paused_at]
        total = [done[i] - ids[i] for i in done]
        if to_pause:
            print(f"time to approval pause: p50 {statistics.median(to_pause):.2f}s, max {max(to_pause):.2f}s")
        if total:
            print(f"time to settle: p50 {statistics.median(total):.2f}s, max {max(total):.2f}s ({len(done)}/{len(ids)})")
        print(f"wall clock {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())

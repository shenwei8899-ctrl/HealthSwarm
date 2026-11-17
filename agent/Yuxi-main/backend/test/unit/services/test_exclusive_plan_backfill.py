import asyncio
from uuid import UUID

from yuxi.services import exclusive_plan_backfill as backfill


def test_backfill_reuses_stable_first_request_without_trade_policy(monkeypatch):
    calls = []

    async def owners(cursor):
        return {
            "": ([], "page-1"),
            "page-1": ([("family", "owner")], "page-2"),
            "page-2": ([], None),
        }[cursor]

    async def start(uid, fid, data, **options):
        calls.append((uid, fid, data.client_request_id, options))
        return None

    monkeypatch.setattr(backfill, "eligible_owners", owners)
    monkeypatch.setattr(backfill, "start_exclusive_plan", start)

    async def run_twice():
        await backfill.prepare_missing_exclusive_plans({})
        await backfill.prepare_missing_exclusive_plans({})

    asyncio.run(run_twice())
    assert len(calls) == 2 and calls[0] == calls[1]
    assert calls[0][:2] == ("owner", "family")
    assert isinstance(calls[0][2], UUID)
    assert calls[0][3] == {"only_missing": True}

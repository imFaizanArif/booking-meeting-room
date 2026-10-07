from __future__ import annotations

import uuid

from fastapi import APIRouter, Query

from app.api.deps import DB, Auth
from app.core.enums import ApprovalStatus
from app.hitl import approvals as hitl
from app.schemas.common import Page
from app.schemas.runtime import ApprovalDetail, ApprovalOut, DecisionIn
from app.services import approvals as service

router = APIRouter(prefix="/approvals", tags=["approvals"])


@router.get("", response_model=Page[ApprovalOut])
async def list_approvals(
    ctx: Auth,
    session: DB,
    status: ApprovalStatus | None = None,
    execution_id: uuid.UUID | None = None,
    limit: int = Query(100, le=500),
    offset: int = 0,
) -> Page[ApprovalOut]:
    items, total = await service.list_approvals(
        session, ctx, status=status, execution_id=execution_id, limit=limit, offset=offset
    )
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/{approval_id}", response_model=ApprovalDetail)
async def get_approval(approval_id: uuid.UUID, ctx: Auth, session: DB) -> ApprovalDetail:
    return await service.approval_detail(session, ctx, approval_id)


@router.post("/{approval_id}/decision", response_model=ApprovalDetail)
async def decide_approval(approval_id: uuid.UUID, data: DecisionIn, ctx: Auth, session: DB) -> ApprovalDetail:
    await hitl.decide(
        session,
        ctx,
        approval_id,
        action=data.action,
        edited_arguments=data.edited_arguments,
        edited_data=data.edited_data,
        reason=data.reason,
        feedback=data.feedback,
        result=data.result,
        confirm=data.confirm,
    )
    return await service.approval_detail(session, ctx, approval_id)

"""Draft controller — save / load / list / delete wizard drafts."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.models.draft_model import DraftModel
from app.schemas.draft_schema import DraftSave, DraftResponse, DraftListItem, DraftListResponse
from app.schemas.response import success_response, error_response, ErrorCodes

router = APIRouter()


@router.get("")
async def list_drafts(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(DraftModel).order_by(DraftModel.updated_at.desc())
    )
    drafts = result.scalars().all()
    return success_response(
        DraftListResponse(
            total_count=len(drafts),
            items=[DraftListItem.model_validate(d) for d in drafts],
        ).model_dump()
    )


@router.get("/{draft_id}")
async def get_draft(draft_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(DraftModel).where(DraftModel.id == draft_id)
    )
    draft = result.scalar_one_or_none()
    if not draft:
        return error_response(ErrorCodes.NOT_FOUND, f"Draft '{draft_id}' not found")
    return success_response(DraftResponse.model_validate(draft).model_dump())


@router.put("")
async def save_draft(payload: DraftSave, session: AsyncSession = Depends(get_session)):
    """Upsert: create if new, update if existing."""
    result = await session.execute(
        select(DraftModel).where(DraftModel.id == payload.id)
    )
    draft = result.scalar_one_or_none()

    if draft:
        draft.name = payload.name
        draft.current_step = payload.current_step
        draft.state = payload.state
    else:
        draft = DraftModel(
            id=payload.id,
            name=payload.name,
            current_step=payload.current_step,
            state=payload.state,
        )
        session.add(draft)

    await session.flush()
    return success_response(DraftResponse.model_validate(draft).model_dump())


@router.delete("/{draft_id}")
async def delete_draft(draft_id: str, session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(DraftModel).where(DraftModel.id == draft_id)
    )
    draft = result.scalar_one_or_none()
    if not draft:
        return error_response(ErrorCodes.NOT_FOUND, f"Draft '{draft_id}' not found")
    await session.delete(draft)
    return success_response({"deleted": draft_id})

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update, func, and_, or_, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from hello.services.database import get_session
from hello import models
from hello.schemas import PromptIn, PromptOut, PromptUpdate, PromptsListResponse
from hello.services.error_handlers import handle_db_error
from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.services.prompt_saving import normalize_prompt_list
from hello.utils.user_utils import get_user_email_map
from hello.utils.auth_utils import get_user_from_claims, require_auth

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/", response_model=PromptsListResponse)
async def list_prompts(
    session: AsyncSession = Depends(get_session),
    page: int = 1,
    page_size: int = 20,
    q: str | None = None,
    section: str | None = None,
    property_type: str | None = None,
    status: str | None = None,
    is_default: bool | None = None,
    market: str | None = None,
    sort_by: str | None = Query(default=None, description="Field to sort by"),
    sort_order: str | None = Query(default="desc", description="asc or desc"),
):
    logger.info(
        "#prompts: Listing prompts for page=%s page_size=%s q=%s section=%s property_type=%s status=%s is_default=%s market=%s",
        page,
        page_size,
        q,
        section,
        property_type,
        status,
        is_default,
        market,
    )
    # Clamp page to minimum 1
    page = 1 if page is None or page < 1 else int(page)
    # Clamp page_size to reasonable bounds
    page_size = max(1, min(100, int(page_size))) if page_size else 20
    sort_field = (sort_by or "").strip().lower()
    sort_dir = (sort_order or "desc").strip().lower()
    sort_desc = sort_dir != "asc"
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    base_stmt = select(models.Prompt)

    # Filters
    conds = []
    if q:
        pattern = f"%{q}%"
        conds.append(
            or_(
                models.Prompt.label.ilike(pattern),
                models.Prompt.section.ilike(pattern),
                models.Prompt.body.ilike(pattern),
                models.Prompt.market.ilike(pattern),
            )
        )
    if section:
        conds.append(func.lower(models.Prompt.section) == section.lower())
    if property_type:
        conds.append(func.lower(models.Prompt.property_type) == property_type.lower())
    if status:
        conds.append(func.lower(models.Prompt.status) == status.lower())
    if is_default is not None:
        conds.append(models.Prompt.is_default.is_(bool(is_default)))
    if market:
        conds.append(models.Prompt.market.ilike(f"%{market}%"))
    if conds:
        base_stmt = base_stmt.where(and_(*conds))

    if sort_field:
        res = await session.execute(base_stmt.order_by(models.Prompt.id))
        items = list(res.scalars().all())
        total_count = len(items)
    else:
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        count_res = await session.execute(count_stmt)
        total_count = count_res.scalar() or 0

        stmt = base_stmt.order_by(models.Prompt.created_at.desc()).limit(page_size).offset(start_idx)
        res = await session.execute(stmt)
        items = list(res.scalars().all())

    email_map = await get_user_email_map(
        session, {p.created_by for p in items} | {p.modified_by for p in items}
    )

    def _sort_key(p: models.Prompt):
        if sort_field == "section":
            return (p.section or "").lower()
        if sort_field == "label":
            return (p.label or "").lower()
        if sort_field == "version":
            return getattr(p, "version", 0) or 0
        if sort_field == "property_type":
            return (p.property_type or "").lower()
        if sort_field == "market":
            return (p.market or "").lower()
        if sort_field == "status":
            return (p.status or "").lower()
        if sort_field == "last_modified":
            return p.last_modified or p.created_at or datetime.min
        if sort_field == "created_at":
            return p.created_at or datetime.min
        if sort_field == "created_by":
            return (email_map.get(p.created_by or -1, "") or "").lower()
        if sort_field == "modified_by":
            return (email_map.get(p.modified_by or -1, "") or "").lower()
        return p.created_at or datetime.min

    if items and sort_field:
        items.sort(key=_sort_key, reverse=sort_desc)

    paginated_items = items[start_idx:end_idx] if sort_field else items

    out_items = []
    for p in paginated_items:
        base = PromptOut.model_validate(p)
        out_items.append(
            base.model_copy(
                update={
                    "created_by_email": email_map.get(p.created_by or -1),
                    "modified_by_email": email_map.get(p.modified_by or -1),
                }
            )
        )
    return PromptsListResponse(totalCount=total_count, items=out_items)


@router.post("/bulk-delete")
async def bulk_delete_prompts(
    payload: dict,
    session: AsyncSession = Depends(get_session),
):
    ids = payload.get("ids", [])
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="ids list is required")
    numeric_ids = [int(i) for i in ids if isinstance(i, (int, str)) and str(i).isdigit()]
    if not numeric_ids:
        raise HTTPException(status_code=400, detail="No valid ids provided")
    try:
        result = await session.execute(
            delete(models.Prompt).where(models.Prompt.id.in_(numeric_ids))
        )
        await session.commit()
        return {"deleted": result.rowcount or 0}
    except Exception as err:
        await session.rollback()
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise


@router.post("/", response_model=PromptOut, status_code=201)
async def create_prompt(
    payload: PromptIn,
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
):
    try:
        logger.info("#prompts: Creating prompt with label=%s section=%s", payload.label, payload.section)
        section = (payload.section or "").strip()
        label = (payload.label or "").strip()
        body = (payload.body or "").strip()

        if not section or not label:
            raise HTTPException(
                status_code=400, detail="Section and label are required"
            )
        if not body:
            raise HTTPException(status_code=400, detail="Prompt body cannot be empty")
        prompt_list = normalize_prompt_list(body, payload.prompt_list)

        # Determine next version for this (section, label)
        max_ver_row = await session.execute(
            select(func.max(models.Prompt.version)).where(
                func.lower(models.Prompt.section) == section.lower(),
                func.lower(models.Prompt.label) == label.lower(),
            )
        )
        max_ver = max_ver_row.scalar() or 0
        next_version = int(max_ver) + 1

        if payload.is_default:
            await session.execute(
                update(models.Prompt)
                .where(models.Prompt.section == section)
                .values(is_default=False)
            )

        status = (payload.status or "Active").strip() or "Active"
        current_user = await get_user_from_claims(session, claims)
        current_user_id = current_user.id if current_user else None

        item = models.Prompt(
            section=section,
            label=label,
            body=body,
            prompt_list=prompt_list,
            market=(payload.market or None),
            property_type=None,
            tier=payload.tier,
            status=status,
            is_default=payload.is_default,
            created_by=current_user_id,
            modified_by=current_user_id,
        )
        # Set computed version
        try:
            item.version = next_version if next_version > 0 else 1
        except Exception:
            item.version = 1
        session.add(item)
        await session.commit()
        await session.refresh(item)
        email_map = await get_user_email_map(session, {item.created_by, item.modified_by})
        base = PromptOut.model_validate(item)
        return base.model_copy(
            update={
                "created_by_email": email_map.get(item.created_by or -1),
                "modified_by_email": email_map.get(item.modified_by or -1),
            }
        )
    except Exception as err:
        logger.error(
            "#prompts: Prompt creation failed. label=%s section=%s",
            getattr(payload, "label", None),
            getattr(payload, "section", None),
            exc_info=err,
        )
        await session.rollback()
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(
                session, err, conflict_message="Prompt already exists"
            )
        raise


@router.post("/bulk", response_model=list[PromptOut], status_code=201)
async def bulk_create_prompts(
    payload: list[PromptIn],
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
):
    items: list[models.Prompt] = []
    try:
        logger.info("#prompts: Creating bulk prompts. count=%s", len(payload))
        current_user = await get_user_from_claims(session, claims)
        current_user_id = current_user.id if current_user else None
        for p in payload:
            item = models.Prompt(**p.model_dump())
            # Property type is deprecated for prompts; ensure we don't persist it for new records.
            item.property_type = None
            item.created_by = current_user_id
            item.modified_by = current_user_id
            prompt_list = normalize_prompt_list(p.body, p.prompt_list)
            setattr(item, "prompt_list", prompt_list)
            session.add(item)
            items.append(item)
        await session.commit()
        out_items = []
        for item in items:
            await session.refresh(item)
        email_map = await get_user_email_map(
            session,
            {i.created_by for i in items} | {i.modified_by for i in items},
        )
        for item in items:
            base = PromptOut.model_validate(item)
            out_items.append(
                base.model_copy(
                    update={
                        "created_by_email": email_map.get(item.created_by or -1),
                        "modified_by_email": email_map.get(item.modified_by or -1),
                    }
                )
            )
        return out_items
    except Exception as err:
        logger.error("#prompts: Bulk prompts creation failed", exc_info=err)
        await session.rollback()
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(
                session, err, conflict_message="One or more prompts already exist"
            )
        raise


@router.get("/sections", response_model=list[str])
async def list_prompt_sections(session: AsyncSession = Depends(get_session)):
    logger.info("#prompt_section: Listing prompt sections.")
    res = await session.execute(
        select(models.TemplateSection.name)
        .distinct()
        .order_by(models.TemplateSection.name.asc())
    )
    names = [row[0] for row in res.all() if row[0]]
    return names


@router.get("/{prompt_id}", response_model=PromptOut)
async def get_prompt(prompt_id: int, session: AsyncSession = Depends(get_session)):
    logger.info("#prompts: Getting prompt with id=%s", prompt_id)
    item = await session.get(models.Prompt, prompt_id)
    if not item:
        raise HTTPException(status_code=404, detail="Prompt not found")
    email_map = await get_user_email_map(session, {item.created_by, item.modified_by})
    base = PromptOut.model_validate(item)
    return base.model_copy(
        update={
            "created_by_email": email_map.get(item.created_by or -1),
            "modified_by_email": email_map.get(item.modified_by or -1),
        }
    )


@router.patch("/{prompt_id}", response_model=PromptOut)
async def patch_prompt(
    prompt_id: int,
    payload: PromptUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
):
    logger.info("#prompts: Updating(patch) prompt with id=%s", prompt_id)
    item = await session.get(models.Prompt, prompt_id)
    if not item:
        raise HTTPException(status_code=404, detail="Prompt not found")
    try:
        current_user = await get_user_from_claims(session, claims)
        current_user_id = current_user.id if current_user else None
        data = payload.model_dump(exclude_unset=True)
        original_label = (item.label or "").strip()
        original_section = (item.section or "").strip()
        original_property_type = (item.property_type or "").strip()
        label_update_requested = False
        new_label_value: str | None = None

        if "section" in data:
            section = (data["section"] or "").strip()
            if not section:
                raise HTTPException(status_code=400, detail="Section is required")
            data["section"] = section

        if "label" in data:
            label = (data["label"] or "").strip()
            if not label:
                raise HTTPException(
                    status_code=400, detail="Prompt name cannot be empty"
                )
            exists = await session.execute(
                select(models.Prompt.id)
                .where(func.lower(models.Prompt.label) == label.lower())
                .where(models.Prompt.id != prompt_id)
            )
            if exists.scalar() is not None:
                raise HTTPException(
                    status_code=409, detail="Prompt name already exists"
                )
            data["label"] = label
            if label.lower() != original_label.lower():
                label_update_requested = True
                new_label_value = label

        if "body" in data:
            body = (data["body"] or "").strip()
            if not body:
                raise HTTPException(
                    status_code=400, detail="Prompt body cannot be empty"
                )
            data["body"] = body

        if data.get("is_default"):
            section_name = data.get("section") or item.section
            await session.execute(
                update(models.Prompt)
                .where(models.Prompt.section == section_name)
                .values(is_default=False)
            )

        if "status" in data:
            status = (data["status"] or "").strip() or "Active"
            data["status"] = status

        if "prompt_list" in data:
            data["prompt_list"] = data.get("prompt_list")

        for k, v in data.items():
            setattr(item, k, v)
        if current_user_id:
            item.modified_by = current_user_id
            logger.debug(
                "patch_prompt: Set modified_by=%s for prompt_id=%s (created_by=%s)",
                current_user_id, prompt_id, item.created_by
            )
            # Don't backfill created_by for historical prompts

        if label_update_requested and new_label_value:
            section_scope = (data.get("section") or original_section).strip()
            property_scope = (data.get("property_type") or original_property_type).strip()
            property_scope_normalized = property_scope.lower()
            stmt = (
                update(models.Prompt)
                .where(func.lower(models.Prompt.section) == section_scope.lower())
                .where(func.lower(models.Prompt.label) == original_label.lower())
                .where(models.Prompt.id != prompt_id)
                .values(label=new_label_value)
            )
            if property_scope:
                stmt = stmt.where(func.lower(models.Prompt.property_type) == property_scope_normalized)
            else:
                stmt = stmt.where(
                    func.coalesce(func.lower(models.Prompt.property_type), "") == ""
                )
            await session.execute(stmt)

        await session.commit()
        await session.refresh(item)
        email_map = await get_user_email_map(session, {item.created_by, item.modified_by})
        base = PromptOut.model_validate(item)
        return base.model_copy(
            update={
                "created_by_email": email_map.get(item.created_by or -1),
                "modified_by_email": email_map.get(item.modified_by or -1),
            }
        )
    except Exception as err:
        logger.error("#prompts: Prompt updation(patch) failed for id=%s", prompt_id, exc_info=err)
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise


@router.put("/{prompt_id}", response_model=PromptOut)
async def put_prompt(
    prompt_id: int,
    payload: PromptIn,
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
):
    logger.info("#prompts: Updating(put) prompt with id=%s", prompt_id)
    item = await session.get(models.Prompt, prompt_id)
    if not item:
        raise HTTPException(status_code=404, detail="Prompt not found")
    try:
        current_user = await get_user_from_claims(session, claims)
        current_user_id = current_user.id if current_user else None
        for k, v in payload.model_dump().items():
            setattr(item, k, v)
        if current_user_id:
            item.modified_by = current_user_id
            # Don't backfill created_by for historical prompts
        await session.commit()
        await session.refresh(item)
        email_map = await get_user_email_map(session, {item.created_by, item.modified_by})
        base = PromptOut.model_validate(item)
        return base.model_copy(
            update={
                "created_by_email": email_map.get(item.created_by or -1),
                "modified_by_email": email_map.get(item.modified_by or -1),
            }
        )
    except Exception as err:
        logger.error("#prompts: Prompt updation(put) failed for id=%s", prompt_id, exc_info=err)
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise


@router.delete("/{prompt_id}", status_code=204)
async def delete_prompt(prompt_id: int, session: AsyncSession = Depends(get_session)):
    logger.info("#prompts: Deleting prompt with id=%s", prompt_id)
    item = await session.get(models.Prompt, prompt_id)
    if not item:
        raise HTTPException(status_code=404, detail="Prompt not found")
    try:
        await session.delete(item)
        await session.commit()
        return None
    except Exception as err:
        logger.error("#prompts: Prompt deletion failed for id=%s", prompt_id, exc_info=err)
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise

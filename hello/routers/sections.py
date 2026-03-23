from __future__ import annotations

from typing import Sequence
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func, select, delete, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hello import models
from hello.schemas import (
    TemplateSectionOut,
    TemplateSectionListResponse,
    SectionUpdate,
    TemplateSectionElementIn,
)
from hello.services.database import get_session
from hello.services.error_handlers import handle_db_error
from hello.routers.templates import (
    _normalize_finalized_config,
    _normalize_attended_query,
    _propagate_section_to_reports,
)  # reuse normalization helper
from hello.utils.template_section_propagation import (
    DEFAULT_EXCLUDED_REPORT_STATUSES,
    remove_report_sections_for_template,
)
from hello.utils.auth_utils import get_user_from_claims, require_auth
from hello.utils.user_utils import get_user_email_map
# from hello.utils.template_registry import load_registry
from hello.ml.logger import GLOBAL_LOGGER as logger

router = APIRouter(dependencies=[Depends(require_auth)])


def _section_query_base() -> select:
    return (
        select(models.TemplateSection)
        .options(
            selectinload(models.TemplateSection.templates),
            selectinload(models.TemplateSection.elements),
        )
    )


async def _attach_prompt_metadata(
    session: AsyncSession, sections: list[models.TemplateSection]
) -> None:
    """Populate prompt_template_id/label/body/prompt_template for template sections."""
    if not sections:
        return
    labels_to_fetch: set[str] = set()
    bodies_to_fetch: set[str] = set()

    for sec in sections:
        lbl = getattr(sec, "prompt_template_label", None) or getattr(sec, "prompt_template", None)
        if isinstance(lbl, str) and lbl.strip():
            labels_to_fetch.add(lbl.strip().lower())
        body = getattr(sec, "prompt_template_body", None) or getattr(sec, "default_prompt", None)
        if isinstance(body, str) and body.strip():
            bodies_to_fetch.add(body.strip())

    prompt_by_label: dict[str, models.Prompt] = {}
    prompt_by_body: dict[str, models.Prompt] = {}

    if labels_to_fetch:
        prompt_rows = await session.execute(
            select(models.Prompt).where(func.lower(models.Prompt.label).in_(labels_to_fetch))
        )
        prompt_by_label = {p.label.strip().lower(): p for p in prompt_rows.scalars().all() if p.label}

    if bodies_to_fetch:
        prompt_rows = await session.execute(
            select(models.Prompt).where(models.Prompt.body.in_(bodies_to_fetch))
        )
        prompt_by_body = {p.body: p for p in prompt_rows.scalars().all() if p.body}

    for sec in sections:
        prompt = None
        lbl_key = None
        lbl_value = getattr(sec, "prompt_template_label", None) or getattr(sec, "prompt_template", None)
        if isinstance(lbl_value, str) and lbl_value.strip():
            lbl_key = lbl_value.strip().lower()
            prompt = prompt_by_label.get(lbl_key)
        if prompt is None:
            body_val = getattr(sec, "prompt_template_body", None) or getattr(sec, "default_prompt", None)
            if isinstance(body_val, str) and body_val.strip():
                prompt = prompt_by_body.get(body_val.strip())
        if prompt:
            setattr(sec, "prompt_template_id", prompt.id)
            setattr(sec, "prompt_template_label", prompt.label)
            setattr(sec, "prompt_template_body", prompt.body)
            if not getattr(sec, "prompt_template", None):
                setattr(sec, "prompt_template", prompt.label)
async def _section_with_emails(
    session: AsyncSession,
    section: models.TemplateSection,
) -> TemplateSectionOut:
    """Convert a TemplateSection model to TemplateSectionOut with user emails populated."""
    email_map = await get_user_email_map(
        session, {section.created_by, section.modified_by}
    )
    base = TemplateSectionOut.model_validate(section)
    return base.model_copy(
        update={
            "created_by_email": email_map.get(section.created_by or -1),
            "modified_by_email": email_map.get(section.modified_by or -1),
        }
    )


@router.get("/", response_model=TemplateSectionListResponse)
async def list_sections(
    session: AsyncSession = Depends(get_session),
    page: int = 1,
    page_size: int = 50,
    q: str | None = None,
    template_id: int | None = None,
    property_type: str | None = None,
    attended: bool | str | None = Query(default=None),
    sort_by: str | None = Query(default=None, description="Field to sort by"),
    sort_order: str | None = Query(default="desc", description="asc or desc"),
) -> TemplateSectionListResponse:
    page = 1 if page is None or page < 1 else int(page)
    page_size = 50 if page_size is None or page_size < 1 else min(int(page_size), 200)

    stmt = _section_query_base()
    count_stmt = select(func.count(func.distinct(models.TemplateSection.id))).select_from(
        models.TemplateSection
    )

    conds: list = []
    if q:
        like = f"%{q.strip().lower()}%"
        conds.append(
            func.lower(models.TemplateSection.name).like(like)
            | func.lower(models.TemplateSection.label).like(like)
        )
    if property_type:
        normalized = property_type.strip().lower()
        synonyms = {normalized}
        if "office" in normalized:
            synonyms.update({"office", "office figures"})
        if "industrial" in normalized:
            synonyms.update({"industrial", "industrial figures"})
        conds.append(
            func.lower(models.TemplateSection.property_type).in_(synonyms)
        )
    normalized_attended = _normalize_attended_query(attended)
    if normalized_attended is not None:
        target_modes = ("tier1", "attended") if normalized_attended else ("tier3", "unattended")
        mode_expr = func.lower(
            func.coalesce(
                models.TemplateSection.mode,
                models.TemplateSection.tier,
                models.TemplateSection.automation_mode,
            )
        )
        conds.append(mode_expr.in_(target_modes))
    if template_id is not None:
        stmt = stmt.join(
            models.template_section_association,
            models.template_section_association.c.section_id == models.TemplateSection.id,
        ).where(models.template_section_association.c.template_id == template_id)
        count_stmt = count_stmt.join(
            models.template_section_association,
            models.template_section_association.c.section_id == models.TemplateSection.id,
        ).where(models.template_section_association.c.template_id == template_id)
    if conds:
        cond_expr = and_(*conds)
        stmt = stmt.where(cond_expr)
        count_stmt = count_stmt.where(cond_expr)

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    sort_field = (sort_by or "").strip().lower()
    sort_dir = (sort_order or "desc").strip().lower()
    sort_desc = sort_dir != "asc"

    try:
        if sort_field:
            res = await session.execute(stmt.order_by(models.TemplateSection.id))
            sections: list[models.TemplateSection] = res.scalars().unique().all()
            total_count = len(sections)
        else:
            stmt = stmt.order_by(models.TemplateSection.created_at.desc())
            stmt = stmt.limit(page_size).offset(start_idx)
            count_res = await session.execute(count_stmt)
            total_count = count_res.scalar() or 0

            res = await session.execute(stmt)
            sections = res.scalars().unique().all()
    except SQLAlchemyError as err:
        msg = str(getattr(err, "orig", err)).lower()
        if (
            "relation \"template_sections\" does not exist" in msg
            or "undefinedtable" in msg
            or "template_section_association" in msg
        ):
            return TemplateSectionListResponse(totalCount=0, items=[])
        raise
    
    with session.no_autoflush:
        # Populate user emails
        user_ids = {s.created_by for s in sections} | {s.modified_by for s in sections}
        email_map = await get_user_email_map(session, user_ids)

        def _tier_value(section: models.TemplateSection) -> str:
            return (
                getattr(section, "mode", None)
                or getattr(section, "tier", None)
                or getattr(section, "automation_mode", None)
                or ""
            ).lower()

        def _template_name(section: models.TemplateSection) -> str:
            if getattr(section, "templates", None):
                tpl = section.templates[0]
                return (getattr(tpl, "name", "") or "").lower()
            return ""

        def _sort_key(section: models.TemplateSection):
            if sort_field == "name":
                return (section.name or "").lower()
            if sort_field in {"section_alias", "sectionname_alias"}:
                return (section.sectionname_alias or "").lower()
            if sort_field == "template":
                return _template_name(section)
            if sort_field == "template_count":
                return len(getattr(section, "templates", []) or [])
            if sort_field == "property_type":
                return (section.property_type or "").lower()
            if sort_field == "tier":
                return _tier_value(section)
            if sort_field == "created_at":
                return section.created_at or datetime.min
            if sort_field == "updated_at":
                return section.updated_at or datetime.min
            if sort_field == "created_by":
                return (email_map.get(section.created_by or -1, "") or "").lower()
            if sort_field == "updated_by":
                return (email_map.get(section.modified_by or -1, "") or "").lower()
            return section.created_at or datetime.min

        if sections and sort_field:
            sections.sort(key=_sort_key, reverse=sort_desc)

        paginated_sections = sections[start_idx:end_idx] if sort_field else sections

        for section in paginated_sections:
            if template_id is not None:
                setattr(section, "template_id", template_id)
            elif section.templates:
                setattr(section, "template_id", section.templates[0].id)
            if not getattr(section, "prompt_template", None):
                prompt_label = getattr(section, "prompt_template_label", None)
                prompt_body = getattr(section, "prompt_template_body", None)
                default_prompt = getattr(section, "default_prompt", None)
                adjust_prompt = getattr(section, "adjust_prompt", None)
                for fallback in (prompt_label, prompt_body, default_prompt, adjust_prompt):
                    if isinstance(fallback, str) and fallback.strip():
                        setattr(section, "prompt_template", fallback.strip())
                        break
        
        await _attach_prompt_metadata(session, list(paginated_sections))

        items: list[TemplateSectionOut] = []
        for section in paginated_sections:
            base = TemplateSectionOut.model_validate(section)
            items.append(
                base.model_copy(
                    update={
                        "created_by_email": email_map.get(section.created_by or -1),
                        "modified_by_email": email_map.get(section.modified_by or -1),
                    }
                )
            )
    return TemplateSectionListResponse(totalCount=total_count, items=items)


@router.post("/bulk-delete")
async def bulk_delete_sections(
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
            delete(models.TemplateSection).where(models.TemplateSection.id.in_(numeric_ids))
        )
        await session.commit()
        return {"deleted": result.rowcount or 0}
    except Exception as err:
        await session.rollback()
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise


@router.get("/{section_id}", response_model=TemplateSectionOut)
async def get_section(
    section_id: int, session: AsyncSession = Depends(get_session)
) -> TemplateSectionOut:
    res = await session.execute(
        _section_query_base().where(models.TemplateSection.id == section_id).limit(1)
    )
    section = res.scalars().first()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    with session.no_autoflush:
        if section.templates:
            setattr(section, "template_id", section.templates[0].id)
        if not getattr(section, "prompt_template", None):
            prompt_label = getattr(section, "prompt_template_label", None)
            prompt_body = getattr(section, "prompt_template_body", None)
            default_prompt = getattr(section, "default_prompt", None)
            adjust_prompt = getattr(section, "adjust_prompt", None)
            for fallback in (prompt_label, prompt_body, default_prompt, adjust_prompt):
                if isinstance(fallback, str) and fallback.strip():
                    setattr(section, "prompt_template", fallback.strip())
                    break
        await _attach_prompt_metadata(session, [section])
        enriched = await _section_with_emails(session, section)
        return enriched


@router.patch("/{section_id}", response_model=TemplateSectionOut)
async def patch_section(
    section_id: int,
    payload: SectionUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
) -> TemplateSectionOut:
    res = await session.execute(
        _section_query_base().where(models.TemplateSection.id == section_id).limit(1)
    )
    section = res.scalars().first()
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    current_user = await get_user_from_claims(session, claims)
    current_user_id = current_user.id if current_user else None
    data = payload.model_dump(exclude_unset=True)
    elements_data = data.pop("elements", None)
    if "sectionname_alias" in data:
        alias_val = (data["sectionname_alias"] or "").strip()
        if not alias_val:
            fallback_alias = (
                (data.get("name") or "").strip()
                or getattr(section, "sectionname_alias", "")
                or getattr(section, "name", "")
            )
            alias_val = fallback_alias.strip()
            if not alias_val:
                raise HTTPException(status_code=400, detail="Section alias is required")
        data["sectionname_alias"] = alias_val
    if "name" in data:
        trimmed = (data["name"] or "").strip()
        if not trimmed:
            raise HTTPException(status_code=400, detail="Section name is required")
        data["name"] = trimmed

    try:
        for key, value in data.items():
            setattr(section, key, value)

        if current_user_id:
            section.modified_by = current_user_id
            logger.debug(
                "patch_section: Set modified_by=%s for section_id=%s (created_by=%s)",
                current_user_id, section_id, section.created_by
            )
            # Don't backfill created_by for historical sections

        if elements_data is not None:
            await session.execute(
                delete(models.TemplateSectionElement).where(
                    models.TemplateSectionElement.section_id == section.id
                )
            )
            for idx, elem in enumerate(elements_data):
                elem_payload = (
                    elem.model_dump() if isinstance(elem, TemplateSectionElementIn) else dict(elem)
                )
                etype = elem_payload.get("element_type")
                cfg = elem_payload.get("config") or {}
                from types import SimpleNamespace

                pseudo_payload = SimpleNamespace(
                    property_type=data.get("property_type") or getattr(section, "property_type", None),
                    property_sub_type=data.get("property_sub_type") or getattr(section, "property_sub_type", None),
                    name=getattr(section, "name", None),
                    prompt_template_id=None,
                    prompt_template_label=None,
                    prompt_template_body=data.get("prompt_template") or getattr(section, "prompt_template", None),
                    prompt_template=data.get("prompt_template") or getattr(section, "prompt_template", None),
                    adjust_prompt=data.get("adjust_prompt") or getattr(section, "adjust_prompt", None),
                )
                normalized_cfg = _normalize_finalized_config(
                    str(etype or ""), cfg, pseudo_payload  # type: ignore[arg-type]
                )
                session.add(
                    models.TemplateSectionElement(
                        section_id=section.id,
                        element_type=etype,
                        display_order=elem_payload.get("display_order", idx),
                        config=normalized_cfg,
                    )
                )

        await session.commit()
        await session.refresh(section, attribute_names=["elements", "templates"])
        if section.templates:
            setattr(section, "template_id", section.templates[0].id)
        await _propagate_section_to_reports(
            session, getattr(section, "id", None), context="patch_section"
        )
        return await _section_with_emails(session, section)
    except Exception as err:
        await session.rollback()
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise


@router.delete("/{section_id}", status_code=204)
async def delete_section(
    section_id: int, session: AsyncSession = Depends(get_session)
) -> None:
    section = await session.get(models.TemplateSection, section_id)
    if not section:
        raise HTTPException(status_code=404, detail="Section not found")
    await session.refresh(section, attribute_names=["templates"])
    section_identifiers = [
        getattr(section, "name", None),
        getattr(section, "sectionname_alias", None),
    ]
    template_ids = [tpl.id for tpl in getattr(section, "templates", []) if tpl.id is not None]
    try:
        await session.delete(section)
        if template_ids:
            await remove_report_sections_for_template(
                session,
                template_ids,
                section_names=section_identifiers,
                exclude_reports_with_status=DEFAULT_EXCLUDED_REPORT_STATUSES,
            )
        await session.commit()
    except Exception as err:
        await session.rollback()
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise

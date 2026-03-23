from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy import select, delete, func, and_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from hello.services.database import get_session
from hello import models
from hello.schemas import (
    TemplateIn,
    TemplateOut,
    TemplateListItemOut,
    TemplateUpdate,
    TemplateDetailOut,
    TemplateSectionIn,
    TemplateSectionOut,
    TemplateSectionUpdate,
    TemplateListResponse,
    FinalizeSectionRequest,
    FinalizeSectionResponse,
    FinalizeSectionPayload,
)
from hello.services.error_handlers import handle_db_error
from hello.services.storage import (
    upload_template_file_to_s3,
    generate_presigned_url_for_key,
    S3UploadError,
)
from hello.services.config import settings
from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.utils.section_elements import normalize_prompt_list
from hello.utils.auth_utils import get_user_from_claims, require_auth
from hello.utils.user_utils import get_user_email_map
from hello.utils.template_section_propagation import (
    DEFAULT_EXCLUDED_REPORT_STATUSES,
    propagate_template_section_changes,
    remove_report_sections_for_template,
)

router = APIRouter(dependencies=[Depends(require_auth)])


async def _propagate_section_to_reports(
    session: AsyncSession,
    section_id: int | None,
    *,
    context: str,
) -> None:
    """Trigger propagation of a template section to all reports while swallowing failures."""
    if not section_id:
        return
    try:
        result = await propagate_template_section_changes(
            session,
            template_section_id=int(section_id),
            exclude_reports_with_status=DEFAULT_EXCLUDED_REPORT_STATUSES,
        )
        sections_updated = result.get("sections_updated", 0) or 0
        reports_affected = result.get("reports_affected", 0) or 0
        if sections_updated:
            logger.info(
                "#template_section: Propagated section_id=%s via %s (%s sections / %s reports)",
                section_id,
                context,
                sections_updated,
                reports_affected,
            )
    except Exception as err:
        logger.error(
            "#template_section: Failed to propagate section_id=%s via %s",
            section_id,
            context,
            exc_info=err,
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

ALLOWED_ELEMENT_TYPES = {"chart", "table", "commentary"}
INVALID_SECTION_CHARS = {"/", "\\"}
UNATTENDED_MODE_VALUES = {"tier3"}
ATTENDED_MODE_LABEL = "Attended"
UNATTENDED_MODE_LABEL = "Unattended"
_REPORT_PARAM_MULTI_VALUE_FIELDS = (
    "defined_markets",
    "vacancy_index",
    "submarket",
    "district",
)


def _ensure_valid_section_name(name: str, *, field: str = "Section name") -> None:
    if any(ch in INVALID_SECTION_CHARS for ch in name):
        raise HTTPException(
            status_code=422,
            detail=f"{field} cannot contain '/' or '\\\\'",
        )


def _extract_confidence_metric_details(
    config: dict | None, override: list[dict[str, Any]] | None = None
) -> list[dict[str, Any]] | None:
    """
    Normalize confidence_metric_details coming either from the payload or existing config.
    """
    if override is not None:
        return override
    if not config:
        return None
    details = config.get("confidence_metric_details")
    if isinstance(details, list):
        return details
    return None


def _normalize_mode_value(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    compact = normalized.replace(" ", "")
    if not compact:
        return None
    if normalized == "attended" or compact == "tier1":
        return "tier1"
    if normalized == "unattended" or compact == "tier3":
        return "tier3"
    return compact


def _normalize_report_params_list_field(
    report_params_data: dict[str, Any],
    field: str,
    *,
    force: bool = False,
) -> list[str]:
    """Normalize list-like selections under report parameters."""
    if field not in report_params_data and not force:
        return []
    raw_value = report_params_data.get(field, [])
    if isinstance(raw_value, str):
        candidates = [raw_value]
    elif isinstance(raw_value, (list, tuple, set)):
        candidates = list(raw_value)
    elif raw_value is None:
        candidates = []
    else:
        candidates = [raw_value]

    normalized: list[str] = []
    for item in candidates:
        if item is None:
            continue
        candidate = str(item).strip()
        if candidate:
            normalized.append(candidate)

    report_params_data[field] = normalized
    return normalized


def _is_unattended_mode(value: str | None) -> bool:
    norm = _normalize_mode_value(value)
    return norm in UNATTENDED_MODE_VALUES if norm else False


def _section_mode_value(section: Any) -> str | None:
    if isinstance(section, models.TemplateSection):
        return (
            section.mode
            or getattr(section, "automation_mode", None)
            or getattr(section, "tier", None)
        )
    data = _to_plain_dict(section)
    return (
        data.get("mode")
        or data.get("automation_mode")
        or data.get("tier")
        or ((data.get("report_parameters") or {}).get("automation_mode"))
    )


async def _template_with_emails(
    session: AsyncSession,
    template: models.Template,
    *,
    include_sections: bool = False,
    email_map: dict[int, str] | None = None,
) -> TemplateOut | TemplateListItemOut:
    sections: list[models.TemplateSection] = []
    if include_sections:
        sections = list(getattr(template, "sections", []) or [])

    user_ids = {template.created_by, template.modified_by}
    if sections:
        user_ids |= {s.created_by for s in sections} | {
            s.modified_by for s in sections
        }
    email_map = email_map or await get_user_email_map(
        session, {uid for uid in user_ids if uid is not None}
    )

    base = TemplateOut.model_validate(template)
    base_with_emails = base.model_copy(
        update={
            "created_by_email": email_map.get(template.created_by or -1),
            "modified_by_email": email_map.get(template.modified_by or -1),
        }
    )
    if not include_sections:
        return base_with_emails

    sections_payload: list[TemplateSectionOut] = []
    for section in sections:
        section_base = TemplateSectionOut.model_validate(section)
        sections_payload.append(
            section_base.model_copy(
                update={
                    "created_by_email": email_map.get(section.created_by or -1),
                    "modified_by_email": email_map.get(section.modified_by or -1),
                    "template_id": template.id,
                }
            )
        )

    return TemplateListItemOut(
        **base_with_emails.model_dump(),
        sections=sections_payload,
    )


def _apply_section_mode_metadata(
    section: Any,
    mode_value: str | None,
) -> None:
    """Populate section.mode / automation_mode defaults without overriding explicit values."""
    if not mode_value:
        return
    canonical = _normalize_mode_value(mode_value) or mode_value.strip().lower()
    friendly_label = UNATTENDED_MODE_LABEL if _is_unattended_mode(canonical) else ATTENDED_MODE_LABEL

    def _set_attr(obj: Any, attr: str, value: Any) -> None:
        if isinstance(obj, dict):
            if not obj.get(attr):
                obj[attr] = value
        else:
            if not getattr(obj, attr, None):
                setattr(obj, attr, value)

    _set_attr(section, "automation_mode", canonical)
    _set_attr(section, "tier", canonical)
    _set_attr(section, "mode", friendly_label)

    if isinstance(section, dict):
        report_params = section.get("report_parameters")
        if report_params is None:
            section["report_parameters"] = {"automation_mode": canonical}
        elif isinstance(report_params, dict) and not report_params.get("automation_mode"):
            report_params["automation_mode"] = canonical
    else:
        report_params = getattr(section, "report_parameters", None)
        if report_params is None:
            setattr(section, "report_parameters", {"automation_mode": canonical})
        elif isinstance(report_params, dict) and not report_params.get("automation_mode"):
            report_params["automation_mode"] = canonical


def _sync_section_mode_with_template(
    template: models.Template,
    section: Any,
    *,
    section_name: str | None = None,
    context: str = "template",
) -> None:
    """Ensure section metadata reflects the template's mode and enforce compatibility."""
    template_attended = bool(getattr(template, "attended", True))
    expected_mode = "tier1" if template_attended else "tier3"

    normalized_section_mode = _normalize_mode_value(_section_mode_value(section))
    if normalized_section_mode is None:
        _apply_section_mode_metadata(section, expected_mode)
    else:
        _apply_section_mode_metadata(section, normalized_section_mode)

    _ensure_section_allowed_for_template(
        template,
        section,
        section_name=section_name,
        context=context,
    )


async def _ensure_section_template_link(
    session: AsyncSession,
    template: models.Template,
    section: models.TemplateSection,
) -> None:
    """Attach template to section if missing, ensuring relationship is loaded."""
    if not template.id:
        await session.flush()
    if not section.id:
        await session.flush()
    await session.refresh(section, attribute_names=["templates"])
    for existing in section.templates:
        if existing.id == template.id:
            return
    section.templates.append(template)


def _ensure_section_allowed_for_template(
    template: models.Template,
    section: Any,
    *,
    section_name: str | None = None,
    context: str = "template",
) -> None:
    template_attended = bool(getattr(template, "attended", True))
    section_mode_value = _section_mode_value(section)
    if section_mode_value is None:
        return
    section_is_unattended = _is_unattended_mode(section_mode_value)
    template_expects_unattended = not template_attended

    if section_is_unattended != template_expects_unattended:
        template_label = "Unattended" if template_expects_unattended else "Attended"
        section_label = "unattended" if section_is_unattended else "attended"
        name = (
            section_name
            or getattr(section, "name", None)
            or _to_plain_dict(section).get("name")
            or "section"
        )
        template_name = getattr(template, "name", None) or f"template #{template.id}"
        raise HTTPException(
            status_code=400,
            detail=(
                f"Template '{template_name}' is configured for {template_label} mode "
                f"and cannot include {section_label} section '{name}'. "
                f"Please use a section configured for {template_label.lower()} mode instead."
            ),
        )


def _to_plain_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    model_dump = getattr(obj, "model_dump", None)
    if callable(model_dump):
        return model_dump()
    data = getattr(obj, "__dict__", None)
    return data if isinstance(data, dict) else {}


def _validate_template_sections(sections: list[TemplateSectionIn] | None) -> list[str]:
    errors: list[str] = []
    for i, raw_section in enumerate(sections or []):
        section = _to_plain_dict(raw_section)
        if not (section.get("name") or "").strip():
            errors.append(f"sections[{i}]: name is required")
        else:
            name_val = section.get("name", "")
            if any(ch in INVALID_SECTION_CHARS for ch in name_val):
                errors.append(
                    f"sections[{i}]: name cannot contain '/' or '\\\\'"
                )
        if not (section.get("sectionname_alias") or "").strip():
            errors.append(f"sections[{i}]: sectionname_alias is required")
        elements = section.get("elements") or []
        for j, raw_element in enumerate(elements):
            element = _to_plain_dict(raw_element)
            et = (element.get("element_type") or "").lower()
            if et not in ALLOWED_ELEMENT_TYPES:
                errors.append(
                    f"sections[{i}].elements[{j}]: invalid element_type '{element.get('element_type')}'"
                )
            display_order = element.get("display_order")
            if display_order is not None and display_order < 0:
                errors.append(f"sections[{i}].elements[{j}]: display_order must be >= 0")
            config = element.get("config")
            if config is not None and not isinstance(config, dict):
                errors.append(f"sections[{i}].elements[{j}]: config must be an object")
    return errors


async def _hydrate_existing_sections(
    session: AsyncSession, sections: list[TemplateSectionIn] | list[dict[str, Any]] | None
) -> list[models.TemplateSection]:
    """
    Resolve existing TemplateSection records for the provided payload.
    Raises HTTPException if any requested section cannot be matched.
    """
    if not sections:
        return []

    lookup_order: list[dict[str, Any]] = []
    requested_ids: set[int] = set()
    lookup_names: set[str] = set()

    for raw in sections:
        section = _to_plain_dict(raw)
        section_id = section.get("id") or section.get("section_id")
        try:
            section_id = int(section_id)
        except (TypeError, ValueError):
            section_id = None

        if section_id is not None:
            requested_ids.add(section_id)
            lookup_order.append({"type": "id", "value": section_id})
            continue

        name = (section.get("name") or "").strip()
        if not name:
            continue
        property_type = section.get("property_type")
        lookup_order.append(
            {"type": "name", "value": name, "property_type": property_type}
        )
        lookup_names.add(name.lower())

    if not lookup_order:
        return []

    fetched_by_id: dict[int, models.TemplateSection] = {}
    if requested_ids:
        id_result = await session.execute(
            select(models.TemplateSection).where(models.TemplateSection.id.in_(requested_ids))
        )
        fetched_by_id = {section.id: section for section in id_result.scalars().unique().all()}
        missing_ids = sorted(requested_ids.difference(fetched_by_id))
        if missing_ids:
            raise HTTPException(
                status_code=404,
                detail={
                    "message": "Template sections not found",
                    "sections": missing_ids,
                },
            )

    fetched_sections: list[models.TemplateSection] = []
    if lookup_names:
        result = await session.execute(
            select(models.TemplateSection)
            .where(func.lower(models.TemplateSection.name).in_(lookup_names))
            .order_by(models.TemplateSection.created_at.desc())
        )
        fetched_sections = list(result.scalars().unique().all())

    sections_by_name: dict[str, list[models.TemplateSection]] = {}
    for sec in fetched_sections:
        key = (sec.name or "").strip().lower()
        if not key:
            continue
        sections_by_name.setdefault(key, []).append(sec)

    missing: list[str] = []
    ordered_unique: list[models.TemplateSection] = []
    seen_ids: set[int] = set()

    for entry in lookup_order:
        match: models.TemplateSection | None = None
        if entry["type"] == "id":
            match = fetched_by_id.get(entry["value"])
        else:
            name = entry["value"]
            property_type = entry.get("property_type")
            key = name.lower()
            candidates = sections_by_name.get(key, [])
            if candidates and property_type:
                prop_lower = property_type.lower()
                for candidate in candidates:
                    if (candidate.property_type or "").lower() == prop_lower:
                        match = candidate
                        break
            if match is None and candidates:
                match = candidates[0]
            if match is None:
                missing.append(name)

        if match is None:
            continue
        if match.id in seen_ids:
            continue
        seen_ids.add(match.id)
        ordered_unique.append(match)

    if missing:
        raise HTTPException(
            status_code=404,
            detail={"message": "Template sections not found", "sections": missing},
        )

    return ordered_unique


async def _apply_section_links(
    session: AsyncSession,
    template: models.Template,
    sections: list[TemplateSectionIn] | list[dict[str, Any]] | None,
) -> None:
    """Synchronize template.section associations without creating new TemplateSection rows."""
    resolved_sections = await _hydrate_existing_sections(session, sections)
    for sec in resolved_sections:
        _sync_section_mode_with_template(
            template,
            sec,
            section_name=getattr(sec, "name", None),
            context="apply_section_links",
        )
    await session.refresh(template, attribute_names=["sections"])
    template.sections.clear()
    template.sections.extend(resolved_sections)
    await session.flush()


def _normalize_finalized_config(
    element_type: str, config: dict | None, payload: FinalizeSectionPayload
) -> dict:
    data = dict(config or {})
    data.setdefault("type", element_type)
    data.setdefault("property_type", getattr(payload, "property_type", None))
    data.setdefault("property_sub_type", getattr(payload, "property_sub_type", None))
    data.setdefault("section_name", getattr(payload, "name", None))
    if data.get("sql") is None:
        data["sql"] = ""
    if element_type == "chart":
        data["chart_type"] = data.get("chart_type") or "Line - Single axis"
    elif element_type == "table":
        data["include_totals"] = bool(data.get("include_totals"))
        data["highlight_changes"] = bool(data.get("highlight_changes"))
    elif element_type == "commentary":
        # Normalize multi-SQL support for commentary elements
        try:
            raw_list = data.get("sql_list")
            if isinstance(raw_list, list):
                sql_list = []
                for item in raw_list:
                    if isinstance(item, str):
                        t = item.strip()
                        if t:
                            sql_list.append(t)
                data["sql_list"] = sql_list
                # Keep legacy 'sql' in sync as a joined string for compatibility
                if sql_list and (not isinstance(data.get("sql"), str) or not data.get("sql").strip()):
                    data["sql"] = "\n\n-- Next query --\n\n".join(sql_list)
            else:
                # If only a single SQL is provided, mirror it into sql_list for consistency
                single = data.get("sql")
                if isinstance(single, str) and single.strip():
                    data["sql_list"] = [single]
        except Exception:
            # On any unexpected shape, fall back to single-SQL semantics
            single = data.get("sql")
            if isinstance(single, str) and single.strip():
                data["sql_list"] = [single]
        if (
            getattr(payload, "prompt_template_id", None) is not None
            and data.get("prompt_template_id") is None
        ):
            data["prompt_template_id"] = payload.prompt_template_id
        if (
            getattr(payload, "prompt_template_label", None) is not None
            and data.get("prompt_template_label") is None
        ):
            data["prompt_template_label"] = payload.prompt_template_label
        if (
            getattr(payload, "prompt_template_body", None) is not None
            and data.get("prompt_template_body") is None
        ):
            data["prompt_template_body"] = payload.prompt_template_body
        if (
            getattr(payload, "prompt_template", None) is not None
            and data.get("prompt_template") is None
        ):
            data["prompt_template"] = payload.prompt_template
            if (
                getattr(payload, "adjust_prompt", None) is not None
                and data.get("adjust_prompt") is None
            ):
                data["adjust_prompt"] = payload.adjust_prompt
        normalize_prompt_list(data)
    confidence_details = _extract_confidence_metric_details(
        data, getattr(payload, "confidence_metric_details", None)
    )
    if confidence_details is not None:
        data["confidence_metric_details"] = confidence_details
    return data


@router.get("/", response_model=TemplateListResponse)
async def list_templates(
    session: AsyncSession = Depends(get_session),
    page: int = 1,
    page_size: int = 20,
    q: str | None = None,
    base_type: str | None = None,
    is_default: bool | None = None,
    attended: bool | str | None = Query(default=None),
    ppt_status: str | None = None,
    user: str | None = None,
    include_sections: bool = Query(
        default=False,
        description="Include associated sections for each template",
    ),
    sort_by: str | None = Query(default=None, description="Field to sort by"),
    sort_order: str | None = Query(default="desc", description="asc or desc"),
):
    logger.info("#templates: listing templates")
    page = 1 if page is None or page < 1 else int(page)
    page_size = 20 if page_size is None or page_size < 1 else int(page_size)
    sort_field = (sort_by or "").strip().lower()
    sort_dir = (sort_order or "desc").strip().lower()
    sort_desc = sort_dir != "asc"

    user_filter_id: int | None = None
    if user:
        try:
            user_filter_id = int(user)
        except ValueError:
            lookup = await session.scalar(
                select(models.User.id).where(func.lower(models.User.email) == user.lower())
            )
            if lookup is None:
                return TemplateListResponse(totalCount=0, items=[])
            user_filter_id = lookup

    load_sections = include_sections or sort_field == "sections"
    base_stmt = select(models.Template)
    if load_sections:
        base_stmt = base_stmt.options(
            selectinload(models.Template.sections)
            .selectinload(models.TemplateSection.elements),
            selectinload(models.Template.sections).selectinload(
                models.TemplateSection.templates
            ),
        )
    conds = []
    if q:
        conds.append(models.Template.name.ilike(f"%{q}%"))
    if base_type:
        conds.append(func.lower(models.Template.base_type) == base_type.lower())
    if is_default is not None:
        conds.append(models.Template.is_default.is_(bool(is_default)))
    attended_filter = _normalize_attended_query(attended)
    if attended_filter is not None:
        conds.append(models.Template.attended.is_(attended_filter))
    if ppt_status:
        conds.append(func.lower(models.Template.ppt_status) == ppt_status.lower())
    if user_filter_id is not None:
        conds.append(models.Template.created_by == user_filter_id)
    if conds:
        base_stmt = base_stmt.where(and_(*conds))

    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size

    try:
        if sort_field:
            res = await session.execute(base_stmt.order_by(models.Template.id))
            templates_all = res.scalars().unique().all()
            total_count = len(templates_all)
        else:
            count_stmt = select(func.count()).select_from(base_stmt.subquery())
            count_res = await session.execute(count_stmt)
            total_count = count_res.scalar() or 0

            stmt = (
                base_stmt.order_by(models.Template.last_modified.desc())
                .limit(page_size)
                .offset(start_idx)
            )
            res = await session.execute(stmt)
            templates_all = res.scalars().unique().all()
    except SQLAlchemyError as e:
        msg = str(getattr(e, "orig", e)).lower()
        if "undefinedtable" in msg or 'relation "templates" does not exist' in msg:
            logger.warning("Templates table not found; returning empty response (DB uninitialized)")
            return TemplateListResponse(totalCount=0, items=[])
        raise

    # Prepare email map for sorting/output
    def _collect_user_ids(templates_list: list[models.Template]) -> set[int]:
        ids: set[int] = set()
        for tpl in templates_list:
            if tpl.created_by is not None:
                ids.add(tpl.created_by)
            if tpl.modified_by is not None:
                ids.add(tpl.modified_by)
            if include_sections and getattr(tpl, "sections", None):
                ids |= {s.created_by for s in tpl.sections if s.created_by is not None}
                ids |= {s.modified_by for s in tpl.sections if s.modified_by is not None}
        return ids

    email_map: dict[int, str] = {}
    if sort_field:
        email_map = await get_user_email_map(session, _collect_user_ids(list(templates_all)))

        def _sections_count(tpl: models.Template) -> int:
            return len(getattr(tpl, "sections", []) or [])

        def _sort_key(tpl: models.Template):
            if sort_field == "name":
                return (tpl.name or "").lower()
            if sort_field == "base_type":
                return (tpl.base_type or "").lower()
            if sort_field == "attended":
                return tpl.attended
            if sort_field == "is_default":
                return tpl.is_default
            if sort_field == "ppt_status":
                return (tpl.ppt_status or "").lower()
            if sort_field == "ppt_attached_time":
                return tpl.ppt_attached_time or datetime.min
            if sort_field == "created_at":
                return tpl.created_at or datetime.min
            if sort_field == "last_modified":
                return tpl.last_modified or datetime.min
            if sort_field == "created_by":
                return (email_map.get(tpl.created_by or -1, "") or "").lower()
            if sort_field == "updated_by":
                return (email_map.get(tpl.modified_by or -1, "") or "").lower()
            if sort_field == "sections":
                return _sections_count(tpl)
            return tpl.last_modified or tpl.created_at or datetime.min

        if templates_all:
            templates_all.sort(key=_sort_key, reverse=sort_desc)
        templates_page = templates_all[start_idx:end_idx]
    else:
        templates_page = templates_all
        email_map = await get_user_email_map(session, _collect_user_ids(list(templates_page)))

    items: list[TemplateListItemOut] = []
    for tpl in templates_page:
        base_model = await _template_with_emails(
            session,
            tpl,
            include_sections=include_sections,
            email_map=email_map,
        )
        if isinstance(base_model, TemplateListItemOut):
            items.append(base_model)
        else:
            items.append(TemplateListItemOut(**base_model.model_dump()))

    return TemplateListResponse(totalCount=total_count, items=items)


@router.post("/bulk-delete")
async def bulk_delete_templates(
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
            delete(models.Template).where(models.Template.id.in_(numeric_ids))
        )
        await session.commit()
        return {"deleted": result.rowcount or 0}
    except Exception as err:
        await session.rollback()
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise


@router.post("/", response_model=TemplateOut, status_code=201)
async def create_template(
    payload: TemplateIn,
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
):
    try:
        logger.info("#templates: Creating template with template_name=%s", payload.name)
        name = (payload.name or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="Template name is required")
        dup = await session.scalar(select(models.Template.id).where(func.lower(models.Template.name) == name.lower()))
        if dup:
            raise HTTPException(status_code=409, detail="Template with this name already exists")
        # Only validate inline sections when section_ids are not provided
        if not payload.section_ids:
            errs = _validate_template_sections(payload.sections)
            if errs:
                raise HTTPException(status_code=422, detail={"message": "Invalid template payload", "issues": errs})
        current_user = await get_user_from_claims(session, claims)
        current_user_id = current_user.id if current_user else None
        tpl = models.Template(
            name=name,
            base_type=payload.base_type,
            is_default=payload.is_default,
            attended=payload.attended,
            ppt_status=payload.ppt_status,
            ppt_attached_time=payload.ppt_attached_time,
            created_by=current_user_id,
            modified_by=current_user_id,
        )
        session.add(tpl)
        await session.flush()
        
        logger.debug(
            "create_template: Template created with audit tracking - id=%s, name=%s, "
            "created_by=%s, modified_by=%s",
            tpl.id, tpl.name, tpl.created_by, tpl.modified_by
        )
        
        if payload.section_ids:
            existing_sections = await session.execute(
                select(models.TemplateSection).where(models.TemplateSection.id.in_(payload.section_ids))
            )
            sections_list = existing_sections.scalars().unique().all()
            missing = set(payload.section_ids) - {s.id for s in sections_list}
            if missing:
                raise HTTPException(status_code=404, detail={"message": "Sections not found", "section_ids": list(missing)})
            # Insert directly into association table to avoid async lazy loads
            for sec in sections_list:
                stmt = (
                    pg_insert(models.template_section_association)
                    .values(template_id=tpl.id, section_id=sec.id)
                    .on_conflict_do_nothing()
                )
                await session.execute(stmt)
        elif payload.sections:
            for s in payload.sections:
                section_data = s.model_dump(exclude={"elements"})
                elements = s.elements or []
                trimmed_section_name = (section_data.get("name") or "").strip()
                alias_value = (section_data.get("sectionname_alias") or "").strip()
                if not trimmed_section_name:
                    raise HTTPException(status_code=422, detail="Section name is required")
                if not alias_value:
                    alias_value = trimmed_section_name
                section_data["name"] = trimmed_section_name
                section_data["sectionname_alias"] = alias_value
                sec = models.TemplateSection(**section_data)
                sec.created_by = current_user_id
                sec.modified_by = current_user_id
                _sync_section_mode_with_template(
                    tpl,
                    sec,
                    section_name=trimmed_section_name,
                    context="create_template",
                )
                sec.templates.append(tpl)
                session.add(sec)
                await session.flush()
                for idx, elem in enumerate(elements):
                    elem_data = (
                        elem.model_dump() if hasattr(elem, "model_dump") else dict(elem)
                    )
                    cfg = dict(elem_data.get("config") or {})
                    etype = (elem_data.get("element_type") or "").lower()
                    if etype == "commentary":
                        normalize_prompt_list(cfg)
                    else:
                        cfg.setdefault("prompt_list", [])
                    confidence_details = _extract_confidence_metric_details(
                        cfg, elem_data.get("confidence_metric_details")
                    )
                    if confidence_details is not None:
                        cfg["confidence_metric_details"] = confidence_details
                    elif "confidence_metric_details" in cfg:
                        details = cfg.get("confidence_metric_details")
                        if isinstance(details, list):
                            cfg["confidence_metric_details"] = details
                        else:
                            cfg.pop("confidence_metric_details", None)
                    session.add(
                        models.TemplateSectionElement(
                            section_id=sec.id,
                            element_type=elem_data.get("element_type"),
                            display_order=elem_data.get("display_order", idx),
                            config=cfg,
                        )
                    )
        await session.commit()
        await session.refresh(tpl)
        return await _template_with_emails(session, tpl)
    except Exception as err:
        logger.error(
            "#templates: Template creation failed for name=%s",
            getattr(payload, "name", None),
            exc_info=err,
        )
        await session.rollback()
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(
                session, err, conflict_message="Template with this name already exists"
            )
        raise


@router.get("/{template_id}", response_model=TemplateOut)
async def get_template(template_id: int, session: AsyncSession = Depends(get_session)):
    logger.info("#templates: Geting template_id=%s", template_id)
    tpl = await session.get(models.Template, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    return await _template_with_emails(session, tpl)


@router.patch("/{template_id}", response_model=TemplateOut)
async def patch_template(
    template_id: int,
    payload: TemplateUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
):
    logger.info("#templates: Updating(patch) template with template_id=%s", template_id)
    tpl = await session.get(models.Template, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    try:
        current_user = await get_user_from_claims(session, claims)
        current_user_id = current_user.id if current_user else None
        data = payload.model_dump(exclude_unset=True)
        sections = data.pop("sections", None)
        changed = False
        for k, v in data.items():
            setattr(tpl, k, v)
            changed = True
        if current_user_id:
            if tpl.modified_by != current_user_id:
                tpl.modified_by = current_user_id
                changed = True
            # Don't backfill created_by for historical templates
        if sections is not None:
            errs = _validate_template_sections(sections)
            if errs:
                raise HTTPException(status_code=422, detail={"message": "Invalid template sections", "issues": errs})
            await _apply_section_links(session, tpl, sections)
            changed = True
        if changed:
            tpl.last_modified = datetime.utcnow()
        await session.commit()
        await session.refresh(tpl)
        return await _template_with_emails(session, tpl)
    except Exception as err:
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise


@router.put("/{template_id}", response_model=TemplateOut)
async def put_template(
    template_id: int,
    payload: TemplateIn,
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
):
    logger.info("#templates: Updating(put) template with template_id=%s", template_id)
    tpl = await session.get(models.Template, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    try:
        current_user = await get_user_from_claims(session, claims)
        current_user_id = current_user.id if current_user else None
        name = (payload.name or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="Template name is required")
        dup = await session.scalar(
            select(models.Template.id)
            .where(func.lower(models.Template.name) == name.lower())
            .where(models.Template.id != template_id)
        )
        if dup:
            raise HTTPException(status_code=409, detail="Template with this name already exists")
        errs = _validate_template_sections(payload.sections)
        if errs:
            raise HTTPException(status_code=422, detail={"message": "Invalid template payload", "issues": errs})
        tpl.name = name
        tpl.base_type = payload.base_type
        tpl.is_default = payload.is_default
        tpl.attended = payload.attended
        tpl.ppt_status = payload.ppt_status
        tpl.ppt_attached_time = payload.ppt_attached_time
        if current_user_id:
            tpl.modified_by = current_user_id
            # Don't backfill created_by for historical templates
        await _apply_section_links(session, tpl, payload.sections)
        tpl.last_modified = datetime.utcnow()
        await session.commit()
        await session.refresh(tpl)
        return await _template_with_emails(session, tpl)
    except Exception as err:
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: int,
    session: AsyncSession = Depends(get_session),
    # _admin_user: models.User = Depends(require_admin_user),
):
    logger.info("#templates: Deleting template with template_id=%s", template_id)
    tpl = await session.get(models.Template, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    try:
        await session.delete(tpl)
        await remove_report_sections_for_template(
            session,
            [template_id],
            section_names=None,
            exclude_reports_with_status=DEFAULT_EXCLUDED_REPORT_STATUSES,
        )
        await session.commit()
        return None
    except Exception as err:
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        logger.error("#templates: Error occured while deleting template %s. Error: %s",
        template_id, err
        )
        raise


@router.post("/bulk-delete")
async def bulk_delete_templates(
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
            delete(models.Template).where(models.Template.id.in_(numeric_ids))
        )
        await session.commit()
        return {"deleted": result.rowcount or 0}
    except Exception as err:
        await session.rollback()
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise


@router.post("/{template_id}/ppt", response_model=TemplateOut)
async def upload_template_ppt(
    template_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
):
    logger.info("#templates: Uploading ppt for template_id=%s filename=%s", template_id, (file.filename or ""))
    tpl = await session.get(models.Template, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")

    if not settings.aws_bucket:
        raise HTTPException(status_code=500, detail="S3 bucket is not configured")

    filename = file.filename or ""
    suffix = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if suffix not in {"ppt", "pptx"}:
        raise HTTPException(
            status_code=400, detail="Only .ppt or .pptx files are supported"
        )

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    try:
        key = await upload_template_file_to_s3(content, filename)
        presigned = await generate_presigned_url_for_key(key)
        if not presigned:
            bucket = settings.aws_bucket or "DUMMY-BUCKET"
            presigned = f"s3://{bucket}/{key}"

        tpl.ppt_status = "Attached"
        tpl.ppt_s3_key = key
        tpl.ppt_url = presigned
        tpl.ppt_attached_time = datetime.utcnow()
        tpl.last_modified = datetime.utcnow()

        await session.commit()
        await session.refresh(tpl)
        return await _template_with_emails(session, tpl)
    except S3UploadError as err:
        await session.rollback()
        logger.warning(
            "#templates: Template PPT upload failed due to storage error",
            extra={"template_id": template_id, "upload_filename": filename},
        )
        raise HTTPException(
            status_code=502, detail=str(err) or "Failed to upload PPT"
        ) from err
    except Exception as err:
        await session.rollback()
        logger.exception(
            "#templates: Template PPT upload failed",
            extra={"template_id": template_id, "upload_filename": filename},
        )
        raise HTTPException(status_code=500, detail="Failed to upload PPT") from err


@router.get("/{template_id}/full", response_model=TemplateDetailOut)
async def get_template_full(
    template_id: int, session: AsyncSession = Depends(get_session)
):
    logger.info("#templates: Getting full template for template_id=%s", template_id)
    res = await session.execute(
        select(models.Template)
        .options(
            selectinload(models.Template.sections).selectinload(
                models.TemplateSection.elements
            ),
            selectinload(models.Template.sections).selectinload(
                models.TemplateSection.templates
            ),
        )
        .where(models.Template.id == template_id)
    )
    tpl = res.scalars().first()
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    for section in tpl.sections:
        setattr(section, "template_id", template_id)
    return await _template_with_emails(session, tpl, include_sections=True)


@router.post(
    "/finalize-section", response_model=FinalizeSectionResponse, status_code=201
)
async def finalize_section(
    payload: FinalizeSectionRequest,
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
):
    logger.info("#template_section: Finalizing section for template_id=%s name=%s", payload.template.existing_template_id, payload.section.name)
    current_user = await get_user_from_claims(session, claims)
    current_user_id = current_user.id if current_user else None
    section_payload = payload.section
    template_ref = payload.template

    if not section_payload.name or not section_payload.name.strip():
        raise HTTPException(status_code=400, detail="Section name is required")
    alias_raw = getattr(section_payload, "sectionname_alias", "")
    alias_trimmed = alias_raw.strip() if isinstance(alias_raw, str) else ""
    if not alias_trimmed:
        raise HTTPException(status_code=400, detail="Section alias is required")
    trimmed_section_name = section_payload.name.strip()
    _ensure_valid_section_name(trimmed_section_name)
    if not section_payload.elements:
        raise HTTPException(
            status_code=400, detail="At least one section element is required"
        )

    if template_ref.existing_template_id and template_ref.new_template_name:
        raise HTTPException(
            status_code=400,
            detail="Provide either an existing template id or a new template name, not both",
        )

    report_params_payload = getattr(payload, "report_parameters", None)
    report_params_data: dict[str, Any] = {}
    defined_markets: list[str] = []
    if report_params_payload:
        try:
            if hasattr(report_params_payload, "model_dump"):
                report_params_data = report_params_payload.model_dump()
            elif isinstance(report_params_payload, dict):
                report_params_data = dict(report_params_payload)
        except Exception:
            report_params_data = {}
    defined_markets = _normalize_report_params_list_field(
        report_params_data, "defined_markets", force=True
    )
    vacancy_values = _normalize_report_params_list_field(report_params_data, "vacancy_index")
    submarket_values = _normalize_report_params_list_field(report_params_data, "submarket")
    district_values = _normalize_report_params_list_field(report_params_data, "district")
    report_params_clean = {
        key: value
        for key, value in report_params_data.items()
        if value not in (None, "", [], {})
    }
    for multi_field in _REPORT_PARAM_MULTI_VALUE_FIELDS:
        if multi_field in report_params_data:
            report_params_clean[multi_field] = report_params_data[multi_field]

    def _clean(value: Any):
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    markets_value = ",".join(defined_markets) if defined_markets else None
    automation_mode_value = _clean(report_params_data.get("automation_mode"))
    division_value = _clean(report_params_data.get("division"))
    publishing_group_value = _clean(report_params_data.get("publishing_group"))
    quarter_value = _clean(report_params_data.get("quarter"))
    history_range_value = _clean(report_params_data.get("history_range"))
    absorption_calc_value = _clean(report_params_data.get("absorption_calculation"))
    total_vs_direct_value = _clean(
        report_params_data.get("total_vs_direct_absorption")
    )
    asking_freq_value = _clean(report_params_data.get("asking_rate_frequency"))
    asking_type_value = _clean(report_params_data.get("asking_rate_type"))
    property_sub_type_value = _clean(
        getattr(section_payload, "property_sub_type", None)
        or report_params_data.get("property_sub_type")
    )
    minimum_transaction_size_value = report_params_data.get(
        "minimum_transaction_size"
    )
    if minimum_transaction_size_value is not None:
        try:
            minimum_transaction_size_value = int(minimum_transaction_size_value)
        except (TypeError, ValueError):
            minimum_transaction_size_value = None
    use_auto_generated_text_value = report_params_data.get(
        "use_auto_generated_text"
    )
    if isinstance(use_auto_generated_text_value, str):
        use_auto_generated_text_value = (
            use_auto_generated_text_value.strip().lower() in {"1", "true", "yes"}
        )

    try:
        # Determine attended flag from automation_mode in the incoming payload.
        # Business rule: attended = True only when automation_mode == 'tier1'; else False.
        attended_flag: bool = False
        try:
            rp = getattr(payload, "report_parameters", None)
            mode_val = None
            if rp is not None:
                # rp may be a Pydantic model or dict
                if hasattr(rp, "model_dump"):
                    mode_val = rp.model_dump().get("automation_mode")
                elif isinstance(rp, dict):
                    mode_val = rp.get("automation_mode")
                else:
                    mode_val = getattr(rp, "automation_mode", None)
            s = (str(mode_val).strip().lower()) if mode_val is not None else ""
            # Accept a few common synonyms just in case
            if s in {"tier1", "tier 1", "attended"}:
                attended_flag = True
            elif s in {"tier3", "tier 3", "unattended"}:
                attended_flag = False
            else:
                # Default to False when not explicitly tier1
                attended_flag = False
        except Exception:
            attended_flag = False
        if template_ref.existing_template_id:
            template = await session.get(
                models.Template, template_ref.existing_template_id
            )
            if not template:
                raise HTTPException(status_code=404, detail="Template not found")
            if current_user_id:
                template.modified_by = current_user_id
                logger.debug(
                    "finalize_section: Set modified_by=%s for template_id=%s",
                    current_user_id, template.id
                )
                # Don't backfill created_by for historical templates
        else:
            new_name = (template_ref.new_template_name or "").strip()
            if not new_name:
                raise HTTPException(status_code=400, detail="Template name is required")
            existing = await session.execute(
                select(models.Template).where(
                    func.lower(models.Template.name) == new_name.lower()
                )
            )
            if existing.scalars().first():
                raise HTTPException(
                    status_code=409, detail="Template with this name already exists"
                )
            base_type = template_ref.base_type or (
                "Industrial Figures"
                if (section_payload.property_type or "").lower() == "industrial"
                else "Office Figures"
            )
            # template_attended = template_ref.attended
            # if template_attended is None:
            #     template_attended = not _is_unattended_mode(automation_mode_value)
            template = models.Template(
                name=new_name,
                base_type=base_type,
                is_default=template_ref.is_default,
                attended=attended_flag,
                ppt_status="Not Attached",
                ppt_attached_time=None,
                created_by=current_user_id,
                modified_by=current_user_id,
            )
            session.add(template)
            await session.flush()

        template.last_modified = datetime.utcnow()
        # Ensure template.attended reflects the automation mode of this finalize action
        try:
            template.attended = bool(attended_flag)
        except Exception:
            # If anything unexpected, default to False unless tier1 was explicit
            template.attended = bool(attended_flag)

        existing_section_id_param = getattr(section_payload, "existing_section_id", None)

        existing_global_section_id = await session.scalar(
            select(models.TemplateSection.id)
            .where(func.lower(models.TemplateSection.name) == trimmed_section_name.lower())
            .order_by(models.TemplateSection.created_at.desc())
            .limit(1)
        )
        if existing_global_section_id is not None:
            if existing_section_id_param is None:
                existing_section_obj = await session.get(models.TemplateSection, existing_global_section_id)
                if existing_section_obj:
                    await session.refresh(existing_section_obj, attribute_names=["templates"])
                    if existing_section_obj.templates:
                        raise HTTPException(
                            status_code=409,
                            detail=f"Section named '{trimmed_section_name}' already exists. Please choose another name.",
                        )
                    existing_section_id_param = existing_global_section_id
            elif existing_global_section_id != existing_section_id_param:
                existing_section_obj = await session.get(models.TemplateSection, existing_global_section_id)
                if existing_section_obj:
                    await session.refresh(existing_section_obj, attribute_names=["templates"])
                    if existing_section_obj.templates:
                        raise HTTPException(
                            status_code=409,
                            detail=f"Section named '{trimmed_section_name}' already exists. Please choose another name.",
                        )

        existing_section_id_on_template = await session.scalar(
            select(models.TemplateSection.id)
            .join(
                models.template_section_association,
                models.template_section_association.c.section_id == models.TemplateSection.id,
            )
            .where(models.template_section_association.c.template_id == template.id)
            .where(func.lower(models.TemplateSection.name) == trimmed_section_name.lower())
            .limit(1)
        )
        if existing_section_id_on_template is not None:
            if existing_section_id_param is None or existing_section_id_on_template != existing_section_id_param:
                raise HTTPException(
                    status_code=409,
                    detail=f"Section named '{trimmed_section_name}' already exists in template '{template.name}'",
                )

        prompt_template_text = (
            section_payload.prompt_template_body
            or section_payload.prompt_template
            or ""
        )
        adjust_prompt_text = section_payload.adjust_prompt or ""

        template_text_clean = prompt_template_text.strip()
        adjust_text_clean = adjust_prompt_text.strip()

        if template_text_clean and adjust_text_clean:
            default_prompt = f"{template_text_clean}\n\n{adjust_text_clean}"
        elif template_text_clean:
            default_prompt = template_text_clean
        elif adjust_text_clean:
            default_prompt = adjust_text_clean
        else:
            default_prompt = None

        # Try to capture commentary preview text from commentary element config (if provided by UI)
        commentary_preview: str | None = None
        try:
            for el in (section_payload.elements or []):
                if getattr(el, 'type', None) == 'commentary':
                    cfg = getattr(el, 'config', None) or {}
                    if isinstance(cfg, dict):
                        v = (
                            cfg.get('commentary_json')
                            or cfg.get('commentary')
                            or cfg.get('commentary_text')
                        )
                        if isinstance(v, str) and v.strip():
                            commentary_preview = v.strip()
                            break
        except Exception:
            commentary_preview = None

        if existing_section_id_param is not None:
            sec = await session.get(models.TemplateSection, existing_section_id_param)
            if not sec:
                raise HTTPException(status_code=404, detail="Template section not found")
            await session.refresh(sec, attribute_names=["templates", "elements"])
        else:
            existing_section_result = await session.execute(
                select(models.TemplateSection)
                .options(
                    selectinload(models.TemplateSection.templates),
                    selectinload(models.TemplateSection.elements),
                )
                .where(func.lower(models.TemplateSection.name) == trimmed_section_name.lower())
                .order_by(models.TemplateSection.created_at.desc())
                .limit(1)
            )
            sec = existing_section_result.scalars().first()

        if not sec:
            sec = models.TemplateSection(
                name=trimmed_section_name,
                sectionname_alias=alias_trimmed,
                label=section_payload.label,
                property_type=section_payload.property_type,
                property_sub_type=property_sub_type_value,
                tier=automation_mode_value,
                markets=markets_value,
                division=division_value,
                publishing_group=publishing_group_value,
                automation_mode=automation_mode_value,
                quarter=quarter_value,
                history_range=history_range_value,
                absorption_calculation=absorption_calc_value,
                total_vs_direct_absorption=total_vs_direct_value,
                asking_rate_frequency=asking_freq_value,
                asking_rate_type=asking_type_value,
                minimum_transaction_size=minimum_transaction_size_value,
                use_auto_generated_text=use_auto_generated_text_value,
                report_parameters=report_params_clean or None,
                vacancy_index=vacancy_values,
                submarket=submarket_values,
                district=district_values,
                default_prompt=default_prompt,
                prompt_template=(template_text_clean or None),
                adjust_prompt=(adjust_text_clean or None),
                commentary=commentary_preview,
                chart_config=None,
                table_config=None,
                slide_layout=None,
                created_by=current_user_id,
                modified_by=current_user_id,
            )
            session.add(sec)
            await session.flush()
        else:
            sec.name = trimmed_section_name
            sec.label = section_payload.label
            sec.property_type = section_payload.property_type
            sec.property_sub_type = property_sub_type_value
            sec.sectionname_alias = alias_trimmed
            sec.tier = automation_mode_value
            sec.markets = markets_value
            sec.division = division_value
            sec.publishing_group = publishing_group_value
            sec.automation_mode = automation_mode_value
            sec.quarter = quarter_value
            sec.history_range = history_range_value
            sec.absorption_calculation = absorption_calc_value
            sec.total_vs_direct_absorption = total_vs_direct_value
            sec.asking_rate_frequency = asking_freq_value
            sec.asking_rate_type = asking_type_value
            sec.minimum_transaction_size = minimum_transaction_size_value
            sec.use_auto_generated_text = use_auto_generated_text_value
            if current_user_id:
                sec.modified_by = current_user_id
                # Don't backfill created_by for historical sections
            sec.report_parameters = report_params_clean or None
            sec.vacancy_index = vacancy_values
            sec.submarket = submarket_values
            sec.district = district_values
            sec.default_prompt = default_prompt
            sec.prompt_template = template_text_clean or None
            sec.adjust_prompt = adjust_text_clean or None
            sec.commentary = commentary_preview
            sec.chart_config = None
            sec.table_config = None
            sec.slide_layout = None
            await session.execute(
                delete(models.TemplateSectionElement).where(
                    models.TemplateSectionElement.section_id == sec.id
                )
            )

        _sync_section_mode_with_template(
            template,
            sec,
            section_name=getattr(sec, "name", trimmed_section_name),
            context="finalize_section",
        )
        await _ensure_section_template_link(session, template, sec)

        chart_items: list[dict] = []
        table_items: list[dict] = []

        for idx, element in enumerate(section_payload.elements):
            normalized = _normalize_finalized_config(
                element.type, element.config, section_payload
            )
            normalized["section_name"] = trimmed_section_name
            normalized["section_alias"] = alias_trimmed
            if element.type == "chart":
                flipped_quarter = ""
                if isinstance(quarter_value, str) and quarter_value.strip():
                    flipped_quarter = " ".join(quarter_value.strip().split(" ")[::-1])
                source_text = normalized.get("chart_source")
                if not source_text:
                    source_text = "Source: CBRE Research"
                    if flipped_quarter:
                        source_text = f"{source_text}, {flipped_quarter}"
                chart_items.append(
                    {
                        "chart_type": normalized.get("chart_type"),
                        "sql": normalized.get("sql"),
                        # Additional metadata if provided by UI
                        "label": normalized.get("label"),
                        "name": normalized.get("name"),
                        "source": source_text,
                        "category": normalized.get("category"),
                    }
                )
            elif element.type == "table":
                table_items.append(
                    {
                        "include_totals": bool(normalized.get("include_totals")),
                        "highlight_changes": bool(normalized.get("highlight_changes")),
                        "sql": normalized.get("sql"),
                        # Extra table metadata if provided
                        "table_type": normalized.get("table_type"),
                        "label": normalized.get("label"),
                        "rows": normalized.get("rows"),
                        "columns": normalized.get("columns"),
                    }
                )
            display_order = element.order if element.order is not None else idx
            session.add(
                models.TemplateSectionElement(
                    section_id=sec.id,
                    element_type=element.type,
                    display_order=display_order,
                    config=normalized,
                )
            )

        if chart_items:
            sec.chart_config = {"items": chart_items, "count": len(chart_items)}
        if table_items:
            sec.table_config = {"items": table_items, "count": len(table_items)}

        await session.commit()

        template = await session.get(models.Template, template.id)
        section_row = await session.execute(
            select(models.TemplateSection)
            .options(
                selectinload(models.TemplateSection.elements),
                selectinload(models.TemplateSection.templates),
            )
            .where(models.TemplateSection.id == sec.id)
        )
        section_obj = section_row.scalars().first()
        if not template or not section_obj:
            raise HTTPException(status_code=500, detail="Failed to persist section")
        setattr(section_obj, "template_id", template.id)
        
        # Populate user emails for both template and section
        template_out = await _template_with_emails(session, template, include_sections=False)
        
        email_map = await get_user_email_map(
            session, {section_obj.created_by, section_obj.modified_by}
        )
        section_base = TemplateSectionOut.model_validate(section_obj)
        section_out = section_base.model_copy(
            update={
                "created_by_email": email_map.get(section_obj.created_by or -1),
                "modified_by_email": email_map.get(section_obj.modified_by or -1),
            }
        )

        await _propagate_section_to_reports(
            session,
            getattr(section_obj, "id", None),
            context="finalize_section",
        )
        return FinalizeSectionResponse(template=template_out, section=section_out)
    except HTTPException:
        await session.rollback()
        raise
    except Exception as err:
        await session.rollback()
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise


@router.patch("/finalize-section/{section_id}", response_model=FinalizeSectionResponse)
async def patch_finalize_section(
    section_id: int,
    payload: FinalizeSectionRequest,
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
):
    payload.section.existing_section_id = section_id
    return await finalize_section(payload, session, claims)


# -------------------------------
# Template Sections convenience CRUD
# -------------------------------


@router.get("/{template_id}/sections", response_model=list[TemplateSectionOut])
async def list_template_sections(
    template_id: int, session: AsyncSession = Depends(get_session)
):
    logger.info("#template_section: Listing all sections for template_id=%s", template_id)
    template = await session.get(models.Template, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    required_tier = "tier1" if template.attended else "tier3"
    tier_matches = ["tier1", "attended"] if template.attended else ["tier3", "unattended"]
    tier_column = func.lower(func.coalesce(models.TemplateSection.tier, required_tier))
    res = await session.execute(
        select(models.TemplateSection)
        .join(models.template_section_association)
        .options(
            selectinload(models.TemplateSection.elements),
            selectinload(models.TemplateSection.templates),
        )
        .where(models.template_section_association.c.template_id == template_id)
        .where(tier_column.in_(tier_matches))
        .order_by(models.TemplateSection.created_at.asc())
    )
    sections = list(res.scalars().unique().all())
    for section in sections:
        setattr(section, "template_id", template_id)
        if not getattr(section, "prompt_template", None):
            prompt_label = getattr(section, "prompt_template_label", None)
            prompt_body = getattr(section, "prompt_template_body", None)
            default_prompt = getattr(section, "default_prompt", None)
            adjust_prompt = getattr(section, "adjust_prompt", None)
            for fallback in (prompt_label, prompt_body, default_prompt, adjust_prompt):
                if isinstance(fallback, str) and fallback.strip():
                    setattr(section, "prompt_template", fallback.strip())
                    break
    await _attach_prompt_metadata(session, sections)
    return sections


@router.post(
    "/{template_id}/sections", response_model=TemplateSectionOut, status_code=201
)
async def create_template_section(
    template_id: int,
    payload: TemplateSectionIn,
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
):
    logger.info("#template_section: Creating template section for template_id=%s with name=%s", template_id, payload.name)
    tpl = await session.get(models.Template, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    try:
        current_user = await get_user_from_claims(session, claims)
        current_user_id = current_user.id if current_user else None
        if current_user_id:
            tpl.modified_by = current_user_id
            # Don't backfill created_by for historical templates
        trimmed_name = (payload.name or "").strip()
        if not trimmed_name:
            raise HTTPException(status_code=400, detail="Section name is required")
        _ensure_valid_section_name(trimmed_name)
        data = payload.model_dump(exclude={"elements"})
        data["name"] = trimmed_name
        alias_value = (data.get("sectionname_alias") or "").strip()
        if not alias_value:
            alias_value = trimmed_name
        data["sectionname_alias"] = alias_value
        report_params_payload = data.pop("report_parameters", None)
        report_params_data: dict[str, Any] = {}
        if report_params_payload:
            if hasattr(report_params_payload, "model_dump"):
                report_params_data = report_params_payload.model_dump()
            elif isinstance(report_params_payload, dict):
                report_params_data = dict(report_params_payload)
        defined_markets = _normalize_report_params_list_field(
            report_params_data, "defined_markets", force=True
        )
        vacancy_values = _normalize_report_params_list_field(report_params_data, "vacancy_index")
        submarket_values = _normalize_report_params_list_field(report_params_data, "submarket")
        district_values = _normalize_report_params_list_field(report_params_data, "district")
        report_params_clean = {
            key: value
            for key, value in report_params_data.items()
            if value not in (None, "", [], {})
        }
        for multi_field in _REPORT_PARAM_MULTI_VALUE_FIELDS:
            if multi_field in report_params_data:
                report_params_clean[multi_field] = report_params_data[multi_field]
        data["report_parameters"] = report_params_clean or None
        data["vacancy_index"] = vacancy_values
        data["submarket"] = submarket_values
        data["district"] = district_values
        if defined_markets:
            data["markets"] = ",".join(defined_markets)
        elif not data.get("markets"):
            data["markets"] = None
        if data.get("automation_mode") and not data.get("tier"):
            data["tier"] = data["automation_mode"]
        min_txn = data.get("minimum_transaction_size")
        if min_txn is not None:
            try:
                data["minimum_transaction_size"] = int(min_txn)
            except (TypeError, ValueError):
                data["minimum_transaction_size"] = None
        if "use_auto_generated_text" in data and isinstance(
            data["use_auto_generated_text"], str
        ):
            data["use_auto_generated_text"] = (
                data["use_auto_generated_text"].strip().lower() in {"1", "true", "yes"}
            )
        elements = payload.elements or []
        existing_section = await session.execute(
            select(models.TemplateSection)
            .options(
                selectinload(models.TemplateSection.templates),
                selectinload(models.TemplateSection.elements),
            )
            .where(func.lower(models.TemplateSection.name) == trimmed_name.lower())
            .order_by(models.TemplateSection.created_at.desc())
            .limit(1)
        )
        sec = existing_section.scalars().first()
        if sec:
            for key, value in data.items():
                setattr(sec, key, value)
            await session.execute(
                delete(models.TemplateSectionElement).where(
                    models.TemplateSectionElement.section_id == sec.id
                )
            )
            if current_user_id:
                sec.modified_by = current_user_id
                # Don't backfill created_by for historical sections
        else:
            sec = models.TemplateSection(
                **data, created_by=current_user_id, modified_by=current_user_id
            )
            session.add(sec)
            await session.flush()
        _sync_section_mode_with_template(
            tpl,
            sec,
            section_name=getattr(sec, "name", trimmed_name),
            context="create_template_section",
        )
        await _ensure_section_template_link(session, tpl, sec)
        for idx, elem in enumerate(elements):
            elem_data = elem.model_dump() if hasattr(elem, "model_dump") else dict(elem)
            etype = elem_data.get("element_type")
            cfg = elem_data.get("config") or {}
            from types import SimpleNamespace
            pseudo_payload = SimpleNamespace(
                property_type=getattr(sec, "property_type", None),
                name=getattr(sec, "name", None),
                prompt_template_id=None,
                prompt_template_label=None,
                prompt_template_body=None,
                prompt_template=None,
                adjust_prompt=None,
            )
            normalized_cfg = _normalize_finalized_config(str(etype or ""), cfg, pseudo_payload)
            confidence_details = _extract_confidence_metric_details(
                normalized_cfg, elem_data.get("confidence_metric_details")
            )
            if confidence_details is not None:
                normalized_cfg["confidence_metric_details"] = confidence_details
            elif "confidence_metric_details" in normalized_cfg and not isinstance(
                normalized_cfg.get("confidence_metric_details"), list
            ):
                normalized_cfg.pop("confidence_metric_details", None)
            session.add(
                models.TemplateSectionElement(
                    section_id=sec.id,
                    element_type=elem_data.get("element_type"),
                    display_order=elem_data.get("display_order", idx),
                    config=normalized_cfg,
                )
            )
        await session.commit()
        res = await session.execute(
            select(models.TemplateSection)
            .options(
                selectinload(models.TemplateSection.elements),
                selectinload(models.TemplateSection.templates),
            )
            .where(models.TemplateSection.id == sec.id)
        )
        section_obj = res.scalars().first()
        if section_obj:
            setattr(section_obj, "template_id", template_id)
            await _propagate_section_to_reports(
                session,
                getattr(section_obj, "id", None),
                context="create_template_section",
            )
        return section_obj
    except Exception as err:
        logger.error(
            "#template_section: Template creation failed for template_id=%s with name=%s",
            template_id,
            getattr(payload, "name", None),
            exc_info=err,
        )
        await session.rollback()
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise


@router.patch("/{template_id}/sections/{section_id}", response_model=TemplateSectionOut)
async def patch_template_section(
    template_id: int,
    section_id: int,
    payload: TemplateSectionUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
):
    logger.info("#template_section: Updating section for template_id=%s section_id=%s", template_id, section_id)
    res = await session.execute(
        select(models.TemplateSection)
        .options(
            selectinload(models.TemplateSection.elements),
            selectinload(models.TemplateSection.templates),
        )
        .join(models.template_section_association)
        .where(
            models.TemplateSection.id == section_id,
            models.template_section_association.c.template_id == template_id,
        )
        .limit(1)
    )
    sec = res.scalars().first()
    if not sec:
        raise HTTPException(status_code=404, detail="Section not found")
    tpl = next((t for t in getattr(sec, "templates", []) if t.id == template_id), None)
    if not tpl:
        tpl = await session.get(models.Template, template_id)
    if not tpl:
        raise HTTPException(status_code=404, detail="Template not found")
    try:
        current_user = await get_user_from_claims(session, claims)
        current_user_id = current_user.id if current_user else None
        data = payload.model_dump(exclude_unset=True)
        elements = data.pop("elements", None)
        if "sectionname_alias" in data:
            alias_val = (data["sectionname_alias"] or "").strip()
            if not alias_val:
                fallback_alias = (
                    (data.get("name") or "").strip()
                    or getattr(sec, "sectionname_alias", "")
                    or getattr(sec, "name", "")
                )
                alias_val = fallback_alias.strip()
                if not alias_val:
                    raise HTTPException(status_code=400, detail="Section alias is required")
            data["sectionname_alias"] = alias_val
        if "name" in data:
            new_name = (data["name"] or "").strip()
            if not new_name:
                raise HTTPException(status_code=400, detail="Section name is required")
            _ensure_valid_section_name(new_name)
            if new_name.lower() != sec.name.lower():
                dup_stmt = (
                    select(func.count())
                    .select_from(models.TemplateSection)
                    .where(
                        func.lower(models.TemplateSection.name) == new_name.lower(),
                        models.TemplateSection.id != sec.id,
                    )
                )
                dup_count = (await session.execute(dup_stmt)).scalar() or 0
                if dup_count:
                    raise HTTPException(
                        status_code=409,
                        detail="Section name already exists",
                    )
            data["name"] = new_name
        if "report_parameters" in data:
            report_params_payload = data["report_parameters"]
            report_params_data: dict[str, Any] = {}
            if report_params_payload:
                if hasattr(report_params_payload, "model_dump"):
                    report_params_data = report_params_payload.model_dump()
                elif isinstance(report_params_payload, dict):
                    report_params_data = dict(report_params_payload)
            defined_markets = _normalize_report_params_list_field(
                report_params_data, "defined_markets", force=True
            )
            vacancy_values = _normalize_report_params_list_field(report_params_data, "vacancy_index")
            submarket_values = _normalize_report_params_list_field(report_params_data, "submarket")
            district_values = _normalize_report_params_list_field(report_params_data, "district")
            report_params_clean = {
                key: value
                for key, value in report_params_data.items()
                if value not in (None, "", [], {})
            }
            for multi_field in _REPORT_PARAM_MULTI_VALUE_FIELDS:
                if multi_field in report_params_data:
                    report_params_clean[multi_field] = report_params_data[multi_field]
            data["report_parameters"] = report_params_clean or None
            data["vacancy_index"] = vacancy_values
            data["submarket"] = submarket_values
            data["district"] = district_values
            if defined_markets:
                data["markets"] = ",".join(defined_markets)
            elif "markets" not in data:
                data["markets"] = None
        if data.get("automation_mode") and "tier" not in data:
            data["tier"] = data["automation_mode"]
        if "minimum_transaction_size" in data:
            min_txn = data["minimum_transaction_size"]
            if min_txn is not None:
                try:
                    data["minimum_transaction_size"] = int(min_txn)
                except (TypeError, ValueError):
                    data["minimum_transaction_size"] = None
        if "use_auto_generated_text" in data and isinstance(
            data["use_auto_generated_text"], str
        ):
            data["use_auto_generated_text"] = (
                data["use_auto_generated_text"].strip().lower() in {"1", "true", "yes"}
            )
        for k, v in data.items():
            setattr(sec, k, v)
        _sync_section_mode_with_template(
            tpl, sec, section_name=data.get("name"), context="patch_template_section"
        )
        if current_user_id:
            sec.modified_by = current_user_id
            # Don't backfill created_by for historical sections
        if elements is not None:
            await session.execute(
                delete(models.TemplateSectionElement).where(
                    models.TemplateSectionElement.section_id == sec.id
                )
            )
            for idx, elem in enumerate(elements):
                elem_data = (
                    elem.model_dump() if hasattr(elem, "model_dump") else dict(elem)
                )
                # Normalize configs to keep commentary sql_list consistent
                etype = elem_data.get("element_type")
                cfg = elem_data.get("config") or {}
                from types import SimpleNamespace
                pseudo_payload = SimpleNamespace(
                    property_type=getattr(sec, "property_type", None),
                    name=getattr(sec, "name", None),
                    prompt_template_id=None,
                    prompt_template_label=None,
                    prompt_template_body=None,
                    prompt_template=None,
                    adjust_prompt=None,
                )
            normalized_cfg = _normalize_finalized_config(str(etype or ""), cfg, pseudo_payload)
            confidence_details = _extract_confidence_metric_details(
                normalized_cfg, elem_data.get("confidence_metric_details")
            )
            if confidence_details is not None:
                normalized_cfg["confidence_metric_details"] = confidence_details
            elif "confidence_metric_details" in normalized_cfg and not isinstance(
                normalized_cfg.get("confidence_metric_details"), list
            ):
                normalized_cfg.pop("confidence_metric_details", None)
                session.add(
                    models.TemplateSectionElement(
                        section_id=sec.id,
                        element_type=elem_data.get("element_type"),
                        display_order=elem_data.get("display_order", idx),
                        config=normalized_cfg,
                    )
                )
        _sync_section_mode_with_template(
            tpl,
            sec,
            section_name=getattr(sec, "name", None),
            context="patch_template_section",
        )
        await session.commit()
        res = await session.execute(
            select(models.TemplateSection)
            .options(
                selectinload(models.TemplateSection.elements),
                selectinload(models.TemplateSection.templates),
            )
            .where(models.TemplateSection.id == sec.id)
        )
        updated_sec = res.scalars().first()
        if updated_sec:
            setattr(updated_sec, "template_id", template_id)
            await _propagate_section_to_reports(
                session,
                getattr(updated_sec, "id", None),
                context="patch_template_section",
            )
        return updated_sec
    except Exception as err:
        logger.error(
            "#template_section: Section update failed for template_id=%s with section_id=%s",
            template_id,
            section_id,
            exc_info=err,
        )
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise


@router.delete("/{template_id}/sections/{section_id}", status_code=204)
async def delete_template_section(
    template_id: int, section_id: int, session: AsyncSession = Depends(get_session)
):
    logger.info("#template_section: Deleting section for template_id=%s with section_id=%s", template_id, section_id)
    res = await session.execute(
        select(models.TemplateSection)
        .options(
            selectinload(models.TemplateSection.templates),
        )
        .join(models.template_section_association)
        .where(
            models.TemplateSection.id == section_id,
            models.template_section_association.c.template_id == template_id,
        )
        .limit(1)
    )
    sec = res.scalars().first()
    if not sec:
        raise HTTPException(status_code=404, detail="Section not found")
    try:
        templates_to_remove = [tpl for tpl in sec.templates if tpl.id == template_id]
        for tpl in templates_to_remove:
            sec.templates.remove(tpl)
        section_identifiers = [
            getattr(sec, "name", None),
            getattr(sec, "sectionname_alias", None),
        ]
        await remove_report_sections_for_template(
            session,
            [template_id],
            section_names=section_identifiers,
            exclude_reports_with_status=DEFAULT_EXCLUDED_REPORT_STATUSES,
        )
        await session.commit()
        return None
    except Exception as err:
        logger.error(
            "#template_section: Delete section failed template_id=%s section_id=%s",
            template_id,
            section_id,
            exc_info=err,
        )
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise
@router.get("/sections/names", response_model=list[str])
async def list_all_section_names(session: AsyncSession = Depends(get_session)) -> list[str]:
    """Return distinct template section names across all templates.

    This is a lightweight endpoint for UIs (like Section Builder) that need
    a list of available section names without loading full section metadata.
    """
    logger.info("#template_section: Listing all section names")
    result = await session.execute(
        select(func.distinct(models.TemplateSection.name)).order_by(models.TemplateSection.name.asc())
    )
    names = [row[0] for row in result.fetchall() if row[0]]
    return names


@router.get("/sections/by-name", response_model=TemplateSectionOut)
async def get_section_by_name(name: str, session: AsyncSession = Depends(get_session)) -> TemplateSectionOut:
    """Return the most recently created TemplateSection and its elements for a given name.

    If multiple templates contain a section with the same name, the newest by created_at is returned.
    """
    logger.info("#template_section: Getting section with name=%s", name)
    res = await session.execute(
        select(models.TemplateSection)
        .options(
            selectinload(models.TemplateSection.elements),
            selectinload(models.TemplateSection.templates),
        )
        .where(func.lower(models.TemplateSection.name) == name.lower())
        .order_by(models.TemplateSection.created_at.desc())
        .limit(1)
    )
    sec = res.scalars().first()
    if not sec:
        raise HTTPException(status_code=404, detail="Section not found")
    if sec.templates:
        setattr(sec, "template_id", sec.templates[0].id)
    return sec
def _normalize_attended_query(value: bool | str | None) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "attended", "tier1"}:
        return True
    if normalized in {"0", "false", "no", "unattended", "tier3"}:
        return False
    return None

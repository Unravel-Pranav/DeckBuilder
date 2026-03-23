from __future__ import annotations

import asyncio
import copy
import json
import time
from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, joinedload, selectinload

from hello import models
from hello.ml.evaluation.metrics.confidence_metric import ConfidenceMetric
from hello.ml.utils.snowflake_exception import NoDataReturnedFromSnowflakeException
from hello.schemas import (
    ReportConfigIn,
    ReportCreate,
    ReportEvaluationOut,
    ReportHistoryListResponse,
    ReportListOut,
    ReportListResponse,
    ReportOut,
    ReportPatchIn,
    ReportRunOut,
    ReportRunsListResponse,
    ReportSaveIn,
    ReportSectionIn,
    SectionRequest,
)
from hello.services.agent_service import generate_section_llm
from hello.services.config import settings
from hello.services.database import get_session
from hello.services.error_handlers import handle_db_error
from hello.utils.sql_utils import render_sql_template
from hello.utils.section_elements import normalize_prompt_list
from hello.utils.utils import get_latest_complete_quarter
from hello.services.fetch_evaluations import CommentaryEvaluationService
from hello.services.multi_agent_workflow_service import workflow_service
from hello.services.notifications import (
    send_multi_market_report_notification,
    send_report_failure_notification,
    send_report_notification,
)
from hello.services.pipeline import generate_first_draft
from hello.services.prompt_saving import save_prompts
from hello.services.report_runner import generate_report_ppt_only, run_report_now
from hello.services.report_saving import save_final_report_to_s3
from hello.services.snowflake_service import fetch_snowflake_data
from hello.services.storage import generate_presigned_url_for_key
from hello.utils.user_utils import get_user_email_map
from hello.utils.auth_utils import (
    get_user_from_claims,
    require_auth,
    get_user_permissions_from_claims,
    build_permission_tree,
    user_can_access_report,
    extract_email_from_claims,
)
from hello.utils.commentary_utils.text_generator import generate_market_narrative
from hello.utils.report_utils import (
    fetch_multi_market_hero_fields,
    normalize_feedback_prompt_entries,
)
from hello.ml.logger import GLOBAL_LOGGER as logger


router = APIRouter(dependencies=[Depends(require_auth)])

env = settings.TESTING_ENV
ALLOWED_ELEMENT_TYPES = {"chart", "table", "commentary"}


async def _attach_prompt_metadata_for_report(
    session: AsyncSession, report: models.Report
) -> None:
    """Populate prompt template id/label/body for report and its sections."""
    if report is None:
        return
    ids_to_fetch: set[int] = set()
    labels_to_fetch: set[str] = set()
    bodies_to_fetch: set[str] = set()

    # Collect from report
    report_prompt_body = getattr(report, "prompt_template_body", None)
    if not getattr(report, "prompt_template", None):
        if report.prompt_template_id:
            ids_to_fetch.add(int(report.prompt_template_id))
        elif report.prompt_template_label:
            labels_to_fetch.add(report.prompt_template_label.strip().lower())
        elif report_prompt_body:
            bodies_to_fetch.add(report_prompt_body.strip())

    # Collect from sections
    for sec in getattr(report, "sections", []) or []:
        if getattr(sec, "prompt_template", None):
            continue
        if sec.prompt_template_id:
            ids_to_fetch.add(int(sec.prompt_template_id))
            continue
        if sec.prompt_template_label:
            labels_to_fetch.add(sec.prompt_template_label.strip().lower())
            bodies_to_fetch.add(sec.prompt_template_label.strip())
        if sec.prompt_template_body:
            bodies_to_fetch.add(sec.prompt_template_body.strip())

    prompt_by_id: dict[int, models.Prompt] = {}
    prompt_by_label: dict[str, models.Prompt] = {}
    prompt_by_body: dict[str, models.Prompt] = {}

    def _body_key(val: str | None) -> str | None:
        if not isinstance(val, str):
            return None
        stripped = val.strip()
        return stripped or None

    if ids_to_fetch:
        rows = await session.execute(
            select(models.Prompt).where(models.Prompt.id.in_(ids_to_fetch))
        )
        for p in rows.scalars().all():
            prompt_by_id[p.id] = p
            if p.label:
                prompt_by_label[p.label.strip().lower()] = p
            if p.body:
                key = _body_key(p.body)
                if key:
                    prompt_by_body[key] = p

    if labels_to_fetch:
        rows = await session.execute(
            select(models.Prompt).where(
                func.lower(models.Prompt.label).in_(labels_to_fetch)
            )
        )
        for p in rows.scalars().all():
            prompt_by_id[p.id] = p
            if p.label:
                prompt_by_label[p.label.strip().lower()] = p
            if p.body:
                key = _body_key(p.body)
                if key:
                    prompt_by_body[key] = p

    if bodies_to_fetch:
        rows = await session.execute(
            select(models.Prompt).where(models.Prompt.body.in_(bodies_to_fetch))
        )
        for p in rows.scalars().all():
            prompt_by_id[p.id] = p
            if p.label:
                prompt_by_label[p.label.strip().lower()] = p
            if p.body:
                key = _body_key(p.body)
                if key:
                    prompt_by_body[key] = p

    # Apply to report
    prompt = getattr(report, "prompt_template", None)
    if prompt is None:
        if report.prompt_template_id and report.prompt_template_id in prompt_by_id:
            prompt = prompt_by_id[report.prompt_template_id]
        elif report.prompt_template_label:
            prompt = prompt_by_label.get(report.prompt_template_label.strip().lower())
        elif report_prompt_body:
            prompt = prompt_by_body.get(report_prompt_body.strip())
    if prompt:
        report.prompt_template_id = prompt.id
        report.prompt_template_label = prompt.label
        if hasattr(report, "prompt_template_body"):
            report.prompt_template_body = prompt.body

    # Apply to sections
    for sec in getattr(report, "sections", []) or []:
        prompt = getattr(sec, "prompt_template", None)
        if prompt is None:
            if sec.prompt_template_id and sec.prompt_template_id in prompt_by_id:
                prompt = prompt_by_id[sec.prompt_template_id]
            elif sec.prompt_template_label:
                prompt = prompt_by_label.get(sec.prompt_template_label.strip().lower())
                if prompt is None:
                    # Fallback in case label actually holds the prompt body
                    key = _body_key(sec.prompt_template_label)
                    if key:
                        prompt = prompt_by_body.get(key)
            elif sec.prompt_template_body:
                key = _body_key(sec.prompt_template_body)
                prompt = prompt_by_body.get(key) if key else None
        if prompt:
            sec.prompt_template_id = prompt.id
            sec.prompt_template_label = prompt.label
            sec.prompt_template_body = prompt.body


async def _report_with_emails(
    session: AsyncSession, report: models.Report
) -> ReportOut:
    email_map = await get_user_email_map(
        session, {report.created_by, report.modified_by}
    )
    base = ReportOut.model_validate(report)
    return base.model_copy(
        update={
            "created_by_email": email_map.get(report.created_by or -1),
            "modified_by_email": email_map.get(report.modified_by or -1),
        }
    )


def _normalize_divisions(value: list[str] | str | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(dict.fromkeys(value or []))


def _current_user_email(
    claims: dict | None, user: models.User | None = None
) -> str | None:
    """Prefer DB user email, fallback to claims."""
    if user and getattr(user, "email", None):
        return user.email
    return extract_email_from_claims(claims)


def _build_report_meta(report: models.Report) -> dict:
    feedback_records: list[dict[str, str]] = []
    try:
        for section in getattr(report, "sections", []) or []:
            for element in getattr(section, "elements", []) or []:
                entries = normalize_feedback_prompt_entries(
                    getattr(element, "feedback_prompt", None)
                )
                for entry in entries:
                    enriched = {
                        "feedback": entry.get("feedback", ""),
                        "commentary": entry.get("commentary", ""),
                        "timestamp": entry.get("timestamp"),
                    }
                    if getattr(section, "id", None) is not None:
                        enriched["section_id"] = section.id
                    if getattr(section, "key", None):
                        enriched["section_key"] = section.key
                    if getattr(element, "id", None) is not None:
                        enriched["element_id"] = element.id
                    if getattr(element, "element_type", None):
                        enriched["element_type"] = element.element_type
                    feedback_records.append(enriched)
    except Exception:
        feedback_records = []

    # If run_quarter is "dynamic", calculate the latest complete quarter
    # Otherwise, use the quarter value from the report (sent by frontend)
    run_quarter = report.run_quarter
    if run_quarter and run_quarter.lower() == "dynamic":
        actual_quarter = get_latest_complete_quarter()
    else:
        actual_quarter = report.quarter

    return {
        "report_id": report.id,
        "name": report.name,
        "template_name": report.template_name,
        "report_type": report.report_type,
        "division": report.division,
        "publishing_group": report.publishing_group,
        "property_type": report.property_type,
        "property_sub_type": report.property_sub_type,
        "defined_markets": list(report.defined_markets or []),
        "vacancy_index": list(getattr(report, "vacancy_index", None) or []),
        "submarket": list(getattr(report, "submarket", None) or []),
        "district": list(getattr(report, "district", None) or []),
        "feedback_prompt": feedback_records,
        "hero_fields": report.hero_fields or {},
        "quarter": actual_quarter,
        "run_quarter": report.run_quarter,
        "history_range": report.history_range,
        "absorption_calculation": report.absorption_calculation,
        "total_vs_direct_absorption": report.total_vs_direct_absorption,
        "asking_rate_frequency": report.asking_rate_frequency,
        "asking_rate_type": report.asking_rate_type,
        "minimum_transaction_size": report.minimum_transaction_size,
        "use_auto_generated_text": report.use_auto_generated_text,
        "automation_mode": report.automation_mode,
        "status": report.status,
    }


async def _validate_report_payload(
    session: AsyncSession, payload: ReportCreate
) -> None:
    errors: list[str] = []

    # Template must exist if an id is provided
    if payload.template_id is not None:
        tpl = await session.get(models.Template, payload.template_id)
        if tpl is None:
            errors.append(f"template_id {payload.template_id} not found")

    # Sections
    sections = list(payload.sections or [])
    if not sections:
        errors.append("at least one section is required")
    else:
        selected = [s for s in sections if getattr(s, "selected", True)]
        if not selected:
            errors.append("at least one section must be selected")

        for idx, s in enumerate(selected):
            if not (s.name or s.key):
                errors.append(f"sections[{idx}]: name or key is required")
            if not isinstance(s.elements, list) or len(s.elements) == 0:
                errors.append(f"sections[{idx}]: at least one element is required")
                continue
            for j, e in enumerate(s.elements):
                et = (e.element_type or "").lower()
                if et not in ALLOWED_ELEMENT_TYPES:
                    errors.append(
                        f"sections[{idx}].elements[{j}]: invalid element_type '{e.element_type}'"
                    )
                if e.display_order is not None and getattr(e, "display_order") < 0:
                    errors.append(
                        f"sections[{idx}].elements[{j}]: display_order must be >= 0"
                    )
                if e.config is not None and not isinstance(e.config, dict):
                    errors.append(
                        f"sections[{idx}].elements[{j}]: config must be an object"
                    )

    # Markets uniqueness is enforced later; ensure no blanks
    if any((m or "").strip() == "" for m in (payload.defined_markets or [])):
        errors.append("defined_markets contains empty values")

    if errors:
        # Return all issues together
        raise HTTPException(
            status_code=422,
            detail={"message": "Invalid report payload", "issues": errors},
        )


async def _persist_report_sections(
    session: AsyncSession,
    report: models.Report,
    sections_payload: list[ReportSectionIn] | None,
    *,
    report_meta: dict | None = None,
    embed_meta: bool = False,
    existing_sections: list[models.ReportSection] | None = None,
) -> set[int]:
    payload_list = sections_payload or []
    selected_sections = [sec for sec in payload_list if getattr(sec, "selected", True)]
    if not selected_sections:
        return set()

    existing_sections_list = list(existing_sections or [])
    existing_by_id: dict[int, models.ReportSection] = {
        int(sec.id): sec
        for sec in existing_sections_list
        if getattr(sec, "id", None) is not None
    }
    key_index: dict[str, list[models.ReportSection]] = defaultdict(list)
    for sec in existing_by_id.values():
        key_val = getattr(sec, "key", None)
        if key_val:
            key_index[key_val].append(sec)

    preserved_ids: set[int] = set()
    new_sections: list[models.ReportSection] = []

    template_alias_index: dict[int, str] = {}
    template_alias_by_name: dict[str, str] = {}
    template_id = getattr(report, "template_id", None)
    if template_id:
        alias_rows = await session.execute(
            select(
                models.TemplateSection.id,
                models.TemplateSection.name,
                models.TemplateSection.sectionname_alias,
            )
            .join(models.template_section_association)
            .where(models.template_section_association.c.template_id == template_id)
        )
        for row_id, row_name, alias in alias_rows:
            alias_str = (alias or "").strip()
            template_alias_index[int(row_id)] = alias_str
            if isinstance(row_name, str) and row_name.strip():
                template_alias_by_name[row_name.strip().lower()] = alias_str
    else:
        template_section_ids = {
            int(getattr(sec, "template_section_id"))
            for sec in selected_sections
            if getattr(sec, "template_section_id", None) is not None
        }
        if template_section_ids:
            alias_rows = await session.execute(
                select(
                    models.TemplateSection.id, models.TemplateSection.sectionname_alias
                ).where(models.TemplateSection.id.in_(template_section_ids))
            )
            for row_id, alias in alias_rows:
                template_alias_index[int(row_id)] = (alias or "").strip()

    for idx, section_payload in enumerate(selected_sections):
        raw_alias = getattr(section_payload, "sectionname_alias", None)
        alias_value = ""
        if isinstance(raw_alias, str) and raw_alias.strip():
            alias_value = raw_alias.strip()
        template_alias_value = ""
        template_section_key = getattr(section_payload, "template_section_id", None)
        if template_section_key is not None:
            template_alias_value = template_alias_index.get(
                int(template_section_key), ""
            ).strip()
        if not alias_value and template_alias_value:
            alias_value = template_alias_value
        if not alias_value:
            for candidate in (
                getattr(section_payload, "name", None),
                getattr(section_payload, "key", None),
            ):
                if isinstance(candidate, str) and candidate.strip():
                    alias_value = candidate.strip()
                    break
        name_candidate = getattr(section_payload, "name", None)
        if (
            template_alias_value
            and isinstance(name_candidate, str)
            and name_candidate.strip()
            and alias_value.strip().lower() == name_candidate.strip().lower()
            and template_alias_value.lower() != name_candidate.strip().lower()
        ):
            alias_value = template_alias_value
        if isinstance(name_candidate, str) and name_candidate.strip():
            alias_by_name = template_alias_by_name.get(name_candidate.strip().lower())
            if alias_by_name:
                if not alias_value.strip():
                    alias_value = alias_by_name
                elif (
                    alias_value.strip().lower() == name_candidate.strip().lower()
                    and alias_by_name.lower() != name_candidate.strip().lower()
                ):
                    alias_value = alias_by_name
        if not alias_value:
            alias_value = f"section-{idx + 1}"

        element_models: list[models.ReportSectionElement] = []
        section_layout_preference = getattr(section_payload, "layout_preference", None)

        for element_idx, element_payload in enumerate(section_payload.elements):
            cfg = dict(element_payload.config or {})
            if getattr(element_payload, "element_type", None) == "chart":
                # Store only the BASE source (user-provided or default) without quarter
                # The quarter will be added dynamically in report_runner.py when report is run
                user_source = cfg.get("chart_source") or cfg.get("source")
                if user_source:
                    cfg["chart_source"] = user_source
                else:
                    cfg["chart_source"] = "Source: CBRE Research"
            try:
                if (
                    getattr(section_payload, "slide_number", None) is not None
                    and "slide_number" not in cfg
                ):
                    cfg["slide_number"] = int(getattr(section_payload, "slide_number"))
            except Exception:
                pass
            text_val = element_payload.prompt_text
            etype = (element_payload.element_type or "").lower()
            feedback_entries = normalize_feedback_prompt_entries(
                getattr(element_payload, "feedback_prompt", None)
            )
            if etype == "commentary":
                commentary_json = None
                section_commentary_value = None
                if isinstance(text_val, str) and text_val.strip():
                    section_commentary_value = text_val.strip()
                cj = cfg.get("commentary_json") if isinstance(cfg, dict) else None
                if isinstance(cj, str) and cj.strip():
                    commentary_json = cj.strip()
                    if not section_commentary_value:
                        section_commentary_value = commentary_json
                if commentary_json is not None:
                    cfg["commentary_json"] = commentary_json
                normalize_prompt_list(cfg)
            else:
                if isinstance(cfg, dict):
                    prompt_list_value = cfg.get("prompt_list")
                    if not isinstance(prompt_list_value, list):
                        cfg["prompt_list"] = []

            element_models.append(
                models.ReportSectionElement(
                    element_type=element_payload.element_type,
                    label=element_payload.label,
                    selected=element_payload.selected,
                    display_order=element_payload.display_order or element_idx,
                    config=cfg,
                    prompt_text=text_val,
                    section_commentary=section_commentary_value
                    if etype == "commentary"
                    else None,
                    feedback_prompt=feedback_entries,
                )
            )

        matched_section: models.ReportSection | None = None
        payload_section_id = getattr(section_payload, "report_section_id", None)
        if payload_section_id is not None:
            matched_section = existing_by_id.pop(int(payload_section_id), None)
        if matched_section is None:
            key_lookup = section_payload.key or section_payload.name
            if key_lookup:
                candidates = key_index.get(key_lookup) or []
                if candidates:
                    matched_section = candidates.pop(0)
                    if getattr(matched_section, "id", None) is not None:
                        existing_by_id.pop(int(matched_section.id), None)

        if matched_section is not None:
            preserved_ids.add(matched_section.id)
            prev_key = getattr(matched_section, "key", None)
            if prev_key:
                lst = key_index.get(prev_key)
                if lst and matched_section in lst:
                    lst.remove(matched_section)

            matched_section.key = section_payload.key
            matched_section.name = section_payload.name
            matched_section.sectionname_alias = alias_value
            matched_section.display_order = section_payload.display_order or idx
            matched_section.selected = getattr(section_payload, "selected", True)
            matched_section.prompt_template_id = section_payload.prompt_template_id
            matched_section.prompt_template_label = (
                section_payload.prompt_template_label
            )
            matched_section.prompt_template_body = section_payload.prompt_template_body
            if section_layout_preference is not None:
                matched_section.layout_preference = section_layout_preference
            matched_section.report = report
            matched_section.elements.clear()
            matched_section.elements.extend(element_models)
            for elem in matched_section.elements:
                elem.section = matched_section

            if (
                not matched_section.prompt_template_id
                and matched_section.prompt_template_label
            ):
                prompt_match = await session.scalar(
                    select(models.Prompt)
                    .where(models.Prompt.label == matched_section.prompt_template_label)
                    .limit(1)
                )
                if prompt_match:
                    matched_section.prompt_template_id = prompt_match.id
                    matched_section.prompt_template_label = prompt_match.label
            continue

        section = models.ReportSection(
            report=report,
            key=section_payload.key,
            name=section_payload.name,
            sectionname_alias=alias_value,
            display_order=section_payload.display_order or idx,
            selected=True,
            prompt_template_id=section_payload.prompt_template_id,
            prompt_template_label=section_payload.prompt_template_label,
            prompt_template_body=section_payload.prompt_template_body,
            layout_preference=section_layout_preference,
            elements=element_models,
        )

        session.add(section)
        new_sections.append(section)

        if not section.prompt_template_id and section.prompt_template_label:
            prompt_match = await session.scalar(
                select(models.Prompt)
                .where(models.Prompt.label == section.prompt_template_label)
                .limit(1)
            )
            if prompt_match:
                section.prompt_template_id = prompt_match.id
                section.prompt_template_label = prompt_match.label

    if new_sections:
        await session.flush()
        for section in new_sections:
            if getattr(section, "id", None) is not None:
                preserved_ids.add(section.id)

    return preserved_ids


async def _fetch_report_with_sections(
    session: AsyncSession, report_id: int
) -> models.Report | None:
    # Use eager joined loading across both relationships to ensure
    # the entire graph is fully loaded in a single context and avoid
    # any lazy IO during Pydantic serialization.
    result = await session.execute(
        select(models.Report)
        .options(
            joinedload(models.Report.prompt_template),
            joinedload(models.Report.sections).joinedload(
                models.ReportSection.elements
            ),
            joinedload(models.Report.sections).joinedload(
                models.ReportSection.prompt_template
            ),
        )
        .where(models.Report.id == report_id)
    )
    return result.scalars().unique().one_or_none()


def _normalize_mode(value: str | None) -> str:
    s = (value or "").strip().lower()
    if s in {"tier1", "tier 1", "attended"}:
        return "tier1"
    if s in {"tier3", "tier 3", "unattended"}:
        return "tier3"
    return "tier1"


def _normalize_string_list(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    if not values:
        return normalized
    for value in values:
        if value is None:
            continue
        candidate = str(value).strip()
        if not candidate:
            continue
        if candidate in seen:
            continue
        normalized.append(candidate)
        seen.add(candidate)
    return normalized


def _is_draft_status(value: str | None) -> bool:
    """Return True when report status is unset or Draft."""
    return (value or "").strip().lower() in {"", "draft"}


def _should_generate_ppt(value: str | None) -> bool:
    """Only generate PPT artifacts when the report has been finalized."""
    return (value or "").strip().lower() == "final"


@router.post("/", response_model=ReportOut, status_code=201)
async def create_report(
    payload: ReportCreate,
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
):
    trimmed_name = payload.name.strip()
    if not trimmed_name:
        raise HTTPException(status_code=422, detail="Report name is required")

    await _validate_report_payload(session, payload)

    existing_id = await session.scalar(
        select(models.Report.id).where(models.Report.name == trimmed_name)
    )
    if existing_id:
        raise HTTPException(status_code=409, detail="Report name already exists")

    current_user = await get_user_from_claims(session, claims)
    current_user_id = current_user.id if current_user else None
    current_user_email = _current_user_email(claims, current_user)
    _mode = _normalize_mode(payload.automation_mode)
    normalized_division = _normalize_string_list(payload.division or [])
    normalized_defined_markets = _normalize_string_list(payload.defined_markets or [])
    normalized_vacancy_index = _normalize_string_list(payload.vacancy_index or [])
    normalized_submarket = _normalize_string_list(payload.submarket or [])
    normalized_district = _normalize_string_list(payload.district or [])

    report = models.Report(
        name=trimmed_name,
        template_id=payload.template_id,
        template_name=payload.template_name,
        report_type=payload.report_type or payload.template_name,
        prompt_template_id=payload.prompt_template_id,
        prompt_template_label=payload.prompt_template_label,
        division=normalized_division,
        publishing_group=payload.publishing_group,
        property_type=payload.property_type,
        property_sub_type=payload.property_sub_type,
        automation_mode=_mode,
        quarter=payload.quarter,
        run_quarter=payload.run_quarter,
        history_range=payload.history_range,
        absorption_calculation=payload.absorption_calculation,
        total_vs_direct_absorption=payload.total_vs_direct_absorption,
        asking_rate_frequency=payload.asking_rate_frequency,
        asking_rate_type=payload.asking_rate_type,
        minimum_transaction_size=payload.minimum_transaction_size,
        use_auto_generated_text=payload.use_auto_generated_text,
        defined_markets=normalized_defined_markets,
        vacancy_index=normalized_vacancy_index,
        submarket=normalized_submarket,
        district=normalized_district,
        status=(payload.status or "Draft"),
        # For tier1 (attended), scheduling is not applicable
        schedule_status=("N/A" if _mode == "tier1" else "NA"),
        created_by=current_user_id,
        modified_by=current_user_id,
    )

    # Resolve prompt template by label if id missing
    if not report.prompt_template_id and report.prompt_template_label:
        prompt_match = await session.scalar(
            select(models.Prompt)
            .where(models.Prompt.label == report.prompt_template_label)
            .limit(1)
        )
        if prompt_match:
            report.prompt_template_id = prompt_match.id
            report.prompt_template_label = prompt_match.label

    session.add(report)
    # Ensure we have a DB identity for the report before creating conversations
    await session.flush()

    logger.debug(
        "create_report: Report created with audit tracking - id=%s, created_by=%s, modified_by=%s",
        report.id,
        report.created_by,
        report.modified_by,
    )

    await _persist_report_sections(
        session,
        report,
        payload.sections,
        report_meta=_build_report_meta(report),
        embed_meta=True,
    )

    try:
        await session.commit()
    except IntegrityError as err:
        await session.rollback()
        if "uq_reports_name" in str(err.orig):
            raise HTTPException(
                status_code=409, detail="Report name already exists"
            ) from err
        raise

    # Fetch hero_fields for all markets AFTER initial commit (tier1 single market, tier3 multiple markets)
    if report.defined_markets and not _is_draft_status(report.status):
        try:
            # Refresh report from DB to avoid session issues
            await session.refresh(report)

            hero_fields = await asyncio.to_thread(
                fetch_multi_market_hero_fields,
                report_meta=_build_report_meta(report),
                property_sub_type=report.property_sub_type,
                asking_rate_type=report.asking_rate_type,
                asking_rate_frequency=report.asking_rate_frequency,
            )
            if payload.ppt_data:
                hero_fields['ppt_data'] = payload.ppt_data
            report.hero_fields = hero_fields 
            
            await session.commit()
            logger.info(
                "create_report: Fetched hero_fields for %d markets",
                len(report.defined_markets),
            )
        except Exception as hero_err:
            logger.warning(
                "create_report: Failed to fetch hero_fields: %s",
                str(hero_err),
            )
            # Rollback if hero_fields fetch fails to avoid session issues
            try:
                await session.rollback()
            except Exception:
                pass
    elif report.defined_markets:
        logger.info(
            "create_report: Skipping hero_fields fetch for Draft status (report_id=%s)",
            report.id,
        )

    created_report = await _fetch_report_with_sections(session, report.id)
    if not created_report:
        raise HTTPException(status_code=404, detail="Report not found after creation")

    # Auto-generate report for tier3 (unattended) reports (skip during tests)

    if created_report.automation_mode and created_report.automation_mode.lower() in {
        "tier3",
        "unattended",
    }:
        logger.info(
            "create_report: Auto-generating tier3 report for report_id=%s",
            created_report.id,
        )
        try:
            # Generate the report asynchronously without blocking the response
            result = await run_report_now(
                session=session,
                report_id=created_report.id,
                trigger_source="manual",
                schedule_id=None,
                created_by=current_user_id,
            )

            # Check if generation failed
            if result.get("status") == "Failed" and current_user_email:
                # Send failure notification to report creator
                try:
                    await send_report_failure_notification(
                        to_emails=[current_user_email],
                        report_name=created_report.name,
                        trigger_source="manual",
                    )
                    logger.info(
                        "create_report: Sent failure notification for tier3 auto-generate to %s",
                        current_user_email,
                    )
                except Exception as notify_err:
                    logger.error(
                        "create_report: Failed to send failure notification: %s",
                        str(notify_err),
                    )
            else:
                logger.info(
                    "create_report: Successfully auto-generated tier3 report for report_id=%s",
                    created_report.id,
                )
        except Exception as gen_err:
            # Log error but don't fail the report creation
            logger.error(
                "create_report: Failed to auto-generate tier3 report for report_id=%s: %s",
                created_report.id,
                str(gen_err),
                exc_info=gen_err,
            )
            # Send failure notification to report creator
            if current_user_email:
                try:
                    await send_report_failure_notification(
                        to_emails=[current_user_email],
                        report_name=created_report.name,
                        trigger_source="manual",
                    )
                    logger.info(
                        "create_report: Sent failure notification for tier3 auto-generate to %s",
                        current_user_email,
                    )
                except Exception as notify_err:
                    logger.error(
                        "create_report: Failed to send failure notification: %s",
                        str(notify_err),
                    )

    return await _report_with_emails(session, created_report)


@router.get("/runs", response_model=ReportRunsListResponse)
async def list_report_runs(
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
    page: int = 1,
    page_size: int = 20,
    q: str | None = None,
    status: str | None = None,
    run_state: str | None = None,
    report_id: int | None = None,
    report_type: str | None = None,
    market: str | None = None,
    trigger_source: str | None = None,
    automation_mode: str | None = None,
    sort_by: str | None = Query(default=None, description="Field to sort by"),
    sort_order: str | None = Query(default="desc", description="asc or desc"),
):
    """Return flat list of recent report runs joined with report template name."""
    logger.info("list_report_runs")

    # Build permission tree for filtering
    permissions = get_user_permissions_from_claims(claims or {})
    permission_tree = build_permission_tree(permissions)

    try:
        rr = aliased(models.ReportRun)
        rpt = aliased(models.Report)
        sched = aliased(models.Schedule)
        page = 1 if page is None or page < 1 else int(page)
        page_size = 20 if page_size is None or page_size < 1 else int(page_size)
        page_size = min(page_size, 100)

        # Include division and defined_markets from Report for permission filtering
        base_stmt = (
            select(
                rr.id,
                rr.report_id,
                rr.schedule_id,
                sched.name.label("schedule_name"),
                sched.created_by.label("schedule_created_by"),
                rr.report_name,
                rr.report_type,
                rr.market,
                rr.sections,
                rr.status,
                rr.run_state,
                rr.trigger_source,
                rr.output_format,
                rr.ppt_url,
                rr.email_status,
                rr.run_time_seconds,
                rr.created_at,
                rr.created_by,
                rr.email_delivery_details.label("email_delivery_details"),
                rpt.template_name.label("template_name"),
                rpt.automation_mode.label("automation_mode"),
                rpt.property_sub_type.label("property_sub_type"),
                rpt.division.label("report_division"),
                rpt.defined_markets.label("report_markets"),
            )
            .select_from(rr)
            .join(rpt, rpt.id == rr.report_id, isouter=True)
            .join(sched, sched.id == rr.schedule_id, isouter=True)
        )
        # Apply filters
        conds = []
        if q:
            conds.append(rr.report_name.ilike(f"%{q}%"))
        if status:
            conds.append(func.lower(rr.status) == status.lower())
        if report_type:
            conds.append(func.lower(rr.report_type) == report_type.lower())
        if market:
            conds.append(rr.market.ilike(f"%{market}%"))
        if run_state:
            conds.append(func.lower(rr.run_state) == run_state.lower())
        if report_id:
            conds.append(rr.report_id == report_id)
        if trigger_source:
            conds.append(func.lower(rr.trigger_source) == trigger_source.lower())
            logger.debug(
                "list_report_runs: Filtering by trigger_source=%s", trigger_source
            )
        if automation_mode:
            conds.append(func.lower(rpt.automation_mode) == automation_mode.lower())
        if conds:
            base_stmt = base_stmt.where(and_(*conds))

        stmt = base_stmt.order_by(rr.created_at.desc())
        res = await session.execute(stmt)
        all_rows = res.mappings().all()

        # Filter by user permissions
        accessible_rows = [
            row
            for row in all_rows
            if user_can_access_report(
                row.get("report_division"), row.get("report_markets"), permission_tree
            )
        ]

        # Preload user emails for sorting and response hydration
        creator_ids = {
            row.get("created_by")
            for row in accessible_rows
            if row.get("created_by") is not None
        } | {
            row.get("schedule_created_by")
            for row in accessible_rows
            if row.get("schedule_created_by") is not None
        }
        email_map = await get_user_email_map(session, creator_ids)

        # Strip permission-related fields and attach emails
        rows_with_emails: list[dict] = []
        for row in accessible_rows:
            item = dict(row)
            item.pop("report_division", None)
            item.pop("report_markets", None)
            created_by_val = item.pop("created_by", None)
            schedule_created_by_val = item.pop("schedule_created_by", None)
            item["created_by_email"] = email_map.get(created_by_val or -1)
            item["schedule_created_by_email"] = email_map.get(
                schedule_created_by_val or -1
            )
            rows_with_emails.append(item)

        # Apply sorting
        sort_field = (sort_by or "").strip().lower()
        sort_dir = (sort_order or "desc").strip().lower()
        sort_desc = sort_dir != "asc"

        def _sort_key(row: dict):
            if sort_field == "report_name":
                return (row.get("report_name") or "").lower()
            if sort_field == "schedule_name":
                return (row.get("schedule_name") or "").lower()
            if sort_field == "template_name":
                return (row.get("template_name") or "").lower()
            if sort_field == "market":
                return (row.get("market") or "").lower()
            if sort_field == "status":
                return (row.get("status") or "").lower()
            if sort_field == "run_state":
                return (row.get("run_state") or "").lower()
            if sort_field == "trigger_source":
                return (row.get("trigger_source") or "").lower()
            if sort_field == "automation_mode":
                return (row.get("automation_mode") or "").lower()
            if sort_field == "email_status":
                return (row.get("email_status") or "").lower()
            if sort_field == "sections":
                try:
                    sections_payload = row.get("sections")
                    if isinstance(sections_payload, dict) and isinstance(
                        sections_payload.get("selected"), list
                    ):
                        return len(sections_payload.get("selected") or [])
                    if isinstance(sections_payload, list):
                        return len(sections_payload)
                except Exception:
                    return 0
                return 0
            if sort_field == "ppt_url":
                return row.get("ppt_url") or ""
            if sort_field == "triggered_by":
                return (
                    row.get("created_by_email")
                    or row.get("schedule_created_by_email")
                    or ""
                ).lower()
            if sort_field == "created_at":
                return row.get("created_at") or datetime.min
            return row.get("created_at") or datetime.min

        if rows_with_emails:
            if sort_field:
                rows_with_emails.sort(key=_sort_key, reverse=sort_desc)
            else:
                rows_with_emails.sort(
                    key=lambda row: row.get("created_at") or datetime.min,
                    reverse=True,
                )

        # Calculate total count after permission filtering
        total_count = len(rows_with_emails)

        # Apply pagination to filtered results
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        paginated_rows = rows_with_emails[start_idx:end_idx]

        result: list[dict] = []
        for row in paginated_rows:
            item = dict(row)
            # Derive agents count from sections payload when possible
            agents_count: int | None = None
            try:
                sections = item.get("sections")
                if isinstance(sections, dict):
                    if isinstance(sections.get("selected"), list):
                        agents_count = len(sections.get("selected") or [])
                    elif isinstance(sections.get("count"), int):
                        agents_count = int(sections.get("count"))
                elif isinstance(sections, list):
                    agents_count = len(sections)
            except Exception:
                agents_count = None
            item["agents"] = agents_count
            result.append(item)
        return ReportRunsListResponse(totalCount=total_count, items=result)
    except Exception as err:
        raise HTTPException(
            status_code=500, detail="Failed to fetch report runs"
        ) from err


@router.get("/runs/active", response_model=ReportRunsListResponse)
async def list_active_report_runs(
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
    report_id: int | None = None,
    report_type: str | None = None,
    market: str | None = None,
):
    """Return report runs that are currently running (abort candidates)."""
    # Build permission tree for filtering
    permissions = get_user_permissions_from_claims(claims or {})
    permission_tree = build_permission_tree(permissions)

    try:
        rr = aliased(models.ReportRun)
        rpt = aliased(models.Report)

        base_stmt = (
            select(
                rr.id,
                rr.report_id,
                rr.report_name,
                rr.report_type,
                rr.market,
                rr.status,
                rr.run_state,
                rr.trigger_source,
                rr.output_format,
                rr.ppt_url,
                rr.run_time_seconds,
                rr.created_at,
                rr.created_by,
                rpt.division.label("report_division"),
                rpt.defined_markets.label("report_markets"),
            )
            .select_from(rr)
            .join(rpt, rpt.id == rr.report_id, isouter=True)
            .where(func.lower(rr.run_state) == "running")
        )

        conds = []
        if report_id:
            conds.append(rr.report_id == report_id)
        if report_type:
            conds.append(func.lower(rr.report_type) == report_type.lower())
        if market:
            conds.append(rr.market.ilike(f"%{market}%"))
        if conds:
            base_stmt = base_stmt.where(and_(*conds))

        stmt = base_stmt.order_by(rr.created_at.desc())
        res = await session.execute(stmt)
        all_rows = res.mappings().all()

        # Permission filter
        accessible_rows = [
            row
            for row in all_rows
            if user_can_access_report(
                row.get("report_division"), row.get("report_markets"), permission_tree
            )
        ]

        email_map = await get_user_email_map(
            session,
            {
                row.get("created_by")
                for row in accessible_rows
                if row.get("created_by") is not None
            },
        )

        result: list[dict] = []
        for row in accessible_rows:
            item = dict(row)
            item.pop("report_division", None)
            item.pop("report_markets", None)
            created_by_val = item.pop("created_by", None)
            item["created_by_email"] = email_map.get(created_by_val or -1)
            result.append(item)

        return ReportRunsListResponse(totalCount=len(result), items=result)
    except Exception as err:
        logger.exception("list_active_report_runs failed", exc_info=err)
        raise HTTPException(
            status_code=500, detail="Failed to fetch active runs"
        ) from err


@router.post("/runs/bulk-delete")
async def bulk_delete_report_runs(
    payload: dict,
    session: AsyncSession = Depends(get_session),
):
    ids = payload.get("ids", [])
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="ids list is required")
    numeric_ids = [
        int(i) for i in ids if isinstance(i, (int, str)) and str(i).isdigit()
    ]
    if not numeric_ids:
        raise HTTPException(status_code=400, detail="No valid ids provided")
    try:
        result = await session.execute(
            delete(models.ReportRun).where(models.ReportRun.id.in_(numeric_ids))
        )
        await session.commit()
        return {"deleted": result.rowcount or 0}
    except Exception as err:
        await session.rollback()
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise


@router.get("/download")
async def download_report(
    run_id: int,
    session: AsyncSession = Depends(get_session),
):
    """Generate presigned URL for a specific report run (market-specific PPT) in S3.

    All downloads are now governed by run_id only. Each market PPT generation creates
    a unique ReportRun entry, and downloads reference that specific run_id.

    Args:
        run_id: The ID of the ReportRun to download

    Returns:
        RedirectResponse to the presigned S3 URL
    """
    logger.info("download_report: Looking up report run with id=%s", run_id)

    run = await session.get(models.ReportRun, run_id)
    if not run:
        logger.error("download_report: Report run not found for id=%s", run_id)
        raise HTTPException(status_code=404, detail="Report run not found")

    s3_path = run.s3_path
    logger.debug("download_report: Found report run, s3_path=%s", s3_path)

    if not s3_path:
        logger.error("download_report: No s3_path found for run_id=%s", run_id)
        raise HTTPException(status_code=404, detail="Report file not found")

    # Generate presigned URL and redirect
    try:
        s3_key = _extract_s3_key(s3_path)
        presigned_url = await generate_presigned_url_for_key(key=s3_key)
        logger.info(
            "download_report: Successfully generated presigned URL for run_id=%s",
            run_id,
        )
        return RedirectResponse(url=presigned_url)
    except Exception as err:
        logger.exception(
            "download_report: Failed to generate download URL for s3_path=%s",
            s3_path,
            exc_info=err,
        )
        raise HTTPException(
            status_code=500, detail="Failed to generate download URL"
        ) from err


def _extract_s3_key(s3_path: str) -> str:
    """Extract S3 key from s3:// path or return as-is if already a key."""
    if s3_path.startswith("s3://"):
        _, rest = s3_path.split("s3://", 1)
        _, s3_key = rest.split("/", 1)
        return s3_key
    return s3_path


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(report_id: int, session: AsyncSession = Depends(get_session)):
    report = await _fetch_report_with_sections(session, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    await _attach_prompt_metadata_for_report(session, report)
    eval_stmt = (
        select(models.CommentaryEvaluation)
        .where(models.CommentaryEvaluation.report_id == report_id)
        .order_by(models.CommentaryEvaluation.created_at.desc())
    )
    eval_records = (await session.execute(eval_stmt)).scalars().all()
    evaluations = [
        ReportEvaluationOut(
            id=record.id,
            run_id=record.run_id,
            section_name=record.section_name,
            property_type=record.property_type,
            property_sub_type=record.property_sub_type,
            division=record.division,
            publishing_group=record.publishing_group,
            automation_mode=record.automation_mode,
            quarter=record.quarter,
            history_range=record.history_range,
            absorption_calculation=record.absorption_calculation,
            total_vs_direct_absorption=record.total_vs_direct_absorption,
            asking_rate_frequency=record.asking_rate_frequency,
            asking_rate_type=record.asking_rate_type,
            defined_markets=list(record.defined_markets or []),
            generated_commentary=record.generated_commentary,
            ground_truth_commentary=record.ground_truth_commentary,
            evaluation_result=dict(record.evaluation_result or {}),
            model_details=dict(record.model_details or {}),
            created_at=record.created_at,
        )
        for record in eval_records
    ]
    report_model = await _report_with_emails(session, report)
    return report_model.model_copy(update={"evaluations": evaluations})


class RunReportIn(BaseModel):
    send_email: bool | None = None
    recipients: list[EmailStr] | None = None


class AbortRunIn(BaseModel):
    aborted_by: str | None = None
    reason: str | None = None


@router.post("/{report_id}/run")
async def run_report_endpoint(
    report_id: int,
    payload: RunReportIn | None = None,
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
):
    """Generate a PPT for the report, upload to S3, record a run, and return the link.

    - Builds a section-wise PPT (charts/tables with associated SQL, commentary)
    - Uploads to S3 using existing utilities
    - Stores a ReportRun row with status=Success and presigned URL
    - Logs a success message to stdout
    """
    try:
        logger.info(
            "run_report_endpoint start report_id=%s send_email=%s",
            report_id,
            getattr(payload, "send_email", None),
        )

        current_user = await get_user_from_claims(session, claims)
        current_user_id = current_user.id if current_user else None

        result = await run_report_now(
            session,
            report_id,
            trigger_source="manual",
            schedule_id=None,
            created_by=current_user_id,
        )
        logger.info("run_report_endpoint result: %s", result)
        if "run_state" not in result or not result.get("run_state"):
            result["run_state"] = "completed"
        if "status" not in result or not result.get("status"):
            result["status"] = "Success"
        # Ensure email_status is present and defaults to Success unless mail send fails below
        if "email_status" not in result or not result.get("email_status"):
            result["email_status"] = "Success"
        logger.info(
            "[Run Report] Report %s generated successfully - run_id=%s, url=%s, "
            "trigger_source=manual, created_by=%s",
            report_id,
            result.get("run_id"),
            result.get("s3_path"),
            current_user_id,
        )
        should_email = bool(
            payload and payload.send_email and (payload.recipients or [])
        )
        market_ppt_info = result.get("market_ppt_info", [])
        all_run_ids = result.get("all_run_ids", [result.get("run_id")])

        if should_email:
            # Skip notifications if any associated run was aborted
            aborted_ids: set[int] = set()
            if all_run_ids:
                aborted_rows = await session.execute(
                    select(models.ReportRun.id).where(
                        models.ReportRun.id.in_(all_run_ids),
                        func.lower(models.ReportRun.run_state) == "aborted",
                    )
                )
                aborted_ids = {row[0] for row in aborted_rows.all()}

            if aborted_ids:
                result["email_status"] = "Aborted"
                result["email_delivery_details"] = {
                    "status": "aborted",
                    "runs": sorted(aborted_ids),
                }
                logger.info(
                    "Skipping email notification because run(s) aborted: %s",
                    sorted(aborted_ids),
                )
                for run_id in all_run_ids:
                    if run_id:
                        await session.execute(
                            update(models.ReportRun)
                            .where(models.ReportRun.id == run_id)
                            .values(email_status="Aborted", email_delivery_details={"status": "Aborted"})
                        )
                await session.commit()
                return result

            try:
                # Fetch report to get report name (without eager loading to avoid unique() requirement)
                report_result = await session.execute(
                    select(models.Report).where(models.Report.id == report_id)
                )
                report = report_result.unique().scalar_one_or_none()
                report_name = report.name if report else f"Report {report_id}"

                # Check if all markets failed
                if result.get("status") == "Failed":
                    # All markets failed - send failure notification
                    logger.info(
                        "sending failure notification (all markets failed), recipients=%s",
                        list(payload.recipients or []),
                    )
                    delivery_details = await send_report_failure_notification(
                        to_emails=list(payload.recipients or []),
                        report_name=report_name,
                        trigger_source="manual",
                    )
                elif len(market_ppt_info) > 1:
                    # Multi-market report - use multi-market notification (handles mixed success/failure)
                    logger.info(
                        "sending multi-market email for %d markets, recipients=%s",
                        len(market_ppt_info),
                        list(payload.recipients or []),
                    )
                    delivery_details = await send_multi_market_report_notification(
                        to_emails=list(payload.recipients or []),
                        market_ppt_info=market_ppt_info,
                        report_name=report_name,
                        trigger_source="manual",
                    )
                else:
                    # Single market - use original function (only if succeeded)
                    if result.get("status") == "Success":
                        logger.info(
                            "sending email for run_id=%s recipients=%s",
                            result.get("run_id"),
                            list(payload.recipients or []),
                        )
                        # Extract presigned URL from market_ppt_info for email (same as multi-market)
                        ppt_url_for_email = None
                        if market_ppt_info and len(market_ppt_info) > 0:
                            ppt_url_for_email = market_ppt_info[0].get("ppt_url")

                        delivery_details = await send_report_notification(
                            to_emails=list(payload.recipients or []),
                            s3_path=result.get("s3_path"),
                            ppt_url=ppt_url_for_email,
                            trigger_source="manual",
                            report_name=report_name,
                        )
                    else:
                        # Single market failed
                        logger.info(
                            "sending failure notification (single market failed), recipients=%s",
                            list(payload.recipients or []),
                        )
                        delivery_details = await send_report_failure_notification(
                            to_emails=list(payload.recipients or []),
                            report_name=report_name,
                            trigger_source="manual",
                        )

                # Determine overall email status
                all_success = all(
                    status == "Success" for status in delivery_details.values()
                )
                all_failed = all(
                    status == "Failed" for status in delivery_details.values()
                )

                if all_success:
                    result["email_status"] = "Success"
                    logger.info(
                        "Email sent successfully to all %d recipients",
                        len(delivery_details),
                    )
                elif all_failed:
                    result["email_status"] = "Failed"
                    logger.warning("Email failed to send to all recipients")
                else:
                    result["email_status"] = "Partial"
                    success_count = sum(
                        1 for s in delivery_details.values() if s == "Success"
                    )
                    logger.warning(
                        "Email partially delivered: %d/%d successful",
                        success_count,
                        len(delivery_details),
                    )

                result["email_delivery_details"] = delivery_details

                # Update email status for ALL ReportRun entries (one per market)
                for run_id in all_run_ids:
                    if run_id:
                        await session.execute(
                            update(models.ReportRun)
                            .where(models.ReportRun.id == run_id)
                            .values(
                                email_status=result["email_status"],
                                email_delivery_details=delivery_details,
                            )
                        )
                await session.commit()
                logger.info("Updated email status for %d report runs", len(all_run_ids))

            except Exception as e:
                logger.error("Exception while sending email: %s", str(e))
                # Mark email as failed but don't fail the entire report generation
                result["email_status"] = "Failed"

                # Update all runs with failed email status
                for run_id in all_run_ids:
                    if run_id:
                        await session.execute(
                            update(models.ReportRun)
                            .where(models.ReportRun.id == run_id)
                            .values(email_status=result["email_status"])
                        )
                await session.commit()
        logger.info(
            "run_report_endpoint done report_id=%s run_id=%s",
            report_id,
            result.get("run_id"),
        )
        return result
    except ValueError as not_found:
        raise HTTPException(
            status_code=404, detail=str(not_found) or "Report not found"
        )
    except HTTPException:
        raise
    except Exception as err:
        logger.exception("[Run Report] failed", exc_info=err)

        # Send failure notification if recipients were specified
        if payload and payload.send_email and payload.recipients:
            try:
                # Fetch report name for notification
                report_result = await session.execute(
                    select(models.Report).where(models.Report.id == report_id)
                )
                report = report_result.scalar_one_or_none()
                report_name = report.name if report else f"Report {report_id}"

                await send_report_failure_notification(
                    to_emails=list(payload.recipients),
                    report_name=report_name,
                    trigger_source="manual",
                )
                logger.info(
                    "[Run Report] Sent failure notification to %s",
                    list(payload.recipients),
                )
            except Exception as notify_err:
                logger.error(
                    "[Run Report] Failed to send failure notification: %s",
                    str(notify_err),
                )

        raise HTTPException(status_code=500, detail="Failed to run report")


@router.post("/runs/{run_id}/abort")
async def abort_report_run(
    run_id: int,
    payload: AbortRunIn | None = None,
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
):
    """Abort a running report run by marking its run_state and trigger_source."""
    run = await session.get(models.ReportRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Report run not found")

    current_state = (run.run_state or "").lower()
    if current_state not in {"running"}:
        raise HTTPException(
            status_code=400,
            detail="Report run is not in a running state",
        )

    user = await get_user_from_claims(session, claims)
    aborted_by = (payload.aborted_by if payload else None) or _current_user_email(
        claims, user
    )
    if not aborted_by and user and getattr(user, "username", None):
        aborted_by = user.username
    safe_trigger_source = (aborted_by or "unknown").strip() or "unknown"
    safe_trigger_source = safe_trigger_source[:32]

    # Capture how long the run lasted before aborting when possible.
    try:
        if run.created_at:
            elapsed_seconds = int(
                max(
                    0,
                    (datetime.utcnow() - run.created_at).total_seconds(),
                )
            )
            run.run_time_seconds = elapsed_seconds
    except Exception:
        pass

    run.run_state = "aborted"
    run.status = "Aborted"
    run.trigger_source = safe_trigger_source

    await session.commit()
    await session.refresh(run)

    logger.info(
        "abort_report_run: run_id=%s aborted_by=%s reason=%s",
        run_id,
        safe_trigger_source,
        payload.reason if payload else None,
    )

    return {
        "id": run.id,
        "run_state": run.run_state,
        "status": run.status,
        "trigger_source": run.trigger_source,
    }


@router.delete("/{report_id}", status_code=204)
async def delete_report(report_id: int, session: AsyncSession = Depends(get_session)):
    report = await session.get(models.Report, report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    try:
        await session.delete(report)
        await session.commit()
        return None
    except Exception as err:
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise


@router.put("/{report_id}", response_model=ReportOut)
async def update_report(
    report_id: int,
    payload: ReportCreate,
    session: AsyncSession = Depends(get_session),
):
    trimmed_name = payload.name.strip()
    if not trimmed_name:
        raise HTTPException(status_code=422, detail="Report name is required")

    await _validate_report_payload(session, payload)

    result = await session.execute(
        select(models.Report)
        .options(
            selectinload(models.Report.sections).selectinload(
                models.ReportSection.elements
            )
        )
        .where(models.Report.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    if trimmed_name != report.name:
        duplicate = await session.scalar(
            select(models.Report.id)
            .where(models.Report.name == trimmed_name)
            .where(models.Report.id != report_id)
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="Report name already exists")

    report.name = trimmed_name
    report.template_id = payload.template_id
    report.template_name = payload.template_name
    report.report_type = payload.report_type or payload.template_name
    report.prompt_template_id = payload.prompt_template_id
    report.prompt_template_label = payload.prompt_template_label
    report.division = _normalize_divisions(payload.division)
    report.publishing_group = payload.publishing_group
    report.property_type = payload.property_type
    report.property_sub_type = payload.property_sub_type
    report.automation_mode = _normalize_mode(payload.automation_mode)
    if (report.automation_mode or "").lower() == "tier1":
        report.schedule_status = "N/A"
    report.quarter = payload.quarter
    report.run_quarter = payload.run_quarter
    report.history_range = payload.history_range
    report.absorption_calculation = payload.absorption_calculation
    report.total_vs_direct_absorption = payload.total_vs_direct_absorption
    report.asking_rate_frequency = payload.asking_rate_frequency
    report.asking_rate_type = payload.asking_rate_type
    report.minimum_transaction_size = payload.minimum_transaction_size
    report.use_auto_generated_text = payload.use_auto_generated_text
    if payload.status:
        report.status = payload.status
    report.defined_markets = list(dict.fromkeys(payload.defined_markets or []))

    if not report.prompt_template_id and report.prompt_template_label:
        prompt_match = await session.scalar(
            select(models.Prompt)
            .where(models.Prompt.label == report.prompt_template_label)
            .limit(1)
        )
        if prompt_match:
            report.prompt_template_id = prompt_match.id
            report.prompt_template_label = prompt_match.label

    existing_section_ids = {
        sec.id
        for sec in getattr(report, "sections", [])
        if getattr(sec, "id", None) is not None
    }
    preserved_ids = await _persist_report_sections(
        session,
        report,
        payload.sections,
        report_meta=_build_report_meta(report),
        embed_meta=True,
        existing_sections=list(getattr(report, "sections", []) or []),
    )
    to_remove = {
        sec_id for sec_id in existing_section_ids if sec_id not in preserved_ids
    }
    if to_remove:
        await session.execute(
            delete(models.ReportSection).where(
                models.ReportSection.id.in_(list(to_remove))
            )
        )
        if hasattr(report, "sections"):
            report.sections[:] = [
                sec
                for sec in report.sections
                if getattr(sec, "id", None) not in to_remove
            ]
    elif hasattr(report, "sections"):
        report.sections[:] = [
            sec
            for sec in report.sections
            if getattr(sec, "id", None) in preserved_ids
            or getattr(sec, "id", None) is None
        ]

    try:
        await session.commit()
    except IntegrityError as err:
        await session.rollback()
        if "uq_reports_name" in str(err.orig):
            raise HTTPException(
                status_code=409, detail="Report name already exists"
            ) from err
        raise

    # Fetch hero_fields for all markets AFTER commit (tier1 single market, tier3 multiple markets)
    if report.defined_markets and not _is_draft_status(report.status):
        try:
            # Refresh report from DB to avoid session issues
            await session.refresh(report)

            hero_fields = await asyncio.to_thread(
                fetch_multi_market_hero_fields,
                report_meta=_build_report_meta(report),
                property_sub_type=report.property_sub_type,
                asking_rate_type=report.asking_rate_type,
                asking_rate_frequency=report.asking_rate_frequency,
            )
            report.hero_fields = hero_fields
            await session.commit()
            logger.info(
                "update_report: Fetched hero_fields for %d markets",
                len(report.defined_markets),
            )
        except Exception as hero_err:
            logger.warning(
                "update_report: Failed to fetch hero_fields: %s",
                str(hero_err),
            )
            # Rollback if hero_fields fetch fails to avoid session issues
            try:
                await session.rollback()
            except Exception:
                pass
    elif report.defined_markets:
        logger.info(
            "update_report: Skipping hero_fields fetch for Draft status (report_id=%s)",
            report.id,
        )

    updated_report = await _fetch_report_with_sections(session, report_id)
    if not updated_report:
        raise HTTPException(status_code=404, detail="Report not found after update")
    return await _report_with_emails(session, updated_report)


@router.patch("/{report_id}/save", response_model=ReportOut)
async def save_report_changes(
    report_id: int,
    payload: ReportSaveIn,
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
):
    """Save edited report content (Step 2).

    - Does not require full report metadata; accepts optional sections and status.
    - When sections are provided, replaces existing sections/elements for the report with the new set.
    - Persists commentary via `prompt_text` on commentary elements.
    """
    # Fetch report
    result = await session.execute(
        select(models.Report)
        .options(
            selectinload(models.Report.sections).selectinload(
                models.ReportSection.elements
            )
        )
        .where(models.Report.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    current_user = await get_user_from_claims(session, claims)
    current_user_id = current_user.id if current_user else None

    sections_payload = payload.sections
    if sections_payload is not None:
        issues: list[str] = []
        sections = list(sections_payload or [])
        if not sections:
            issues.append("at least one section is required")
        else:
            selected = [s for s in sections if getattr(s, "selected", True)]
            if not selected:
                issues.append("at least one section must be selected")
            for idx, s in enumerate(selected):
                if not (s.name or s.key):
                    issues.append(f"sections[{idx}]: name or key is required")
                if not isinstance(s.elements, list) or len(s.elements) == 0:
                    issues.append(f"sections[{idx}]: at least one element is required")
                    continue
                for j, e in enumerate(s.elements):
                    et = (e.element_type or "").lower()
                    if et not in ALLOWED_ELEMENT_TYPES:
                        issues.append(
                            f"sections[{idx}].elements[{j}]: invalid element_type '{e.element_type}'"
                        )
                    if e.display_order is not None and getattr(e, "display_order") < 0:
                        issues.append(
                            f"sections[{idx}].elements[{j}]: display_order must be >= 0"
                        )
                    if e.config is not None and not isinstance(e.config, dict):
                        issues.append(
                            f"sections[{idx}].elements[{j}]: config must be an object"
                        )
        if issues:
            raise HTTPException(
                status_code=422,
                detail={"message": "Invalid sections payload", "issues": issues},
            )

    # Optionally update status
    if payload.status:
        report.status = payload.status
    if current_user_id:
        report.modified_by = current_user_id
        logger.debug(
            "patch_report: Set modified_by=%s for report_id=%s (created_by=%s)",
            current_user_id,
            report_id,
            report.created_by,
        )
        # Don't backfill created_by for historical reports

    # Ensure schedule_status reflects mode on save: tier1 => N/A
    try:
        if (report.automation_mode or "").lower() == "tier1":
            report.schedule_status = "N/A"
    except Exception:
        # non-fatal
        pass

    preserved_ids: set[int] = set()
    if sections_payload is not None:
        existing_section_ids = {
            sec.id
            for sec in getattr(report, "sections", [])
            if getattr(sec, "id", None) is not None
        }
        preserved_ids = await _persist_report_sections(
            session,
            report,
            sections_payload,
            report_meta=_build_report_meta(report),
            embed_meta=True,
            existing_sections=list(getattr(report, "sections", []) or []),
        )
        to_remove = {
            sec_id for sec_id in existing_section_ids if sec_id not in preserved_ids
        }
        if to_remove:
            await session.execute(
                delete(models.ReportSection).where(
                    models.ReportSection.id.in_(list(to_remove))
                )
            )
            if hasattr(report, "sections"):
                report.sections[:] = [
                    sec
                    for sec in report.sections
                    if getattr(sec, "id", None) not in to_remove
                ]
        elif hasattr(report, "sections"):
            report.sections[:] = [
                sec
                for sec in report.sections
                if getattr(sec, "id", None) in preserved_ids
                or getattr(sec, "id", None) is None
            ]

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise

    # Fetch hero_fields for all markets AFTER commit (tier1 single market, tier3 multiple markets)
    if report.defined_markets and not _is_draft_status(report.status):
        try:
            # Refresh report from DB to avoid session issues
            await session.refresh(report)

            hero_fields = await asyncio.to_thread(
                fetch_multi_market_hero_fields,
                report_meta=_build_report_meta(report),
                property_sub_type=report.property_sub_type,
                asking_rate_type=report.asking_rate_type,
                asking_rate_frequency=report.asking_rate_frequency,
            )
            report.hero_fields = hero_fields
            await session.commit()
            logger.info(
                "save_report_changes: Fetched hero_fields for %d markets",
                len(report.defined_markets),
            )
        except Exception as hero_err:
            logger.warning(
                "save_report_changes: Failed to fetch hero_fields: %s",
                str(hero_err),
            )
            # Rollback if hero_fields fetch fails to avoid session issues
            try:
                await session.rollback()
            except Exception:
                pass
    elif report.defined_markets:
        logger.info(
            "save_report_changes: Skipping hero_fields fetch for Draft status (report_id=%s)",
            report.id,
        )

    updated = await _fetch_report_with_sections(session, report_id)
    if not updated:
        raise HTTPException(status_code=404, detail="Report not found after save")
    return await _report_with_emails(session, updated)


@router.patch("/{report_id}", response_model=ReportOut)
async def patch_report(
    report_id: int,
    payload: ReportPatchIn,
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
):
    """Partially update a report. If sections are provided, replaces them.

    Supports updating any subset of top-level fields and optionally the full
    sections graph, without requiring the full PUT payload.
    """
    result = await session.execute(
        select(models.Report)
        .options(
            selectinload(models.Report.sections).selectinload(
                models.ReportSection.elements
            )
        )
        .where(models.Report.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    current_user = await get_user_from_claims(session, claims)
    current_user_id = current_user.id if current_user else None

    # Handle optional name change with conflict check
    if payload.name is not None:
        trimmed = payload.name.strip()
        if not trimmed:
            raise HTTPException(status_code=422, detail="Report name cannot be blank")
        if trimmed != report.name:
            duplicate = await session.scalar(
                select(models.Report.id)
                .where(models.Report.name == trimmed)
                .where(models.Report.id != report_id)
            )
            if duplicate:
                raise HTTPException(
                    status_code=409, detail="Report name already exists"
                )
            report.name = trimmed

    # Patch simple scalar fields if present
    def set_if_present(field: str):
        val = getattr(payload, field)
        if val is not None:
            setattr(report, field, val)

    set_if_present("template_id")
    set_if_present("template_name")
    set_if_present("report_type")
    set_if_present("prompt_template_id")
    set_if_present("prompt_template_label")
    # division is handled separately below for deduplication
    set_if_present("publishing_group")
    set_if_present("property_type")
    set_if_present("property_sub_type")
    set_if_present("quarter")
    set_if_present("run_quarter")
    set_if_present("history_range")
    set_if_present("absorption_calculation")
    set_if_present("total_vs_direct_absorption")
    set_if_present("asking_rate_frequency")
    set_if_present("asking_rate_type")
    set_if_present("minimum_transaction_size")
    if payload.use_auto_generated_text is not None:
        report.use_auto_generated_text = payload.use_auto_generated_text

    if payload.status:
        report.status = payload.status

    if payload.automation_mode is not None:
        report.automation_mode = _normalize_mode(payload.automation_mode)
        if (report.automation_mode or "").lower() == "tier1":
            report.schedule_status = "N/A"

    if payload.defined_markets is not None:
        report.defined_markets = _normalize_string_list(payload.defined_markets or [])

    if payload.vacancy_index is not None:
        report.vacancy_index = _normalize_string_list(payload.vacancy_index or [])

    if payload.submarket is not None:
        report.submarket = _normalize_string_list(payload.submarket or [])

    if payload.district is not None:
        report.district = _normalize_string_list(payload.district or [])

    if payload.division is not None:
        report.division = _normalize_divisions(payload.division)

    # Resolve prompt label if id missing
    if not report.prompt_template_id and report.prompt_template_label:
        prompt_match = await session.scalar(
            select(models.Prompt)
            .where(models.Prompt.label == report.prompt_template_label)
            .limit(1)
        )
        if prompt_match:
            report.prompt_template_id = prompt_match.id
            report.prompt_template_label = prompt_match.label

    # Replace sections if provided
    if payload.sections is not None:
        # Validate as in create/update
        issues: list[str] = []
        sections = list(payload.sections or [])
        if sections:
            selected = [s for s in sections if getattr(s, "selected", True)]
            if not selected:
                issues.append("at least one section must be selected")
            for idx, s in enumerate(selected):
                if not (s.name or s.key):
                    issues.append(f"sections[{idx}]: name or key is required")
                if not isinstance(s.elements, list) or len(s.elements) == 0:
                    issues.append(f"sections[{idx}]: at least one element is required")
                    continue
                for j, e in enumerate(s.elements):
                    et = (e.element_type or "").lower()
                    if et not in ALLOWED_ELEMENT_TYPES:
                        issues.append(
                            f"sections[{idx}].elements[{j}]: invalid element_type '{e.element_type}'"
                        )
                    if e.display_order is not None and getattr(e, "display_order") < 0:
                        issues.append(
                            f"sections[{idx}].elements[{j}]: display_order must be >= 0"
                        )
                    if e.config is not None and not isinstance(e.config, dict):
                        issues.append(
                            f"sections[{idx}].elements[{j}]: config must be an object"
                        )
        if issues:
            raise HTTPException(
                status_code=422,
                detail={"message": "Invalid sections payload", "issues": issues},
            )

        existing_section_ids = {
            sec.id
            for sec in getattr(report, "sections", [])
            if getattr(sec, "id", None) is not None
        }
        preserved_ids = await _persist_report_sections(
            session,
            report,
            payload.sections,
            report_meta=_build_report_meta(report),
            embed_meta=True,
            existing_sections=list(getattr(report, "sections", []) or []),
        )
        to_remove = {
            sec_id for sec_id in existing_section_ids if sec_id not in preserved_ids
        }
        if to_remove:
            await session.execute(
                delete(models.ReportSection).where(
                    models.ReportSection.id.in_(list(to_remove))
                )
            )
            if hasattr(report, "sections"):
                report.sections[:] = [
                    sec
                    for sec in report.sections
                    if getattr(sec, "id", None) not in to_remove
                ]
        elif hasattr(report, "sections"):
            report.sections[:] = [
                sec
                for sec in report.sections
                if getattr(sec, "id", None) in preserved_ids
                or getattr(sec, "id", None) is None
            ]

    if current_user_id:
        report.modified_by = current_user_id
        # Don't backfill created_by for historical reports

    try:
        await session.commit()
        # Force a fresh load of the report graph in the current session.
        session.expire_all()
    except IntegrityError as err:
        await session.rollback()
        if "uq_reports_name" in str(err.orig):
            raise HTTPException(
                status_code=409, detail="Report name already exists"
            ) from err
        raise

    updated_report = await _fetch_report_with_sections(session, report_id)
    if not updated_report:
        raise HTTPException(status_code=404, detail="Report not found after patch")

    # Fetch hero_fields for all markets AFTER commit, BEFORE PPT generation (tier1 single market, tier3 multiple markets)
    if updated_report.defined_markets and not _is_draft_status(updated_report.status):
        try:
            # Refresh report from DB to avoid session issues
            await session.refresh(updated_report)

            hero_fields = await asyncio.to_thread(
                fetch_multi_market_hero_fields,
                report_meta=_build_report_meta(updated_report),
                property_sub_type=updated_report.property_sub_type,
                asking_rate_type=updated_report.asking_rate_type,
                asking_rate_frequency=updated_report.asking_rate_frequency,
            )
            updated_report.hero_fields = hero_fields
            if payload.ppt_data:
                updated_report.hero_fields['ppt_data'] = payload.ppt_data
            await session.commit()
            logger.info(
                "patch_report: Fetched hero_fields for %d markets",
                len(updated_report.defined_markets),
            )
        except Exception as hero_err:
            logger.warning(
                "patch_report: Failed to fetch hero_fields; keeping previous hero_fields: %s",
                str(hero_err),
            )
            # Rollback if hero_fields fetch fails to avoid session issues
            try:
                await session.rollback()
            except Exception:
                pass
    elif updated_report.defined_markets:
        logger.info(
            "patch_report: Skipping hero_fields fetch for Draft status (report_id=%s)",
            updated_report.id,
        )

    # Report updated properly, generate PPT with ReportRun tracking when finalized
    if _should_generate_ppt(updated_report.status):
        result = await generate_report_ppt_only(
            session, report_id, trigger_source="manual", created_by=current_user_id
        )

        # Save the PPT URLs and paths to the report (now as lists)
        if result and result.get("ppt_url"):
            updated_report.ppt_url = result["ppt_url"]  # List of URLs
            updated_report.s3_path = result["s3_path"]  # List of S3 paths
            updated_report.market_ppt_mapping = result.get("market_ppt_mapping", {})
            await session.commit()
    else:
        logger.info(
            "patch_report: Skipping PPT generation for non-final status (report_id=%s, status=%s)",
            updated_report.id,
            updated_report.status,
        )

    return await _report_with_emails(session, updated_report)


# class LLMGenerateIn(BaseModel):
#     adjust_prompt: str | None = None
#     prompt_template_id: int | None = None
#     prompt_template_label: str | None = None
#     charts_data: list[dict] | None = None
#     tables_data: list[dict] | None = None
#     feedback: str | None = None
#     commentary: str | None = None


async def _parse_llm_request_payload(request: Request) -> dict:
    """Parse and validate the incoming request payload for LLM generation."""
    try:
        request_obj = await request.json()
        payload = (
            request_obj.get("payload")
            if isinstance(request_obj, dict) and "payload" in request_obj
            else request_obj
        )
        return payload
    except Exception:
        logger.info("AGENTS /llm-generate-preview invalid JSON Payload body")
        raise HTTPException(status_code=400, detail="Invalid JSON Payload")


def _extract_tier1_commentary_data(section_name: str, elements: list[dict]) -> dict:
    """Extract commentary data from section elements for tier1 mode."""
    section_commentary_data = {
        section_name: {
            "commentary_sql_list": [],
            "adjust_prompt": None,
            "commentary_data": [],
            "commentary_prompt_list": [],
        }
    }

    for el in elements:
        if el.get("elementType") == "commentary":
            sql_list = el["config"].get("sql_list", [])
            adjust_prompt = el["config"].get("adjust_prompt")
            prompt_list = el["config"].get("prompt_list", [])

            if sql_list and isinstance(sql_list, list):
                section_commentary_data[section_name]["commentary_sql_list"] = sql_list
            if adjust_prompt and isinstance(adjust_prompt, str):
                section_commentary_data[section_name]["adjust_prompt"] = adjust_prompt
            if prompt_list and isinstance(prompt_list, list):
                section_commentary_data[section_name]["commentary_prompt_list"] = (
                    prompt_list
                )

    return section_commentary_data


def _fetch_snowflake_data_for_section(
    commentary_sql_list: list[str], report_payload: dict
) -> list[str]:
    """Render SQL templates and fetch data from Snowflake."""
    try:
        rendered_sql_list = [
            render_sql_template(sql_template, report_payload)
            for sql_template in commentary_sql_list
        ]
        logger.info(f"AGENTS /preview-chart rendered-sql: \n{rendered_sql_list}")
    except Exception as e:
        logger.error(f"AGENTS /preview-chart error: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail="Failed to render SQL template. Please check the SQL syntax and rerun the query.",
        )

    data_list = []
    if env == "CBRE":
        try:
            for sql in rendered_sql_list:
                db_response = fetch_snowflake_data(sql)
                data_list.append(json.dumps(db_response, indent=2))
        except NoDataReturnedFromSnowflakeException as e:
            logger.error(f"AGENTS /llm-generate-preview error:\n{e.to_dict()}")
            raise HTTPException(
                status_code=404,
                detail="No data returned from Snowflake for the given SQL query.",
            )
        except Exception as e:
            logger.error(f"AGENTS /llm-generate-preview error:\n{str(e)}")
            raise HTTPException(
                status_code=400,
                detail="An error occurred while executing the query. Please check the SQL syntax and rerun the query.",
            )

    return data_list


async def _evaluate_commentary(
    payload: dict,
    section_name: str,
    generated_commentary: str,
    report_id: int | None = None,
) -> dict:
    """Evaluate generated commentary using CommentaryEvaluationService."""
    try:
        service = CommentaryEvaluationService()

        if settings.AGENTS_DEBUG:
            report_payload = payload.get("reportPayload", {}) or {}
            report_parameters = report_payload.get("report_parameters", {}) or {}

            logger.debug("Evaluation debug info - report_id: %s", report_id)
            logger.debug("Evaluation debug info - section_name: %s", section_name)
            logger.debug(
                "Evaluation debug info - automation_mode: %s",
                report_parameters.get("automation_mode"),
            )

        # Extract filters from payload
        report_params = payload.get("reportPayload", {}).get("report_parameters", {})
        section_data = payload.get("reportPayload", {}).get("section", {})

        filters_dict = {
            "section_name": section_name,
            "property_type": section_data.get("property_type"),
            "property_sub_type": section_data.get("property_sub_type"),
            "division": report_params.get("division"),
            "publishing_group": report_params.get("publishing_group"),
            "automation_mode": report_params.get("automation_mode"),
            "quarter": report_params.get("quarter"),
            "history_range": report_params.get("history_range"),
            "absorption_calculation": report_params.get("absorption_calculation"),
            "total_vs_direct_absorption": report_params.get(
                "total_vs_direct_absorption"
            ),
            "asking_rate_frequency": report_params.get("asking_rate_frequency"),
            "asking_rate_type": report_params.get("asking_rate_type"),
        }

        # Remove None values from filters
        filters_dict = {k: v for k, v in filters_dict.items() if v is not None}

        # Include defined_markets if provided
        defined_markets = report_params.get("defined_markets")
        if defined_markets:
            if isinstance(defined_markets, str):
                defined_markets = [defined_markets]
            if isinstance(defined_markets, (list, tuple)) and defined_markets:
                filters_dict["defined_markets"] = [
                    str(m).strip() for m in defined_markets if str(m).strip()
                ]

        result = await service.evaluate_and_save(
            filters=filters_dict,
            generated_commentary=copy.deepcopy(generated_commentary),
            evaluation_types=["factual_correctness"],
            report_id=report_id,
        )

        # Log evaluation results
        scores = result.get("scores", {})
        logger.info(
            "Commentary evaluation scores: %s, for section_name: %s",
            scores,
            section_name,
        )
        logger.info(
            "Commentary evaluation saved to database: %s", result.get("saved", False)
        )

        if result.get("saved_id"):
            logger.info(
                "Commentary evaluation new record ID: %s", result.get("saved_id")
            )
        elif result.get("updated_id"):
            logger.info(
                "Commentary evaluation updated record ID: %s", result.get("updated_id")
            )

        return result

    except Exception as e:
        logger.error("Commentary evaluation error: %s", str(e))
        return {"error": str(e), "scores": {}, "saved": False}


async def _generate_tier1_response(
    section_name: str,
    section_commentary_data: dict,
    data_list: list[str],
    payload: dict,
) -> str:
    """Generate LLM response for tier1 automation mode."""
    if env != "CBRE":
        return "agent generated successfully"

    user_feedback = payload.get("feedback_prompt", None)
    consolidation_prompt = section_commentary_data[section_name].get(
        "adjust_prompt", ""
    )
    sql_prompts = section_commentary_data[section_name].get(
        "commentary_prompt_list", []
    )
    prompt_obj = {
        "consolidation_prompt": consolidation_prompt,
        "sql_prompts": sql_prompts,
    }

    if user_feedback:
        section = SectionRequest(
            section_id=section_name,
            section_name=section_name,
            session_type=section_name,
            input_data=data_list,
            prompt=prompt_obj,
            feedback=json.dumps(user_feedback, indent=2),
        )
    else:
        section = SectionRequest(
            section_id=section_name,
            section_name=section_name,
            session_type=section_name,
            input_data=data_list,
            prompt=prompt_obj,
        )

    sections = [section]
    results = await generate_section_llm(sections)

    if results.get(section_name).error:
        raise RuntimeError(results.get(section_name).error)

    return results.get(section_name).summary_result


async def _generate_tier3_response(section_name: str, report_parameters: dict) -> str:
    """Generate LLM response for tier3 automation mode."""
    logger.info("LLM generation requested in Tier 3 mode")
    normalized_section_name = section_name.replace(" ", "_").lower()

    if env != "CBRE":
        return "Tier3 commentary generated successfully"

    try:
        response = generate_market_narrative(
            report_parameters, paragraph_keys=[normalized_section_name]
        )
        return response.get(
            normalized_section_name,
            "Couldn't generate the commentary, Please try again...",
        )
    except Exception as e:
        logger.error(f"Commentary generation failed in Tier 3 mode: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Commentary generation failed, check section names and try again.",
        )


async def _generate_llm_response(
    automation_mode: str,
    section_name: str,
    section_commentary_data: dict,
    data_list: list[str],
    payload: dict,
    report_parameters: dict,
) -> str:
    """Generate LLM response based on automation mode."""
    try:
        if automation_mode == "tier1":
            return await _generate_tier1_response(
                section_name=section_name,
                section_commentary_data=section_commentary_data,
                data_list=data_list,
                payload=payload,
            )
        elif automation_mode == "tier3":
            normalized_section_name = (
                payload.get("section", {})
                .get("sectionAlias", "")
                .replace(" ", "_")
                .lower()
            )
            return await _generate_tier3_response(
                section_name=normalized_section_name,
                report_parameters=report_parameters,
            )
        else:
            logger.error(
                f"LLM generation requested with unsupported automation_mode: {automation_mode}"
            )
            raise HTTPException(
                status_code=400,
                detail="Invalid automation mode for Commentary generation.",
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("LLM generation failed: %s", e, exc_info=e)
        return "Agent couldn't generate the commentary, Please try again..."


async def _persist_conversation_and_messages(
    session: AsyncSession,
    report_id: int,
    section_key: str,
    payload: dict,
    final_response: str,
    user_email: str | None,
) -> None:
    """Persist conversation and messages for Step 2 interactions."""
    try:
        payload_dict: dict[str, Any] = payload or {}
        report_payload: dict[str, Any] = payload_dict.get("reportPayload") or {}

        # Resolve the report section without mutating any report tables
        report_section: models.ReportSection | None = None
        rs_id = payload_dict.get("report_section_id") or report_payload.get(
            "report_section_id"
        )
        if rs_id:
            try:
                report_section = await session.get(models.ReportSection, int(rs_id))
            except Exception:
                report_section = None

        if report_section is None:
            result = await session.execute(
                select(models.ReportSection)
                .where(models.ReportSection.report_id == report_id)
                .where(
                    (models.ReportSection.key == section_key)
                    | (models.ReportSection.name == section_key)
                )
                .limit(1)
            )
            report_section = result.scalars().first()

        if report_section is None:
            logger.info(
                "llm-generate: no report_section found for report_id=%s section_key=%s; skipping conversation persistence",
                report_id,
                section_key,
            )
        else:
            email = (user_email or "unknown@example.com").strip()
            user = await session.scalar(
                select(models.User).where(models.User.email == email).limit(1)
            )
            if not user:
                user = models.User(
                    email=email,
                    username=email.split("@")[0],
                    is_admin=False,
                )
                session.add(user)
                await session.flush()

            agent_name = f"{section_key} agent"
            stmt = (
                (
                    select(models.AgentConversation)
                    .where(models.AgentConversation.is_active.is_(True))
                    .where(models.AgentConversation.agent_name == agent_name)
                )
                .where(models.AgentConversation.report_id == int(report_id))
                .where(
                    models.AgentConversation.report_section_id == int(report_section.id)
                )
                .order_by(models.AgentConversation.created_at.desc())
                .limit(1)
            )
            existing_conv = await session.execute(stmt)
            conversation = existing_conv.scalars().first()

            if conversation is None:
                conversation = models.AgentConversation(
                    report_id=int(report_id),
                    report_section_id=int(report_section.id),
                    agent_name=agent_name,
                    created_by=user.id,
                    is_active=True,
                    meta={
                        "created_from": "report_step2",
                        "report_id": int(report_id),
                        "section_key": section_key,
                    },
                    last_message_at=datetime.utcnow(),
                )
                session.add(conversation)
                await session.flush()

            # Persist user turn
            default_prompt = (
                (report_payload.get("prompts") or {}).get("default")
                or report_payload.get("default_prompt")
                or payload_dict.get("default_prompt")
            )
            adjust_prompt = payload_dict.get("adjust_prompt") or report_payload.get(
                "adjust_prompt"
            )
            parts: list[str] = []
            if default_prompt:
                parts.append(f"Default prompt:\n{default_prompt}")
            if adjust_prompt:
                parts.append(f"Adjust prompt:\n{adjust_prompt}")
            prev_summary = payload_dict.get("commentary")
            feedback_text = payload_dict.get("feedback")
            if prev_summary and feedback_text:
                parts.append(f"Previous summary:\n{prev_summary}")
                parts.append(f"User feedback:\n{feedback_text}")
            if not parts:
                parts.append("(no prompt provided)")
            user_content = "\n\n".join(parts)

            session.add(
                models.AgentMessage(
                    conversation_id=conversation.id,
                    role="user",
                    content=user_content,
                    payload={
                        "charts": report_payload.get("charts", [])
                        or payload_dict.get("charts_data")
                        or [],
                        "tables": report_payload.get("tables", [])
                        or payload_dict.get("tables_data")
                        or [],
                    },
                    created_by=user.id,
                )
            )

            session.add(
                models.AgentMessage(
                    conversation_id=conversation.id,
                    role="agent",
                    content=final_response or "",
                    payload={"format": "plain"},
                )
            )

            conversation.last_message_at = datetime.utcnow()
            await session.commit()
    except Exception as persist_err:
        logger.warning(
            "llm-generate: failed to persist conversation/messages: %s", persist_err
        )
        try:
            await session.rollback()
        except Exception:
            pass


@router.post("/{report_id}/sections/{section_key}/llm-generate")
async def llm_generate_for_section(
    report_id: int,
    section_key: str,
    request: Request = None,
    session: AsyncSession = Depends(get_session),
    stream: bool = Query(default=False),
    claims: dict | None = Depends(require_auth),
):
    """Build a complete input dictionary for a single report section from DB
    (including charts/tables/prompt and report configuration), pass it to
    generate_section_llm, and return the string output.

    - section_key matches either ReportSection.key or .name (case-sensitive).
    - Returns: { "text": "agent generated successfully" }
    """
    # Parse and validate request payload
    payload = await _parse_llm_request_payload(request)
    current_user = await get_user_from_claims(session, claims)
    current_user_email = _current_user_email(claims, current_user)

    # Initialize variables
    section_commentary_data = {}
    confidence_result = {}
    final_response = ""

    logger.info(
        f"AGENTS /llm-generate-preview request received with following details:\n"
        f"report_id: {report_id}\n"
        f"section_key: {section_key}\n"
        f"payload: {payload}\n"
    )

    # Extract automation mode and report parameters
    report_payload = payload.get("reportPayload", {})
    report_parameters = report_payload.get("report_parameters", {})
    automation_mode = report_parameters.get("automation_mode", "tier1")

    # If run_quarter is "Dynamic", calculate the latest complete quarter
    actual_quarter = report_parameters.get("quarter")
    run_quarter = report_parameters.get("run_quarter")
    if run_quarter and run_quarter.lower() == "dynamic":
        actual_quarter = get_latest_complete_quarter()
        logger.info(
            f"Report {report_id} has Dynamic run_quarter. Using latest complete quarter: {actual_quarter}"
        )
    report_parameters["quarter"] = actual_quarter

    # If streaming is requested (tier1 only), send SSE with LangGraph events
    if stream and automation_mode == "tier1":
        # Extract commentary inputs
        section_name = payload["section"].get("name")
        elements = payload["section"].get("elements", [])
        section_commentary_data = _extract_tier1_commentary_data(section_name, elements)
        commentary_sql_list = section_commentary_data[section_name].get(
            "commentary_sql_list", []
        )

        # Non‑CBRE environments: stream a minimal start/done sequence with dummy text
        if env != "CBRE":

            async def _dummy_stream():
                # start
                completion_json = {
                    "state": {
                        "node": "summary_generation_successful",
                        "status": "end",
                        "description": "Summary generation successful!",
                        "summary_result": "agent generated successfully",
                    }
                }
                yield (
                    "event: agent_status\n"
                    + f"data: {json.dumps(completion_json, default=str)}\n\n"
                )
                # done
                confidence_metric_payload = {
                    "state": {
                        "node": "confidence_metric_calculation",
                        "status": "end",
                        "description": "Confidence metric calculation successful!",
                        "confidence_metric_details": {"confidence_score": 100},
                    }
                }
                yield (
                    "event: agent_status\n"
                    + f"data: {json.dumps(confidence_metric_payload, default=str)}\n\n"
                )

            return StreamingResponse(_dummy_stream(), media_type="text/event-stream")

        # Render SQL and fetch Snowflake data
        data_list = []
        try:
            if commentary_sql_list:
                data_list = _fetch_snowflake_data_for_section(
                    commentary_sql_list, payload["reportPayload"]
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.error("llm-generate[stream] SQL/Snowflake error: %s", str(e))
            raise HTTPException(
                status_code=400, detail="Failed to fetch data for streaming"
            )

        # if data_list and isinstance(data_list, list):
        #     original_data_list = data_list.copy()
        #     try:
        #         transformer = DataTransformer()
        #         transformed_data_list: list[str] = []
        #         for idx, raw in enumerate(data_list):
        #             try:
        #                 parsed = json.loads(raw) if isinstance(raw, str) else raw
        #                 processed = transformer.process(parsed)
        #                 # Keep schema contract: list of JSON strings
        #                 transformed_data_list.append(json.dumps(processed, indent=2))
        #             except Exception as err:
        #                 logger.warning("Data transform skipped index %d: %s", idx, err)
        #                 # Preserve original item so downstream still has data
        #                 transformed_data_list.append(raw)
        #         data_list = transformed_data_list
        #     except Exception as e:
        #         logger.error("Error in data transformation: %s", str(e))
        #         data_list = original_data_list  # Fallback to original data

        # Build SectionRequest (include feedback when provided)
        user_feedback = payload.get("feedback_prompt", None)
        consolidation_prompt = section_commentary_data[section_name].get(
            "adjust_prompt", ""
        )
        sql_prompts = section_commentary_data[section_name].get(
            "commentary_prompt_list", []
        )
        prompt_obj = {
            "consolidation_prompt": consolidation_prompt,
            "sql_prompts": sql_prompts,
        }
        # Ensure at least one input string for single‑run path
        safe_input_list = data_list if (data_list and len(data_list) > 0) else ["[]"]
        if user_feedback:
            section_req = SectionRequest(
                section_id=section_name,
                section_name=section_name,
                session_type=section_name,
                input_data=safe_input_list,
                prompt=prompt_obj,
                feedback=json.dumps(user_feedback, indent=2),
            )
        else:
            section_req = SectionRequest(
                section_id=section_name,
                section_name=section_name,
                session_type=section_name,
                input_data=safe_input_list,
                prompt=prompt_obj,
            )

        if not workflow_service.is_parallel_ready():
            raise HTTPException(
                status_code=503,
                detail="Parallel multi-agent workflow service is not ready",
            )
        graph = workflow_service.get_compiled_parallel_workflow()
        if graph is None:
            raise HTTPException(
                status_code=503, detail="Parallel workflow is unavailable"
            )

        start_time = time.time()
        initial_state = {
            "processing_mode": "parallel",
            "sections": [section_req.model_dump()],
            "section_results": {},
            "completed_sections": [],
            "failed_sections": [],
            "messages": [],
            "parallel_start_time": start_time,
        }

        async def event_generator():
            loop = asyncio.get_running_loop()
            queue: asyncio.Queue = asyncio.Queue(maxsize=256)
            final_state_holder = {"state": None}

            def _produce():
                try:
                    for chunk, mode, state in graph.stream(
                        initial_state, stream_mode=["custom", "values"], subgraphs=True
                    ):
                        msg = {"type": mode, "state": state}
                        if mode == "values":
                            final_state_holder["state"] = state
                        asyncio.run_coroutine_threadsafe(queue.put(msg), loop)
                except Exception as e:
                    asyncio.run_coroutine_threadsafe(
                        queue.put({"type": "error", "error": str(e)}), loop
                    )
                finally:
                    asyncio.run_coroutine_threadsafe(queue.put({"type": "done"}), loop)

            producer_task = asyncio.create_task(asyncio.to_thread(_produce))
            try:
                while True:
                    event = await queue.get()
                    et = event.get("type")
                    if et == "values":
                        continue
                    if et == "done":
                        # Compute final text (from final values state if available)
                        final_text = ""
                        try:
                            st = final_state_holder.get("state") or {}
                            section_results = (st or {}).get("section_results") or {}
                            section_out = section_results.get(section_name) or {}
                            # If section reported an error, surface it as SSE error and stop
                            final_text = section_out.get("summary_result")
                            if section_out.get("error"):
                                # payload = {"error": section_out.get("error")}
                                # yield "event: error\n" + f"data: {json.dumps(payload, default=str)}\n\n"
                                if final_text:
                                    final_text = "Need Human Review:\n\n" + final_text
                                completion_json = {
                                    "state": {
                                        "node": "summary_generation_successful",
                                        "status": "end",
                                        "description": "Summary generation successful!",
                                        "summary_result": final_text,
                                    }
                                }
                                yield (
                                    "event: agent_status\n"
                                    + f"data: {json.dumps(completion_json, default=str)}\n\n"
                                )
                                break
                            completion_json = {
                                "state": {
                                    "node": "summary_generation_successful",
                                    "status": "end",
                                    "description": "Summary generation successful!",
                                    "summary_result": final_text,
                                }
                            }
                            yield (
                                "event: agent_status\n"
                                + f"data: {json.dumps(completion_json, default=str)}\n\n"
                            )
                        except Exception as e:
                            logger.error(
                                f"AGENTS /llm-generate-preview[stream] summary result error: {str(e)}"
                            )
                            completion_json = {
                                "state": {
                                    "node": "summary_generation_failed",
                                    "status": "error",
                                    "description": "Summary generation failed!",
                                    "summary_result": final_text,
                                }
                            }
                            yield (
                                "event: agent_status\n"
                                + f"data: {json.dumps(completion_json, default=str)}\n\n"
                            )
                            payload_err = {"error": str(e)}
                            yield (
                                "event: error\n"
                                + f"data: {json.dumps(payload_err, default=str)}\n\n"
                            )
                            break

                        # Optionally evaluate and persist before signaling completion
                        async def _background_evaluate_and_persist():
                            try:
                                if (
                                    automation_mode == "tier1"
                                    and final_text
                                    and final_text.strip()
                                ):
                                    await _evaluate_commentary(
                                        payload=payload,
                                        section_name=section_name,
                                        generated_commentary=final_text,
                                        report_id=report_id,
                                    )
                                    await _persist_conversation_and_messages(
                                        session=session,
                                        report_id=report_id,
                                        section_key=section_key,
                                        payload=payload,
                                        final_response=final_text,
                                        user_email=current_user_email,
                                    )
                            except Exception as persist_err:
                                logger.warning(
                                    "stream persist/eval failed: %s", persist_err
                                )

                        # Create background task - don't await it
                        asyncio.create_task(_background_evaluate_and_persist())

                        # Confidence metric (mirror non-streaming behavior)
                        confidence_metric_details = {}
                        try:
                            if (
                                env == "CBRE"
                                and final_text
                                and final_text
                                != "Agent couldn't generate the commentary, Please try again..."
                            ):
                                confidence_metric_payload = {
                                    "state": {
                                        "node": "confidence_metric_calculation",
                                        "status": "start",
                                        "description": "Confidence metric calculation started!",
                                    }
                                }
                                yield (
                                    "event: agent_status\n"
                                    + f"data: {json.dumps(confidence_metric_payload, default=str)}\n\n"
                                )
                                cm = ConfidenceMetric(final_text, data_list)
                                cm_result = await cm.get_confidence_metric_pydantic(
                                    section_name=section_name
                                )
                                if hasattr(cm_result, "model_dump"):
                                    confidence_metric_details = cm_result.model_dump()
                                elif hasattr(cm_result, "dict"):
                                    confidence_metric_details = cm_result.dict()
                                else:
                                    confidence_metric_details = cm_result
                                try:
                                    score = getattr(cm_result, "confidence_score", None)
                                    verifs = getattr(cm_result, "verifications", None)
                                    score_str = (
                                        f"{score:.4f}"
                                        if isinstance(score, (int, float))
                                        else score
                                    )
                                    factors = (
                                        len(verifs)
                                        if isinstance(verifs, (list, tuple))
                                        else None
                                    )
                                    logger.info(
                                        "Confidence metric score=%s factors=%s",
                                        score_str,
                                        factors,
                                    )
                                    if settings.AGENTS_DEBUG:
                                        logger.info(
                                            "Confidence metric full result for %s: %s",
                                            section_name,
                                            cm_result,
                                        )
                                except Exception:
                                    pass
                                confidence_metric_payload = {
                                    "state": {
                                        "node": "confidence_metric_calculation",
                                        "status": "end",
                                        "description": "Confidence metric calculation successful!",
                                        "confidence_metric_details": confidence_metric_details,
                                    }
                                }
                                yield (
                                    "event: agent_status\n"
                                    + f"data: {json.dumps(confidence_metric_payload, default=str)}\n\n"
                                )
                        except Exception as cm_err:
                            logger.error(
                                "reports llm-generate[stream] confidence metric error",
                                exc_info=cm_err,
                            )
                            confidence_metric_details = {}
                            confidence_metric_payload = {
                                "state": {
                                    "node": "confidence_metric_calculation",
                                    "status": "error",
                                    "description": "Confidence metric calculation failed!",
                                    "confidence_metric_details": confidence_metric_details,
                                }
                            }
                            yield (
                                "event: agent_status\n"
                                + f"data: {json.dumps(confidence_metric_payload, default=str)}\n\n"
                            )
                        break
                    if et == "error":
                        payload_err = {"error": event.get("error")}
                        yield (
                            "event: error\n"
                            + f"data: {json.dumps(payload_err, default=str)}\n\n"
                        )
                        continue
                    yield (
                        "event: agent_status\n"
                        + f"data: {json.dumps(event, default=str)}\n\n"
                    )

            finally:
                try:
                    producer_task.cancel()
                except Exception:
                    pass

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    # Render SQL and fetch Snowflake data
    data_list = []
    # Handle tier1 mode processing
    if automation_mode == "tier1":
        section_name = payload["section"].get("name")
        elements = payload["section"].get("elements", [])

        # Extract commentary data from elements
        section_commentary_data = _extract_tier1_commentary_data(section_name, elements)
        logger.info(f"section_commentary_data: {section_commentary_data}")

        # Fetch data from Snowflake
        commentary_sql_list = section_commentary_data[section_name].get(
            "commentary_sql_list", []
        )
        if commentary_sql_list:
            data_list = _fetch_snowflake_data_for_section(
                commentary_sql_list, payload["reportPayload"]
            )

    # Generate LLM response
    section_name = payload["section"].get("name")

    final_response = await _generate_llm_response(
        automation_mode=automation_mode,
        section_name=section_name,
        section_commentary_data=section_commentary_data,
        data_list=data_list,
        payload=payload,
        report_parameters=report_parameters,
    )

    # Evaluate commentary for tier1 mode (run asynchronously to not block response)
    if (
        automation_mode == "tier1"
        and final_response
        and final_response
        != "Agent couldn't generate the commentary, Please try again..."
    ):
        try:

            async def _run_confidence_metric(
                commentary: str, transformed_data_list: list[Any]
            ):
                """Run the confidence metric and return a plain dict suitable for JSON serialization."""
                try:
                    cm = ConfidenceMetric(commentary, transformed_data_list)
                    result_model = await cm.get_confidence_metric_pydantic(
                        section_name=section_name
                    )  # Pydantic model
                    logger.info(
                        "Confidence metric score=%.4f facts=%d",
                        result_model.confidence_score,
                        len(result_model.verifications),
                    )
                    if hasattr(result_model, "model_dump"):
                        confidence_metric_result = result_model.model_dump()
                    elif hasattr(result_model, "dict"):
                        confidence_metric_result = result_model.dict()
                    else:
                        confidence_metric_result = result_model
                    return confidence_metric_result
                except Exception as err:
                    logger.warning("Confidence metric failed: %s", err)
                    return {}

            eval_task = _evaluate_commentary(
                payload=payload,
                section_name=section_name,
                generated_commentary=final_response,
                report_id=report_id,
            )
            confidence_task = _run_confidence_metric(final_response, data_list)

            # Run both concurrently; errors handled inside tasks so gather shouldn't raise.
            eval_result, confidence_result = await asyncio.gather(
                eval_task, confidence_task, return_exceptions=True
            )

            if settings.AGENTS_DEBUG:
                logger.info(
                    "Confidence metric full result for %s: %s",
                    section_name,
                    confidence_result,
                )
        except Exception as outer_err:
            # Catch any unexpected exception in orchestration to avoid breaking downstream logic
            logger.error(
                "Unexpected failure in concurrent evaluation/confidence metric: %s",
                outer_err,
            )
            logger.debug(
                "Proceeding without blocking subsequent persistence operations."
            )

    # Persist conversation and messages for tier1 mode
    if automation_mode == "tier1":
        await _persist_conversation_and_messages(
            session=session,
            report_id=report_id,
            section_key=section_key,
            payload=payload,
            final_response=final_response,
            user_email=current_user_email,
        )
    return {
        "text": final_response,
        "confidence_metric_details": confidence_result,
    }


@router.get("/", response_model=ReportListResponse)
async def list_reports(
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
    page: int = 1,
    page_size: int = 20,
    q: str | None = None,
    report_type: str | None = None,
    property_type: str | None = None,
    status: str | None = None,
    automation_mode: str | None = None,
    template_name: str | None = None,
    sort_by: str | None = Query(default=None, description="Field to sort by"),
    sort_order: str | None = Query(default="desc", description="asc or desc"),
):
    page = 1 if page is None or page < 1 else int(page)
    page_size = 20 if page_size is None or page_size < 1 else int(page_size)

    # Build permission tree for filtering
    permissions = get_user_permissions_from_claims(claims or {})
    permission_tree = build_permission_tree(permissions)

    # Build base query for filtering
    base_stmt = select(models.Report)
    conds = []
    if q:
        conds.append(models.Report.name.ilike(f"%{q}%"))
    if report_type:
        conds.append(func.lower(models.Report.report_type) == report_type.lower())
    if property_type:
        conds.append(func.lower(models.Report.property_type) == property_type.lower())
    if status:
        conds.append(func.lower(models.Report.status) == status.lower())
    if automation_mode:
        conds.append(
            func.lower(models.Report.automation_mode) == automation_mode.lower()
        )
    if template_name:
        conds.append(models.Report.template_name.ilike(f"%{template_name}%"))
    if conds:
        base_stmt = base_stmt.where(and_(*conds))

    try:
        # Fetch all matching reports for permission filtering
        # Permission filtering must be done in-memory because divisions/markets are JSON arrays
        stmt = base_stmt.options(selectinload(models.Report.sections)).order_by(
            models.Report.updated_at.desc(), models.Report.created_at.desc()
        )
        res = await session.execute(stmt)
        all_reports = res.scalars().unique().all()
    except SQLAlchemyError as e:
        # Graceful first‑run behavior: if tables are missing (UndefinedTableError),
        # return an empty response instead of failing the whole request.
        msg = str(getattr(e, "orig", e)).lower()
        if "undefinedtable" in msg or 'relation "reports" does not exist' in msg:
            logger.warning(
                "Reports table not found; returning empty response (DB uninitialized)"
            )
            return ReportListResponse(totalCount=0, items=[])
        # Otherwise re‑raise through our global error handler
        raise

    # Filter reports by user permissions
    accessible_reports = [
        report
        for report in all_reports
        if user_can_access_report(
            report.division, report.defined_markets, permission_tree
        )
    ]

    user_ids = {
        r.created_by for r in accessible_reports if r.created_by is not None
    } | {r.modified_by for r in accessible_reports if r.modified_by is not None}
    email_map = await get_user_email_map(session, user_ids)

    sort_field = (sort_by or "").strip().lower()
    sort_dir = (sort_order or "desc").strip().lower()
    sort_desc = sort_dir != "asc"

    def _market_value(report: models.Report) -> str:
        if report.defined_markets:
            return ", ".join(dict.fromkeys(report.defined_markets)).lower()
        return ""

    def _sections_count(report: models.Report) -> int:
        return len(
            [
                section
                for section in getattr(report, "sections", [])
                if getattr(section, "selected", True)
            ]
        )

    def _sort_key(report: models.Report):
        if sort_field == "name":
            return (report.name or "").lower()
        if sort_field == "template_name":
            return (report.template_name or "").lower()
        if sort_field == "automation_mode":
            return (report.automation_mode or "").lower()
        if sort_field == "sections":
            return _sections_count(report)
        if sort_field == "status":
            return (report.status or "").lower()
        if sort_field == "schedule_status":
            return (report.schedule_status or "").lower()
        if sort_field == "property_type":
            return (report.property_type or "").lower()
        if sort_field == "market":
            return _market_value(report)
        if sort_field == "created_at":
            return report.created_at or datetime.min
        if sort_field == "updated_at":
            return report.updated_at or datetime.min
        if sort_field == "created_by":
            return (email_map.get(report.created_by or -1, "") or "").lower()
        if sort_field == "updated_by":
            return (email_map.get(report.modified_by or -1, "") or "").lower()
        return report.updated_at or report.created_at or datetime.min

    if accessible_reports:
        if sort_field:
            accessible_reports.sort(key=_sort_key, reverse=sort_desc)
        else:
            accessible_reports.sort(
                key=lambda r: r.updated_at or r.created_at or datetime.min,
                reverse=True,
            )

    # Calculate total count after permission filtering
    total_count = len(accessible_reports)

    # Apply pagination to filtered results
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_reports = accessible_reports[start_idx:end_idx]

    items: list[ReportListOut] = []
    for report in paginated_reports:
        sections = [section.name for section in report.sections if section.selected]
        market = None
        if report.defined_markets:
            market = ", ".join(dict.fromkeys(report.defined_markets))

        items.append(
            ReportListOut(
                id=report.id,
                name=report.name,
                template_name=report.template_name,
                sections=sections,
                status=report.status,
                schedule_status=report.schedule_status,
                automation_mode=report.automation_mode,
                property_type=report.property_type,
                property_sub_type=report.property_sub_type,
                market=market,
                created_at=report.created_at,
                updated_at=report.updated_at,
                ppt_url=report.ppt_url,
                created_by_email=email_map.get(report.created_by or -1),
                modified_by_email=email_map.get(report.modified_by or -1),
            )
        )

    return ReportListResponse(totalCount=total_count, items=items)


@router.post("/bulk-delete")
async def bulk_delete_reports(
    payload: dict,
    session: AsyncSession = Depends(get_session),
):
    ids = payload.get("ids", [])
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="ids list is required")
    numeric_ids = [
        int(i) for i in ids if isinstance(i, (int, str)) and str(i).isdigit()
    ]
    if not numeric_ids:
        raise HTTPException(status_code=400, detail="No valid ids provided")
    try:
        result = await session.execute(
            delete(models.Report).where(models.Report.id.in_(numeric_ids))
        )
        await session.commit()
        return {"deleted": result.rowcount or 0}
    except Exception as err:
        await session.rollback()
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise


@router.post("/draft")
async def create_draft(payload: ReportConfigIn):
    try:
        result = await generate_first_draft(payload.model_dump())
        return result
    except Exception as err:
        raise HTTPException(status_code=500, detail="Failed to generate draft") from err


@router.post("/finalize")
async def finalize_report(
    payload: ReportConfigIn,
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
):
    """Generate the report using the pipeline, upload to S3, persist a GeneratedReport row,
    and (optionally) send notifications.
    """
    try:
        logger.info(
            "[Finalize Report] name=%s automation=%s markets=%s sections=%s",
            payload.name,
            payload.automation_mode,
            payload.defined_markets,
            list((payload.sections or {}).keys())
            if isinstance(payload.sections, dict)
            else None,
        )
        current_user = await get_user_from_claims(session, claims)
        current_user_id = current_user.id if current_user else None
        current_user_email = _current_user_email(claims, current_user)

        # Run pipeline and save to S3
        logger.debug("[Finalize Report] generating draft")
        draft = await generate_first_draft(payload.model_dump())
        s3_path = await save_final_report_to_s3(draft)
        logger.info("[Finalize Report] saved draft to S3: %s", s3_path)

        # Ensure a Report entry exists; if not, create a minimal one with status Final.
        # The Report model has several required fields; fill sensible defaults when missing.
        trimmed_name = (payload.name or "").strip() or "Untitled Report"
        defined_markets = payload.defined_markets or (
            [payload.market] if payload.market else []
        )
        automation_mode_value = _normalize_mode(payload.automation_mode)
        existing_report = await session.scalar(
            select(models.Report).where(models.Report.name == trimmed_name).limit(1)
        )
        created_new_report = False
        report_created_by: int | None = current_user_id
        if not existing_report:
            logger.debug(
                "[Finalize Report] creating new Report row for %s", trimmed_name
            )
            report = models.Report(
                name=trimmed_name,
                template_id=None,
                template_name=payload.report_type,
                report_type=payload.report_type,
                prompt_template_id=None,
                prompt_template_label=None,
                division="Unknown",
                publishing_group="Published",
                property_type=payload.property_type or "Unknown",
                property_sub_type=getattr(payload, "property_sub_type", None),
                automation_mode=automation_mode_value,
                quarter=None,
                history_range=None,
                absorption_calculation=None,
                total_vs_direct_absorption=None,
                asking_rate_frequency=None,
                asking_rate_type=None,
                minimum_transaction_size=None,
                use_auto_generated_text=True,
                defined_markets=list(dict.fromkeys(defined_markets)),
                status="Final",
                schedule_status=(
                    "N/A" if automation_mode_value == "tier1" else "unscheduled"
                ),
                created_by=current_user_id,
                modified_by=current_user_id,
            )
            session.add(report)
            await session.commit()
            await session.refresh(report)
            report_id_for_run = report.id
            created_new_report = True
            report_created_by = report.created_by
        else:
            logger.debug("[Finalize Report] updating existing report %s", trimmed_name)
            existing_report.status = "Final"
            existing_report.schedule_status = (
                "N/A" if automation_mode_value == "tier1" else "unscheduled"
            )
            existing_report.defined_markets = list(dict.fromkeys(defined_markets))
            if automation_mode_value:
                existing_report.automation_mode = automation_mode_value
            new_sub_type = getattr(payload, "property_sub_type", None)
            if new_sub_type is not None:
                existing_report.property_sub_type = new_sub_type
            if current_user_id:
                existing_report.modified_by = current_user_id
                # Don't backfill created_by for historical reports
            await session.commit()
            report_id_for_run = existing_report.id
            report_created_by = existing_report.created_by or current_user_id

        rec = models.GeneratedReport(
            report_id=report_id_for_run,
            status="Final",
            s3_path=s3_path,
            trigger_source="manual",
            created_by=current_user_id,
        )
        session.add(rec)
        await session.commit()
        await session.refresh(rec)

        # If we just created a new report record, attach minimal sections for this run
        sections_created_successfully = not created_new_report
        if created_new_report:
            sections_map = (
                payload.sections if isinstance(payload.sections, dict) else {}
            )
            display_order = 0
            created_sections: list[models.ReportSection] = []
            for sec_name, conf in sections_map.items():
                section = models.ReportSection(
                    report_id=report_id_for_run,
                    key=str(sec_name),
                    name=str(sec_name),
                    sectionname_alias=str(sec_name),
                    display_order=display_order,
                    selected=True,
                    prompt_template_id=None,
                    prompt_template_label=None,
                    prompt_template_body=None,
                )
                display_order += 1

                element_models: list[models.ReportSectionElement] = []
                if isinstance(conf, dict):
                    prompt_text = conf.get("prompt")
                    if prompt_text:
                        element_models.append(
                            models.ReportSectionElement(
                                element_type="commentary",
                                label="Commentary",
                                selected=True,
                                display_order=0,
                                config={
                                    "commentary_json": prompt_text,
                                    "sql_list": [],
                                    "prompt_list": [],
                                },
                                # Store to the new column as well
                                section_commentary=prompt_text,
                                prompt_text=None,
                            )
                        )

                section.elements = element_models
                session.add(section)
                created_sections.append(section)

            try:
                await session.commit()
                sections_created_successfully = bool(created_sections)
            except Exception:
                await session.rollback()
                sections_created_successfully = False
                raise

        is_unattended = automation_mode_value == "tier3"

        if not is_unattended:
            try:
                sections_list = []
                if isinstance(payload.sections, dict):
                    sections_list = list(payload.sections.keys())
                run = models.ReportRun(
                    report_id=report_id_for_run,
                    trigger_source="manual",
                    created_by=current_user_id or report_created_by,
                    run_time_seconds=rec.duration_seconds,
                    report_name=trimmed_name,
                    report_type=payload.report_type,
                    market=payload.market,
                    sections={"selected": sections_list},
                    status="Success",
                    run_state="completed",
                    output_format="ppt",
                    ppt_url=None,
                )
                session.add(run)
                await session.commit()
            except Exception as run_err:
                logger.exception(
                    "[Finalize Report] failed to persist report run", exc_info=run_err
                )

        # Save any provided final prompts (if frontend sends them) only when sections were created
        if sections_created_successfully:
            try:
                sec = (
                    (payload.sections or {})
                    if isinstance(payload.sections, dict)
                    else {}
                )
                prompts_payload: list[dict] = []
                for sec_name, conf in sec.items():
                    body = (conf or {}).get("prompt")
                    if body:
                        prompts_payload.append(
                            {
                                "section": sec_name,
                                "label": f"Final - {sec_name}",
                                "body": body,
                                "property_type": payload.property_type,
                                "market": payload.market,
                                "status": "Final",
                                "is_default": False,
                                "author": current_user_email,
                            }
                        )
                if prompts_payload:
                    await save_prompts(session, prompts_payload)
            except Exception as prompt_err:
                logger.exception(
                    "[Finalize Report] failed to save prompts", exc_info=prompt_err
                )

        # Notifications: current user only (subscriptions removed)
        try:
            recipients = set([current_user_email] if current_user_email else [])
            if not recipients:
                recipients.add("demo@example.com")
            delivery_details = await send_report_notification(
                sorted(recipients), s3_path, report_name=trimmed_name
            )
            success_count = sum(1 for s in delivery_details.values() if s == "Success")
            logger.info(
                "[Finalize Report] Email delivery: %d/%d successful. Details: %s",
                success_count,
                len(delivery_details),
                delivery_details,
            )
        except Exception as notify_err:
            logger.exception(
                "[Finalize Report] failed to send notifications", exc_info=notify_err
            )

        return {
            "generated_report_id": rec.id,
            "report_id": report_id_for_run,
            "s3_path": s3_path,
        }
    except Exception as err:
        logger.exception("[Finalize Report] unexpected error", exc_info=err)
        # Try to persist failed record for auditing
        try:
            rec = models.GeneratedReport(report_id=None, status="Failed")
            session.add(rec)
            await session.commit()
        except SQLAlchemyError as db_err:
            await handle_db_error(session, db_err)
        raise HTTPException(
            status_code=500, detail="Failed to finalize report"
        ) from err


@router.get("/history", response_model=ReportHistoryListResponse)
async def list_history(
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
    page: int = 1,
    page_size: int = 20,
    q: str | None = None,
    report_type: str | None = None,
    market: str | None = None,
    property_type: str | None = None,
    status: str | None = None,
    trigger_source: str | None = None,
):
    page = 1 if page is None or page < 1 else int(page)
    page_size = 20 if page_size is None or page_size < 1 else int(page_size)

    # Build permission tree for filtering
    permissions = get_user_permissions_from_claims(claims or {})
    permission_tree = build_permission_tree(permissions)

    rr = aliased(models.ReportRun)
    rpt = aliased(models.Report)

    # Include division and defined_markets from Report for permission filtering
    base_stmt = (
        select(
            rr.id,
            rr.report_id,
            rr.report_name,
            rr.report_type,
            rr.market,
            rr.property_type,
            rr.property_sub_type,
            rr.created_at,
            rr.status,
            rr.run_state,
            rr.trigger_source,
            rr.output_format.label("output_formats"),
            rr.duration_seconds,
            rr.s3_path,
            rr.created_by,
            rr.schedule_id,
            rpt.division.label("report_division"),
            rpt.defined_markets.label("report_markets"),
        )
        .select_from(rr)
        .join(rpt, rpt.id == rr.report_id, isouter=True)
    )

    conds = []
    if q:
        conds.append(rr.report_name.ilike(f"%{q}%"))
    if report_type:
        conds.append(func.lower(rr.report_type) == report_type.lower())
    if market:
        conds.append(rr.market.ilike(f"%{market}%"))
    if property_type:
        conds.append(func.lower(rr.property_type) == property_type.lower())
    if status:
        conds.append(func.lower(rr.status) == status.lower())
    if trigger_source:
        conds.append(func.lower(rr.trigger_source) == trigger_source.lower())
    if conds:
        base_stmt = base_stmt.where(and_(*conds))

    # Fetch all rows for permission filtering
    stmt = base_stmt.order_by(rr.created_at.desc())
    res = await session.execute(stmt)
    all_rows = res.mappings().all()

    # Filter by user permissions
    accessible_rows = [
        row
        for row in all_rows
        if user_can_access_report(
            row.get("report_division"), row.get("report_markets"), permission_tree
        )
    ]

    # Calculate total count after permission filtering
    total_count = len(accessible_rows)

    # Apply pagination to filtered results
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_rows = accessible_rows[start_idx:end_idx]

    row_dicts = [dict(row) for row in paginated_rows]
    email_map = await get_user_email_map(
        session,
        {rd.get("created_by") for rd in row_dicts if rd.get("created_by") is not None},
    )
    items: list[ReportRunOut] = []
    for row_dict in row_dicts:
        # Remove permission-related fields from response
        row_dict.pop("report_division", None)
        row_dict.pop("report_markets", None)
        created_by_val = row_dict.pop("created_by", None)
        row_dict["created_by_email"] = email_map.get(created_by_val or -1)
        items.append(ReportRunOut(**row_dict))
    return ReportHistoryListResponse(totalCount=total_count, items=items)

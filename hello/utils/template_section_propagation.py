from __future__ import annotations

import copy
from collections import defaultdict
from typing import Any, Iterable, Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from hello import models
from hello.ml.logger import GLOBAL_LOGGER as logger

DEFAULT_EXCLUDED_REPORT_STATUSES: tuple[str, ...] = ("finalized", "published", "archived")
_CONFIG_PRESERVE_KEYS = {"commentary_json", "prompt_list"}
_SECTION_META_FIELDS = (
    "property_type",
    "property_sub_type",
    "division",
    "publishing_group",
    "automation_mode",
    "quarter",
    "history_range",
    "absorption_calculation",
    "total_vs_direct_absorption",
    "asking_rate_frequency",
    "asking_rate_type",
    "minimum_transaction_size",
)
_SECTION_META_LIST_FIELDS = ("vacancy_index", "submarket", "district")


def _normalize_key(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None


def _split_markets(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = [part.strip() for part in raw.split(",")]
        return [part for part in parts if part]
    if isinstance(raw, (list, tuple, set)):
        normalized: list[str] = []
        for value in raw:
            if value is None:
                continue
            candidate = str(value).strip()
            if candidate:
                normalized.append(candidate)
        return normalized
    candidate = str(raw).strip()
    return [candidate] if candidate else []


def _section_metadata(section: models.TemplateSection) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for field in _SECTION_META_FIELDS:
        metadata[field] = getattr(section, field, None)
    for field in _SECTION_META_LIST_FIELDS:
        value = getattr(section, field, None)
        metadata[field] = list(value or []) if isinstance(value, (list, tuple)) else (value or [])
    markets = _split_markets(getattr(section, "markets", None))
    metadata["markets"] = markets
    metadata["defined_markets"] = markets
    metadata["section_name"] = getattr(section, "name", None)
    metadata["section_alias"] = getattr(section, "sectionname_alias", None) or metadata["section_name"]
    report_params = getattr(section, "report_parameters", None)
    if isinstance(report_params, dict):
        metadata["report_parameters"] = copy.deepcopy(report_params)
    else:
        metadata["report_parameters"] = report_params
    metadata["tier"] = getattr(section, "tier", None)
    return metadata


def _element_identity_key(element: Any) -> tuple[str | None, str | None] | None:
    """Return a stable (type, label) identifier to align template/report elements."""
    element_type = _normalize_key(getattr(element, "element_type", None))
    label_value: str | None = None
    config = getattr(element, "config", None)
    if isinstance(config, dict):
        for candidate_key in ("label", "name", "section_name"):
            candidate_val = config.get(candidate_key)
            if isinstance(candidate_val, str) and candidate_val.strip():
                label_value = candidate_val
                break
    if not label_value:
        attr_val = getattr(element, "label", None)
        if isinstance(attr_val, str) and attr_val.strip():
            label_value = attr_val
    normalized_label = _normalize_key(label_value)
    if element_type is None and normalized_label is None:
        return None
    return (element_type, normalized_label)


def _report_section_name_keys(section: models.ReportSection) -> set[str]:
    """Collect normalized names/aliases for a report section."""
    keys = {
        _normalize_key(getattr(section, "name", None)),
        _normalize_key(getattr(section, "sectionname_alias", None)),
        _normalize_key(getattr(section, "key", None)),
    }
    keys.discard(None)
    return keys


def _merge_element_config(
    template_section: models.TemplateSection,
    template_element: models.TemplateSectionElement,
    existing_config: dict | None,
    *,
    update_all_fields: bool,
) -> dict[str, Any]:
    base_cfg = copy.deepcopy(template_element.config or {})
    section_meta = _section_metadata(template_section)
    base_cfg.update({key: value for key, value in section_meta.items() if value not in (None, [], {})})
    if not update_all_fields and isinstance(existing_config, dict):
        for key in _CONFIG_PRESERVE_KEYS:
            if key in existing_config and existing_config[key] not in (None, "", [], {}):
                base_cfg[key] = existing_config[key]
    return base_cfg


def _report_section_matches_template(
    report_section: models.ReportSection, template_section: models.TemplateSection
) -> bool:
    template_keys = {
        _normalize_key(getattr(template_section, "name", None)),
        _normalize_key(getattr(template_section, "sectionname_alias", None)),
    }
    template_keys.discard(None)
    if not template_keys:
        return False
    candidates = {
        _normalize_key(getattr(report_section, "name", None)),
        _normalize_key(getattr(report_section, "sectionname_alias", None)),
        _normalize_key(getattr(report_section, "key", None)),
    }
    candidates.discard(None)
    return bool(template_keys.intersection(candidates))


def _update_report_section_from_template(
    report_section: models.ReportSection,
    template_section: models.TemplateSection,
) -> bool:
    updated = False
    new_name = getattr(template_section, "name", None)
    if new_name and new_name != report_section.name:
        report_section.name = new_name
        updated = True
    new_alias = getattr(template_section, "sectionname_alias", None) or new_name
    if new_alias and new_alias != report_section.sectionname_alias:
        report_section.sectionname_alias = new_alias
        updated = True
    layout_preference = getattr(template_section, "slide_layout", None)
    if layout_preference != getattr(report_section, "layout_preference", None):
        report_section.layout_preference = layout_preference
        updated = True
    return updated


async def _update_report_section_elements(
    session: AsyncSession,
    report_section: models.ReportSection,
    template_section: models.TemplateSection,
    *,
    update_all_fields: bool,
) -> bool:
    template_elements = sorted(
        list(getattr(template_section, "elements", []) or []),
        key=lambda elem: getattr(elem, "display_order", 0),
    )
    report_elements = sorted(
        list(getattr(report_section, "elements", []) or []),
        key=lambda elem: getattr(elem, "display_order", 0),
    )

    buckets: dict[tuple[str | None, str | None] | None, list[models.ReportSectionElement]] = defaultdict(list)
    remaining: list[models.ReportSectionElement] = []
    for elem in report_elements:
        key = _element_identity_key(elem)
        buckets[key].append(elem)
        remaining.append(elem)

    def _pop_by_key(key: tuple[str | None, str | None] | None) -> models.ReportSectionElement | None:
        bucket = buckets.get(key)
        if bucket:
            match = bucket.pop(0)
            if match in remaining:
                remaining.remove(match)
            return match
        return None

    def _pop_any() -> models.ReportSectionElement | None:
        if not remaining:
            return None
        match = remaining.pop(0)
        bucket = buckets.get(_element_identity_key(match))
        if bucket and match in bucket:
            bucket.remove(match)
        return match

    changed = False

    for idx, template_element in enumerate(template_elements):
        report_element = _pop_by_key(_element_identity_key(template_element))
        if report_element is None:
            report_element = _pop_any()

        if report_element is None:
            new_element = models.ReportSectionElement(
                report_section_id=report_section.id,
                element_type=template_element.element_type,
                display_order=idx,
                config=_merge_element_config(
                    template_section,
                    template_element,
                    None,
                    update_all_fields=update_all_fields,
                ),
                selected=True,
            )
            session.add(new_element)
            report_section.elements.append(new_element)
            changed = True
            continue

        new_config = _merge_element_config(
            template_section,
            template_element,
            report_element.config,
            update_all_fields=update_all_fields,
        )
        if report_element.element_type != template_element.element_type:
            report_element.element_type = template_element.element_type
            changed = True
        if report_element.display_order != idx:
            report_element.display_order = idx
            changed = True
        if report_element.config != new_config:
            report_element.config = new_config
            changed = True

    if remaining:
        for extra in list(remaining):
            if extra in report_section.elements:
                report_section.elements.remove(extra)
            await session.delete(extra)
            changed = True

    report_section.elements.sort(key=lambda elem: getattr(elem, "display_order", 0))
    return changed


async def _load_template_section(
    session: AsyncSession, template_section_id: int
) -> models.TemplateSection | None:
    stmt = (
        select(models.TemplateSection)
        .execution_options(populate_existing=True)
        .options(
            selectinload(models.TemplateSection.templates),
            selectinload(models.TemplateSection.elements),
        )
        .where(models.TemplateSection.id == template_section_id)
    )
    result = await session.execute(stmt)
    return result.scalars().first()


async def propagate_template_section_changes(
    session: AsyncSession,
    *,
    template_section_id: int | None = None,
    update_all_fields: bool = False,
    exclude_reports_with_status: Iterable[str] | None = None,
    auto_commit: bool = True,
) -> dict[str, Any]:
    """Propagate an updated template section (and its elements) to all matching report sections."""
    if template_section_id is None:
        raise ValueError("template_section_id is required")

    result: dict[str, Any] = {
        "template_section_id": template_section_id,
        "template_section_name": None,
        "reports_examined": 0,
        "reports_affected": 0,
        "sections_updated": 0,
    }
    exclusions = {
        status.strip().lower()
        for status in (exclude_reports_with_status or DEFAULT_EXCLUDED_REPORT_STATUSES)
        if isinstance(status, str)
    }

    try:
        section = await _load_template_section(session, template_section_id)
        if not section:
            logger.warning(
                "propagate_template_section_changes: section_id=%s not found", template_section_id
            )
            return result
        result["template_section_name"] = getattr(section, "name", None)
        template_ids = [tpl.id for tpl in getattr(section, "templates", []) if tpl.id is not None]
        if not template_ids:
            logger.info(
                "propagate_template_section_changes: section_id=%s not linked to any templates",
                template_section_id,
            )
            return result

        stmt = select(models.Report).options(
            selectinload(models.Report.sections).selectinload(models.ReportSection.elements)
        )
        stmt = stmt.where(models.Report.template_id.in_(template_ids))
        if exclusions:
            status_field = func.lower(models.Report.status)
            stmt = stmt.where(~status_field.in_(exclusions))

        reports = (await session.execute(stmt)).scalars().unique().all()
        result["reports_examined"] = len(reports)
        if not reports:
            return result

        logger.info(
            "propagate_template_section_changes: section_id=%s -> %s reports to inspect",
            template_section_id,
            len(reports),
        )

        total_sections_updated = 0
        for report in reports:
            updated_in_report = False
            for report_section in getattr(report, "sections", []) or []:
                if not _report_section_matches_template(report_section, section):
                    continue
                section_changed = _update_report_section_from_template(report_section, section)
                elements_changed = await _update_report_section_elements(
                    session,
                    report_section,
                    section,
                    update_all_fields=update_all_fields,
                )
                if section_changed or elements_changed:
                    updated_in_report = True
                    total_sections_updated += 1
            if updated_in_report:
                result["reports_affected"] += 1

        result["sections_updated"] = total_sections_updated
        if total_sections_updated:
            await session.flush()
            if auto_commit:
                await session.commit()
            logger.info(
                "propagate_template_section_changes: section_id=%s updated %s sections across %s reports",
                template_section_id,
                total_sections_updated,
                result["reports_affected"],
            )
        else:
            if auto_commit:
                await session.rollback()

        return result
    except Exception:
        if auto_commit:
            await session.rollback()
        raise


async def propagate_multiple_template_sections(
    session: AsyncSession,
    template_section_ids: Sequence[int],
    *,
    update_all_fields: bool = False,
    exclude_reports_with_status: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    """Propagate a collection of template sections in a single transaction."""
    results: list[dict[str, Any]] = []
    try:
        for section_id in template_section_ids:
            result = await propagate_template_section_changes(
                session,
                template_section_id=int(section_id),
                update_all_fields=update_all_fields,
                exclude_reports_with_status=exclude_reports_with_status,
                auto_commit=False,
            )
            results.append(result)
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    return results


async def propagate_template_changes(
    session: AsyncSession,
    template_id: int,
    *,
    update_all_fields: bool = False,
    exclude_reports_with_status: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Propagate every section under a template to its associated reports."""
    stmt = (
        select(models.TemplateSection.id)
        .join(models.template_section_association)
        .where(models.template_section_association.c.template_id == template_id)
    )
    section_ids = [row[0] for row in (await session.execute(stmt)).all()]
    if not section_ids:
        return {
            "template_id": template_id,
            "template_name": None,
            "sections_processed": 0,
            "reports_affected": 0,
            "total_sections_updated": 0,
        }

    template = await session.get(models.Template, template_id)
    template_name = getattr(template, "name", None) if template else None
    section_results = await propagate_multiple_template_sections(
        session,
        section_ids,
        update_all_fields=update_all_fields,
        exclude_reports_with_status=exclude_reports_with_status,
    )
    reports_affected = sum(result.get("reports_affected", 0) or 0 for result in section_results)
    sections_updated = sum(result.get("sections_updated", 0) or 0 for result in section_results)
    return {
        "template_id": template_id,
        "template_name": template_name,
        "sections_processed": len(section_ids),
        "reports_affected": reports_affected,
        "total_sections_updated": sections_updated,
    }


async def remove_report_sections_for_template(
    session: AsyncSession,
    template_ids: Sequence[int],
    *,
    section_names: Sequence[str] | None = None,
    exclude_reports_with_status: Iterable[str] | None = None,
    auto_commit: bool = False,
) -> dict[str, int]:
    """Delete report sections tied to the provided templates and section names."""
    template_ids_clean = [int(tid) for tid in template_ids if tid is not None]
    result = {
        "templates": template_ids_clean,
        "sections_removed": 0,
        "reports_affected": 0,
    }
    if not template_ids_clean:
        return result

    normalized_names = {
        key for key in (_normalize_key(name) for name in (section_names or [])) if key
    }
    remove_all = not normalized_names
    exclusions = {
        status.strip().lower()
        for status in (exclude_reports_with_status or DEFAULT_EXCLUDED_REPORT_STATUSES)
        if isinstance(status, str)
    }

    stmt = select(models.Report).options(
        selectinload(models.Report.sections).selectinload(models.ReportSection.elements)
    )
    stmt = stmt.where(models.Report.template_id.in_(template_ids_clean))
    if exclusions:
        status_field = func.lower(models.Report.status)
        stmt = stmt.where(~status_field.in_(exclusions))

    reports = (await session.execute(stmt)).scalars().unique().all()
    if not reports:
        return result

    for report in reports:
        sections_to_remove: list[models.ReportSection] = []
        for section in list(getattr(report, "sections", []) or []):
            keys = _report_section_name_keys(section)
            if remove_all or keys.intersection(normalized_names):
                sections_to_remove.append(section)
        if sections_to_remove:
            for section in sections_to_remove:
                await session.delete(section)
            result["sections_removed"] += len(sections_to_remove)
            result["reports_affected"] += 1

    if auto_commit and result["sections_removed"] > 0:
        await session.commit()

    return result

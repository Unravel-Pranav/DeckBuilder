from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from hello import models


async def _count(session: AsyncSession, model) -> int:
    res = await session.execute(select(func.count()).select_from(model))
    return int(res.scalar() or 0)


async def _get_template_by_name(
    session: AsyncSession, name: str
) -> models.Template | None:
    res = await session.execute(
        select(models.Template).where(models.Template.name == name)
    )
    return res.scalars().first()


def _seed_chart_sql(name: str, property_type: str) -> str:
    base = property_type.lower()
    return (
        f"-- Chart source for {name}"
        f"SELECT quarter, net_absorption"
        f"FROM demo_{base}_market_kpis"
        f"WHERE section = '{name}'"
        "ORDER BY quarter;"
    )


def _seed_table_sql(name: str, property_type: str) -> str:
    base = property_type.lower()
    return (
        f"-- Table source for {name}"
        f"SELECT metric, current_value, prior_value, change_percent"
        f"FROM demo_{base}_market_metrics"
        f"WHERE section = '{name}'"
        "ORDER BY metric;"
    )


def _seed_commentary_sql(name: str, property_type: str) -> str:
    base = property_type.lower()
    return (
        f"-- Commentary context for {name}"
        f"SELECT metric, narrative"
        f"FROM demo_{base}_commentary_inputs"
        f"WHERE section = '{name}'"
        "ORDER BY metric;"
    )


async def _add_section_with_elements(
    session: AsyncSession,
    *,
    template: models.Template,
    name: str,
    property_type: str,
    property_sub_type: str | None = None,
    default_prompt: str,
    chart_sql: str | None = None,
    table_sql: str | None = None,
    commentary_sql: str | None = None,
    commentary_label: str | None = None,
    adjust_prompt: str | None = None,
    mode: str = "Attended",
    slide_layout: str | None = None,
    tier: str | None = None,
    markets: str | None = None,
) -> models.TemplateSection:
    sec = models.TemplateSection(
        name=name,
        sectionname_alias=name,
        property_type=property_type,
        property_sub_type=property_sub_type,
        default_prompt=default_prompt,
        mode=mode,
        slide_layout=slide_layout,
        tier=tier,
        markets=markets,
    )
    sec.templates.append(template)
    session.add(sec)
    await session.flush()

    chart_items: list[dict[str, Any]] = []
    table_items: list[dict[str, Any]] = []
    order = 0

    if chart_sql:
        chart_config = {
            "type": "chart",
            "chart_type": "Line - Single axis",
            "sql": chart_sql,
            "property_type": property_type,
            "property_sub_type": property_sub_type,
            "section_name": name,
            "section_alias": name,
        }
        session.add(
            models.TemplateSectionElement(
                section_id=sec.id,
                element_type="chart",
                display_order=order,
                config=chart_config,
            )
        )
        chart_items.append(
            {
                "chart_type": chart_config["chart_type"],
                "sql": chart_sql,
            }
        )
        order += 1

    if table_sql:
        table_config = {
            "type": "table",
            "include_totals": True,
            "highlight_changes": True,
            "sql": table_sql,
            "property_type": property_type,
            "property_sub_type": property_sub_type,
            "section_name": name,
            "section_alias": name,
        }
        session.add(
            models.TemplateSectionElement(
                section_id=sec.id,
                element_type="table",
                display_order=order,
                config=table_config,
            )
        )
        table_items.append(
            {
                "include_totals": True,
                "highlight_changes": True,
                "sql": table_sql,
            }
        )
        order += 1

    commentary_source_sql = commentary_sql or table_sql or chart_sql or ""
    if commentary_source_sql or default_prompt:
        commentary_config = {
            "type": "commentary",
            "prompt_template_label": commentary_label or f"{name} Commentary",
            "prompt_template_body": default_prompt,
            "adjust_prompt": adjust_prompt or "",
            "sql": commentary_source_sql,
            "property_type": property_type,
            "property_sub_type": property_sub_type,
            "section_name": name,
        }
        session.add(
            models.TemplateSectionElement(
                section_id=sec.id,
                element_type="commentary",
                display_order=order,
                config=commentary_config,
            )
        )

    if chart_items:
        sec.chart_config = {"items": chart_items, "count": len(chart_items)}
    if table_items:
        sec.table_config = {"items": table_items, "count": len(table_items)}

    return sec


async def _ensure_template(
    session: AsyncSession,
    *,
    name: str,
    base_type: str,
    sections: int,
    is_default: bool,
    last_modified: datetime,
    property_type_for_sections: str,
) -> models.Template:
    existing = await _get_template_by_name(session, name)
    if existing:
        # Optionally align flags and timestamp
        changed = False
        if existing.is_default != is_default:
            existing.is_default = is_default
            changed = True
        if existing.attended is None or existing.attended is False:
            existing.attended = True
            changed = True
        if not getattr(existing, "ppt_status", None):
            existing.ppt_status = "Not Attached"
            changed = True
        if getattr(existing, "ppt_attached_time", None) is not None:
            # retain existing timestamp, do nothing
            pass
        # Update last_modified only if differs materially
        try:
            if abs((existing.last_modified - last_modified).total_seconds()) > 1:
                existing.last_modified = last_modified
                changed = True
        except Exception:
            existing.last_modified = last_modified
            changed = True
        if changed:
            await session.flush()
        return existing

    tpl = models.Template(
        name=name,
        base_type=base_type,
        is_default=is_default,
        attended=True,
        ppt_status="Not Attached",
        ppt_attached_time=None,
        last_modified=last_modified,
    )
    session.add(tpl)
    await session.flush()

    # Create simple placeholder sections to reach the desired count
    base_names = [
        "Executive Summary",
        "Market Overview",
        "Vacancy Analysis",
        "Net Absorption",
        "Leasing Activity",
        "Construction Pipeline",
        "Economic Overview",
        "Submarket Analysis",
        "Capital Markets",
        "Asking Rents",
    ]
    for idx in range(sections):
        section_name = base_names[idx % len(base_names)]
        default_prompt = f"Default prompt for {section_name}"
        chart_sql = _seed_chart_sql(section_name, property_type_for_sections)
        table_sql = _seed_table_sql(section_name, property_type_for_sections)
        commentary_sql = _seed_commentary_sql(section_name, property_type_for_sections)
        await _add_section_with_elements(
            session,
            template=tpl,
            name=section_name,
            property_type=property_type_for_sections,
            default_prompt=default_prompt,
            chart_sql=chart_sql,
            table_sql=table_sql,
            commentary_sql=commentary_sql,
            commentary_label=f"{section_name} Narrative",
        )
    return tpl


async def ensure_demo_templates(session: AsyncSession) -> dict[str, Any]:
    """Ensure the four UI demo templates from the screenshot are present.

    - Standard Office Analysis (Office Figures) – 5 sections – default – 2024-12-15 14:30
    - Industrial Market Overview (Industrial Figures) – 7 sections – default – 2024-12-12 09:15
    - Custom Office Deep Dive (Office Figures) – 8 sections – not default – 2024-12-10 16:45
    - Quarterly Industrial Report (Industrial Figures) – 6 sections – not default – 2024-12-08 11:20
    """
    created_or_updated = 0

    items = [
        {
            "name": "Standard Office Analysis",
            "base_type": "Office Figures",
            "sections": 5,
            "is_default": True,
            "last_modified": datetime(2024, 12, 15, 14, 30),
            "ptype": "Office",
        },
        {
            "name": "Industrial Market Overview",
            "base_type": "Industrial Figures",
            "sections": 7,
            "is_default": True,
            "last_modified": datetime(2024, 12, 12, 9, 15),
            "ptype": "Industrial",
        },
        {
            "name": "Custom Office Deep Dive",
            "base_type": "Office Figures",
            "sections": 8,
            "is_default": False,
            "last_modified": datetime(2024, 12, 10, 16, 45),
            "ptype": "Office",
        },
        {
            "name": "Quarterly Industrial Report",
            "base_type": "Industrial Figures",
            "sections": 6,
            "is_default": False,
            "last_modified": datetime(2024, 12, 8, 11, 20),
            "ptype": "Industrial",
        },
    ]

    for it in items:
        before = await _get_template_by_name(session, it["name"])
        await _ensure_template(
            session,
            name=it["name"],
            base_type=it["base_type"],
            sections=it["sections"],
            is_default=it["is_default"],
            last_modified=it["last_modified"],
            property_type_for_sections=it["ptype"],
        )
        after = await _get_template_by_name(session, it["name"])
        if (before is None) or (
            before
            and after
            and (
                before.is_default != after.is_default
                or before.last_modified != after.last_modified
            )
        ):
            created_or_updated += 1

    await session.commit()
    return {"templates_created_or_updated": created_or_updated}


async def ensure_sample_reports(
    session: AsyncSession, admin_user: models.User | None
) -> dict[str, int]:
    """Ensure we have realistic sample report data. Report configs are deprecated."""
    return {
        "report_configs_created": 0,
        "generated_reports_created": 0,
        "schedules_created": 0,
    }


async def seed_if_empty(session: AsyncSession) -> dict[str, Any]:
    """Seed minimal demo data if tables are empty. Safe to call multiple times."""

    templates_created = 0
    prompts_created = 0
    schedules_created = 0
    users_created = 0

    # Users
    admin_user: models.User | None = None
    if await _count(session, models.User) == 0:
        admin_user = models.User(
            email="admin@cbre.com",
            username="Admin User",
            miq_user_id=None,
        )
        analyst = models.User(
            email="analyst@cbre.com",
            username="Analyst One",
            miq_user_id=None,
        )
        nycuser = models.User(
            email="nyc.user@cbre.com",
            username="NYC User",
            miq_user_id=None,
        )
        session.add_all([admin_user, analyst, nycuser])
        users_created = 3
        await session.flush()
    else:
        res = await session.execute(select(models.User).order_by(models.User.id))
        admin_user = res.scalars().first()

    # Templates + sections
    if await _count(session, models.Template) == 0:
        tpl1 = models.Template(
            name="Office Quarterly Template",
            base_type="Office Figures",
            is_default=True,
            attended=True,
            ppt_status="Not Attached",
            ppt_attached_time=None,
        )
        tpl2 = models.Template(
            name="Industrial Quarterly Template",
            base_type="Industrial Figures",
            is_default=False,
            attended=True,
            ppt_status="Not Attached",
            ppt_attached_time=None,
        )
        tpl3 = models.Template(
            name="Office Summary Template",
            base_type="Office Figures",
            is_default=False,
            attended=True,
            ppt_status="Not Attached",
            ppt_attached_time=None,
        )
        session.add_all([tpl1, tpl2, tpl3])
        await session.flush()
        # Sections for Office
        office_sections = [
            ("Executive Summary", "Office", "A short executive summary"),
            ("Market Overview", "Office", "Key market overview prompt"),
            ("Vacancy Analysis", "Office", "Vacancy prompt"),
            ("Net Absorption", "Office", "Absorption prompt"),
            ("Leasing Activity", "Office", "Leasing prompt"),
            ("Construction Pipeline", "Office", "Pipeline prompt"),
        ]
        for name, ptype, prompt in office_sections:
            chart_sql = _seed_chart_sql(name, ptype)
            table_sql = _seed_table_sql(name, ptype)
            commentary_sql = _seed_commentary_sql(name, ptype)
            await _add_section_with_elements(
                session,
                template=tpl1,
                name=name,
                property_type=ptype,
                default_prompt=prompt,
                chart_sql=chart_sql,
                table_sql=table_sql,
                commentary_sql=commentary_sql,
                commentary_label=f"{name} Narrative",
                slide_layout="Title and Content",
            )
        # A couple sections for Industrial
        for name in ("Executive Summary", "Market Overview"):
            prompt = f"{name} default prompt"
            chart_sql = _seed_chart_sql(name, "Industrial")
            table_sql = _seed_table_sql(name, "Industrial")
            commentary_sql = _seed_commentary_sql(name, "Industrial")
            await _add_section_with_elements(
                session,
                template=tpl2,
                name=name,
                property_type="Industrial",
                default_prompt=prompt,
                chart_sql=chart_sql,
                table_sql=table_sql,
                commentary_sql=commentary_sql,
                commentary_label=f"{name} Insights",
                slide_layout="Title",
            )
        # A shorter summary template (2 sections)
        for name in ("Executive Summary", "Net Absorption"):
            prompt = f"Summary for {name}"
            chart_sql = _seed_chart_sql(name, "Office")
            table_sql = _seed_table_sql(name, "Office")
            commentary_sql = _seed_commentary_sql(name, "Office")
            await _add_section_with_elements(
                session,
                template=tpl3,
                name=name,
                property_type="Office",
                default_prompt=prompt,
                chart_sql=chart_sql,
                table_sql=table_sql,
                commentary_sql=commentary_sql,
                commentary_label=f"{name} Summary",
                mode="Unattended",
            )
        templates_created = 3

    # Prompts
    if await _count(session, models.Prompt) == 0:
        body_1 = "Write a concise executive summary for {market} {propertyType} market."
        body_2 = "Provide a market overview with key KPI trends."
        body_3 = "Summarize net absorption and highlight notable tenants."
        body_4 = "Explain changes in vacancy and underlying causes."
        body_5 = "Executive summary for industrial {market} with emphasis on logistics demand."
        body_6 = "Denver market overview with regional factors."

        session.add_all(
            [
                models.Prompt(
                    section="Executive Summary",
                    label="Default Executive Summary",
                    property_type="Office",
                    market="Global",
                    body=body_1,
                    prompt_list=[body_1],
                    status="Active",
                    is_default=True,
                    author="John Doe",
                    tier="tier1",
                    upvotes=48,
                    downvotes=3,
                ),
                models.Prompt(
                    section="Market Overview",
                    label="Default Market Overview",
                    property_type="Office",
                    body=body_2,
                    prompt_list=[body_2],
                    status="Active",
                    is_default=False,
                    author="Jane Smith",
                    tier="tier1",
                    upvotes=35,
                    downvotes=5,
                ),
                models.Prompt(
                    section="Net Absorption",
                    label="Absorption Overview",
                    property_type="Office",
                    body=body_3,
                    prompt_list=[body_3],
                    status="Active",
                    author="Michael Chen",
                    tier="tier2",
                    upvotes=22,
                    downvotes=2,
                ),
                models.Prompt(
                    section="Vacancy Analysis",
                    label="Vacancy Deep Dive",
                    property_type="Office",
                    body=body_4,
                    prompt_list=[body_4],
                    status="Active",
                    author="Emma Davis",
                    tier="tier2",
                    upvotes=28,
                    downvotes=1,
                ),
                models.Prompt(
                    section="Executive Summary",
                    label="Industrial Exec Summary",
                    property_type="Industrial",
                    market="Chicago",
                    body=body_5,
                    prompt_list=[body_5],
                    status="Active",
                    author="Carlos Ramirez",
                    tier="tier3",
                    upvotes=18,
                    downvotes=4,
                ),
                models.Prompt(
                    section="Market Overview",
                    label="Denver Office Overview",
                    property_type="Office",
                    market="Denver",
                    body=body_6,
                    prompt_list=[body_6],
                    status="Active",
                    is_default=False,
                    author="John Doe",
                    tier="tier1",
                    upvotes=41,
                    downvotes=6,
                ),
            ]
        )
        prompts_created = 6

    # Schedules (optional demo)
    if await _count(session, models.Schedule) == 0:
        session.add_all(
            [
                models.Schedule(
                    name="Weekly Oakland Office Figures",
                    frequency="Weekly",
                    recipients="research@cbre.com, exec@cbre.com",
                    status="Active",
                ),
                models.Schedule(
                    name="Monthly Executive Summary (Industrial)",
                    frequency="Monthly",
                    recipients="industry-team@cbre.com",
                    status="Active",
                ),
            ]
        )
        schedules_created += 2

    sample_counts = await ensure_sample_reports(session, admin_user)
    schedules_created += sample_counts["schedules_created"]

    await session.commit()

    # Also ensure UI demo templates are present
    try:
        demo = await ensure_demo_templates(session)
    except Exception:
        demo = {"templates_created_or_updated": 0}

    return {
        "users": users_created,
        "templates": templates_created,
        "prompts": prompts_created,
        "schedules": schedules_created,
        **demo,
    }

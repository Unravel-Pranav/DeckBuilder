"""SeedService — populate demo templates on startup."""
from __future__ import annotations
from datetime import datetime
from typing import Any
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import TemplateModel, TemplateSectionModel, TemplateSectionElementModel
from app.utils.logger import logger

class SeedService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def _count(self, model: type) -> int:
        res = await self._session.execute(select(func.count()).select_from(model))
        return int(res.scalar() or 0)

    async def _add_section(self, template: TemplateModel, name: str, property_type: str, default_prompt: str = "", slide_layout: str | None = None) -> None:
        sec = TemplateSectionModel(name=name, sectionname_alias=name, property_type=property_type, default_prompt=default_prompt, mode="Attended", slide_layout=slide_layout)
        sec.templates.append(template)
        self._session.add(sec)
        await self._session.flush()
        chart_cfg: dict[str, Any] = {"type": "chart", "chart_type": "Bar Chart", "chart_data": [{"Category": "Q1", "Value1": 65}, {"Category": "Q2", "Value1": 80}, {"Category": "Q3", "Value1": 55}, {"Category": "Q4", "Value1": 90}], "chart_label": f"{name} — Chart", "chart_source": "", "axisConfig": {"xAxis": [{"key": "Category", "name": "Category"}], "yAxis": [{"key": "Value1", "name": name, "isPrimary": True}], "isMultiAxis": False}}
        self._session.add(TemplateSectionElementModel(section_id=sec.id, element_type="chart", display_order=0, config=chart_cfg))
        table_cfg: dict[str, Any] = {"type": "table", "table_data": [{"Metric": f"{name} KPI 1", "Current": "$12.5M", "Previous": "$10.2M", "Change": "+22%"}, {"Metric": f"{name} KPI 2", "Current": "85%", "Previous": "78%", "Change": "+7pp"}], "table_columns_sequence": ["Metric", "Current", "Previous", "Change"]}
        self._session.add(TemplateSectionElementModel(section_id=sec.id, element_type="table", display_order=1, config=table_cfg))
        commentary_cfg: dict[str, Any] = {"type": "commentary", "content": f"Commentary for {name}.", "commentary_text": f"Commentary for {name}.", "section_alias": name}
        self._session.add(TemplateSectionElementModel(section_id=sec.id, element_type="commentary", display_order=2, config=commentary_cfg))

    async def seed_if_empty(self) -> dict[str, Any]:
        if await self._count(TemplateModel) > 0:
            return {"templates": 0, "message": "Already seeded"}
        count = 0
        for tpl_name, base_type, sections in [
            ("Office Quarterly Template", "Office Figures", ["Executive Summary", "Market Overview", "Vacancy Analysis", "Net Absorption", "Leasing Activity", "Construction Pipeline"]),
            ("Industrial Quarterly Template", "Industrial Figures", ["Executive Summary", "Market Overview", "Vacancy Analysis", "Net Absorption", "Leasing Activity"]),
            ("Custom Analysis Template", "Office Figures", ["Executive Summary", "Net Absorption"]),
        ]:
            tpl = TemplateModel(name=tpl_name, base_type=base_type, is_default=count < 2, attended=True, ppt_status="Not Attached")
            self._session.add(tpl)
            await self._session.flush()
            ptype = "Office" if "Office" in base_type else "Industrial"
            for sec_name in sections:
                await self._add_section(tpl, sec_name, ptype, f"Default prompt for {sec_name}", "Title and Content")
            count += 1
        await self._session.commit()
        logger.info("Seeded %d templates", count)
        return {"templates": count}

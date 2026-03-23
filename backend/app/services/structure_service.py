"""StructureService — auto-generate report structure."""
from __future__ import annotations
from app.schemas.structure_schema import (StructureGenerateRequest, StructureGenerateResponse, GeneratedSectionResponse, GeneratedElementResponse)
from app.utils.logger import logger

CHART_PREFS = {"financial": ["Bar Chart", "Line - Single axis", "Pie Chart"], "business": ["Bar Chart", "Pie Chart", "Line - Single axis"], "research": ["Bar Chart", "Line - Single axis", "Bar Chart"], "custom": ["Bar Chart", "Pie Chart"]}
COMMENTARY = {"financial": "Financial metrics show strong performance.", "business": "Strategic execution remains on track.", "research": "Analysis reveals statistically significant patterns.", "custom": "Data analysis indicates noteworthy patterns."}

class StructureService:
    async def generate_structure(self, body: StructureGenerateRequest) -> StructureGenerateResponse:
        logger.info("Generating structure: %d sections", len(body.sections))
        generated, total = [], 0
        for sec_idx, sec in enumerate(body.sections):
            elements = []
            for tmpl_idx, tmpl in enumerate(sec.suggested_templates):
                if tmpl.type in ("chart-heavy", "mixed"):
                    prefs = CHART_PREFS.get(body.intent_type, ["Bar Chart"])
                    elements.append(GeneratedElementResponse(element_type="chart", label=f"{sec.name} — {tmpl.name}", display_order=len(elements), config={"chart_type": prefs[tmpl_idx % len(prefs)], "chart_data": [{"Category": "Q1", "Value1": 65}, {"Category": "Q2", "Value1": 80}, {"Category": "Q3", "Value1": 55}, {"Category": "Q4", "Value1": 90}], "chart_label": f"{sec.name} — {tmpl.name}", "chart_source": "", "axisConfig": {"xAxis": [{"key": "Category", "name": "Category"}], "yAxis": [{"key": "Value1", "name": tmpl.name, "isPrimary": True}], "isMultiAxis": False}}))
                if tmpl.type in ("table-heavy", "mixed"):
                    elements.append(GeneratedElementResponse(element_type="table", label=f"{sec.name} — Table", display_order=len(elements), config={"table_type": "table", "table_data": [{"Metric": f"{sec.name} KPI 1", "Current": "$12.5M", "Previous": "$10.2M", "Change": "+22%"}, {"Metric": f"{sec.name} KPI 2", "Current": "85%", "Previous": "78%", "Change": "+7pp"}], "table_columns_sequence": ["Metric", "Current", "Previous", "Change"]}))
                if tmpl.type == "commentary":
                    text = COMMENTARY.get(body.intent_type, COMMENTARY["custom"])
                    elements.append(GeneratedElementResponse(element_type="commentary", label=f"{sec.name} — Commentary", display_order=len(elements), config={"content": text, "commentary_text": text, "section_alias": sec.name}))
            total += len(elements)
            generated.append(GeneratedSectionResponse(name=sec.name, sectionname_alias=sec.name, display_order=sec_idx, elements=elements))
        return StructureGenerateResponse(sections=generated, total_elements=total)

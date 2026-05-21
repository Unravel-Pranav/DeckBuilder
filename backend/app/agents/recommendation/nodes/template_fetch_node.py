"""template_fetch_node — load template slot schemas from the DB."""
from __future__ import annotations

from typing import Any

from app.core.database import async_session_factory
from app.services.template_service import TemplateService
from app.utils.logger import logger


async def template_fetch_node(state: dict[str, Any]) -> dict[str, Any]:
    try:
        async with async_session_factory() as session:
            svc = TemplateService(session)
            templates = await svc.get_templates_for_llm(state.get("presentation_type"))
        logger.info("template_fetch_node: loaded %d templates", len(templates))
        return {"available_templates": templates}
    except Exception as exc:  # noqa: BLE001
        logger.warning("template_fetch_node failed: %s", exc)
        return {"available_templates": []}

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from .. import models


def normalize_prompt_list(body: str, prompt_list: list[str] | None) -> list[str]:
    """Ensure prompt_list is a cleaned list with at least the canonical body."""
    safe_body = (body or "").strip()
    prompts: list[str] = []
    if prompt_list:
        for entry in prompt_list:
            if not isinstance(entry, str):
                raise ValueError("Prompt must be string")
            cleaned = entry.strip()
            prompts.append(cleaned)
    if not prompts and safe_body:
        prompts = [safe_body]
    return prompts


async def save_prompts(
    session: AsyncSession, prompts: list[dict]
) -> list[models.Prompt]:
    saved: list[models.Prompt] = []
    for p in prompts:
        item = models.Prompt(**p)
        prompt_list = normalize_prompt_list(p.get("body"), p.get("prompt_list"))
        setattr(item, "prompt_list", prompt_list)
        session.add(item)
        saved.append(item)
    await session.commit()
    for item in saved:
        await session.refresh(item)
    return saved

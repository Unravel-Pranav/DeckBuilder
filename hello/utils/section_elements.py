from __future__ import annotations

from typing import Any


def normalize_prompt_list(config: dict[str, Any] | None) -> list[str]:
    """Ensure config.prompt_list mirrors sanitized config.sql_list."""
    if config is None:
        return []

    prompts: list[str] = []
    raw_prompts = config.get("prompt_list")
    if isinstance(raw_prompts, list):
        for item in raw_prompts:
            if item is None:
                prompts.append("")
            else:
                prompts.append(str(item).strip())

    sql_list: list[str] = []
    raw_sql = config.get("sql_list")
    if isinstance(raw_sql, list):
        for item in raw_sql:
            if isinstance(item, str):
                cleaned = item.strip()
                if cleaned:
                    sql_list.append(cleaned)
    config["sql_list"] = sql_list

    if sql_list:
        if not prompts:
            prompts = [""] * len(sql_list)
        elif len(prompts) < len(sql_list):
            prompts.extend([""] * (len(sql_list) - len(prompts)))
        elif len(prompts) > len(sql_list):
            prompts = prompts[: len(sql_list)]
    else:
        prompts = []

    config["prompt_list"] = prompts
    return prompts

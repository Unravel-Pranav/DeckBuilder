from __future__ import annotations

import asyncio

from hello.services.database import async_session
from hello.services.seed import seed_if_empty, ensure_demo_templates


async def _main() -> None:
    async with async_session() as session:  # type: ignore
        res1 = await seed_if_empty(session)
        res2 = await ensure_demo_templates(session)
        print({"seeded": res1, "demo": res2})


if __name__ == "__main__":
    asyncio.run(_main())

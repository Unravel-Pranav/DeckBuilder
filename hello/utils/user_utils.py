from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hello import models
from hello.ml.logger import GLOBAL_LOGGER as logger


async def get_user_email_map(
    session: AsyncSession, user_ids: Iterable[int | None]
) -> dict[int, str]:
    """Return a mapping of user_id -> email for the provided ids.
    
    Args:
        session: Database session
        user_ids: Iterable of user IDs (including None values which are filtered out)
        
    Returns:
        Dictionary mapping user ID to email address
    """
    ids = {int(uid) for uid in user_ids if uid is not None}
    if not ids:
        logger.debug("get_user_email_map: No valid user IDs provided, returning empty map")
        return {}
    
    logger.debug(f"get_user_email_map: Resolving emails for {len(ids)} user(s): {ids}")
    
    try:
        rows = await session.execute(
            select(models.User.id, models.User.email).where(models.User.id.in_(ids))
        )
        result = {int(uid): email for uid, email in rows.all()}
        
        # Log warning if some IDs couldn't be resolved
        missing_ids = ids - result.keys()
        if missing_ids:
            logger.warning(
                f"get_user_email_map: Could not resolve emails for user IDs: {missing_ids}"
            )
        
        logger.debug(f"get_user_email_map: Successfully resolved {len(result)} email(s)")
        return result
    except Exception as err:
        logger.error(
            f"get_user_email_map: Failed to resolve user emails for IDs {ids}: {err}",
            exc_info=True
        )
        return {}

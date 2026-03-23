from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from hello.services.database import get_session
from hello import models
from hello.schemas import UserIn, UserOut, UserUpdate
from hello.services.error_handlers import handle_db_error
from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.utils.auth_utils import require_auth, get_user_from_claims

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/", response_model=list[UserOut])
async def list_users(session: AsyncSession = Depends(get_session)):
    logger.info("#users: Listing users")
    res = await session.execute(
        select(models.User).order_by(models.User.id.desc())
    )
    return list(res.scalars().all())


@router.post("/", response_model=UserOut, status_code=201)
async def create_user(payload: UserIn, session: AsyncSession = Depends(get_session)):
    try:
        logger.info("#users: Creating user with email=%s", payload.email)
        user = models.User(**payload.model_dump())
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user
    except Exception as err:
        logger.error("#users: User creation failed for email=%s", getattr(payload, "email", None), exc_info=err)
        await session.rollback()
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(
                session, err, conflict_message="User with this email already exists"
            )
        raise


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: int, session: AsyncSession = Depends(get_session)):
    logger.info("#users: Getting user with id=%s", user_id)
    user = await session.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserOut)
async def patch_user(
    user_id: int, payload: UserUpdate, session: AsyncSession = Depends(get_session)
):
    logger.info("#users: Updating(patch) user with id=%s", user_id)
    user = await session.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        payload_data = payload.model_dump(exclude_unset=True)
        for k, v in payload_data.items():
            setattr(user, k, v)
        await session.commit()
        await session.refresh(user)
        return user
    except Exception as err:
        logger.error("#users: Updating(patch) user failed for id=%s", user_id, exc_info=err)
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise


@router.put("/{user_id}", response_model=UserOut)
async def put_user(
    user_id: int, payload: UserIn, session: AsyncSession = Depends(get_session)
):
    logger.info("#users: Updating(put) user with id=%s", user_id)
    user = await session.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        payload_data = payload.model_dump()
        for k, v in payload_data.items():
            setattr(user, k, v)
        await session.commit()
        await session.refresh(user)
        return user
    except Exception as err:
        logger.error("#users: Updating(put) user failed for id=%s", user_id, exc_info=err)
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise


@router.delete("/{user_id}", status_code=204)
async def delete_user(user_id: int, session: AsyncSession = Depends(get_session)):
    logger.info("#users: Deleting user with id=%s", user_id)
    user = await session.get(models.User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        await session.delete(user)
        await session.commit()
        return None
    except Exception as err:
        logger.error("#users: User deletion failed for id=%s", user_id, exc_info=err)
        from sqlalchemy.exc import SQLAlchemyError

        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise


# -------------------------------
# Current user helpers (header-based)
# -------------------------------


@router.get("/me", response_model=UserOut)
async def get_me(
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
):
    """Return the current user derived from cryptographically validated claims."""
    current_user = await get_user_from_claims(session, claims)
    logger.info("#users: Getting user details for claims user")
    if current_user:
        return UserOut.model_validate(current_user)
    raise HTTPException(status_code=404, detail="User not found")

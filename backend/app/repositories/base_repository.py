"""Generic async CRUD repository base."""
from __future__ import annotations
from typing import Generic, TypeVar
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import Base

ModelT = TypeVar("ModelT", bound=Base)

class BaseRepository(Generic[ModelT]):
    def __init__(self, session: AsyncSession, model_class: type[ModelT]):
        self._session = session
        self._model = model_class

    async def get_by_id(self, entity_id: int) -> ModelT | None:
        return await self._session.get(self._model, entity_id)

    async def get_all(self, *, limit: int = 100, offset: int = 0) -> list[ModelT]:
        stmt = select(self._model).limit(limit).offset(offset)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self) -> int:
        result = await self._session.scalar(select(func.count()).select_from(self._model))
        return result or 0

    async def create(self, entity: ModelT) -> ModelT:
        self._session.add(entity)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def update(self, entity: ModelT, data: dict) -> ModelT:
        for key, value in data.items():
            if value is not None and hasattr(entity, key):
                setattr(entity, key, value)
        await self._session.flush()
        await self._session.refresh(entity)
        return entity

    async def delete_by_id(self, entity_id: int) -> bool:
        entity = await self.get_by_id(entity_id)
        if entity:
            await self._session.delete(entity)
            return True
        return False

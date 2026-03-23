from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Optional

import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession

from hello.services.database import async_session
from hello.services import scheduler_runtime as runtime
from hello.ml.logger import GLOBAL_LOGGER as logger

POLL_SECONDS = int(os.getenv("SCHEDULER_POLL_SECONDS", "300"))  # 5 minutes
LEASE_SECONDS = int(os.getenv("SCHEDULER_LEASE_SECONDS", "900"))  # 15 minutes
BATCH_SIZE = int(os.getenv("SCHEDULER_BATCH_SIZE", "5"))
WORKER_ID = os.getenv("SCHEDULER_WORKER_ID", os.uname().nodename)


async def call_external_api(session_http: aiohttp.ClientSession, *, endpoint: str, method: str, payload: Optional[dict], headers: Optional[dict], idempotency_key: str) -> dict:
    req_headers = {"Idempotency-Key": idempotency_key}
    if headers:
        req_headers.update(headers)
    method_upper = (method or "POST").upper()
    async with session_http.request(method_upper, endpoint, json=payload, headers=req_headers, timeout=aiohttp.ClientTimeout(total=600)) as resp:
        resp.raise_for_status()
        try:
            return await resp.json()
        except Exception:
            text = await resp.text()
            return {"text": text, "status": resp.status}


async def worker_cycle(db: AsyncSession):
    # 1) Reap
    await runtime.reap_expired_leases(db)
    # 2) Promote
    await runtime.promote_schedules(db)
    # 3) Lease
    jobs = await runtime.lease_jobs(db, batch_size=BATCH_SIZE, worker_id=WORKER_ID, lease_seconds=LEASE_SECONDS)
    if not jobs:
        return
    # 4) Execute synchronously one by one
    async with aiohttp.ClientSession() as http:
        for job in jobs:
            idemp = f"job-{job.id}"
            try:
                response = await call_external_api(
                    http,
                    endpoint=job.endpoint,
                    method=job.method,
                    payload=job.payload,
                    headers=job.headers,
                    idempotency_key=idemp,
                )
                await runtime.complete_job(db, job.id, response)
            except Exception as e:
                # Backoff 5 minutes by default; runtime.fail_job handles retry vs fail
                await runtime.fail_job(db, job.id, error=str(e), backoff_seconds=300)


async def main():
    logger.info(
        "[scheduler] starting worker id=%s poll=%ss lease=%ss batch=%s",
        WORKER_ID,
        POLL_SECONDS,
        LEASE_SECONDS,
        BATCH_SIZE,
    )
    try:
        while True:
            started = datetime.utcnow()
            async with async_session() as db:
                await worker_cycle(db)
            elapsed = (datetime.utcnow() - started).total_seconds()
            sleep_s = max(1.0, POLL_SECONDS - elapsed)
            await asyncio.sleep(sleep_s)
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(main())

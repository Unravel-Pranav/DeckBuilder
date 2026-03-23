from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from hello import models
from hello.ml.utils.snowflake_connector import SnowflakeConnector
from hello.services.config import settings
from hello.services.logging_helper import setup_logging
from hello.services.database import async_session
from hello.services.multi_agent_workflow_service import workflow_service
from hello.services.notifications import (
    send_multi_market_report_notification,
    send_report_failure_notification,
    send_report_notification,
)
from hello.services.report_runner import run_report_now
from hello.ml.logger import GLOBAL_LOGGER as log

# Load .env file before importing settings
# Find the app/backend directory (3 levels up from this file: job.py -> hello -> src -> app)
# In Docker/K8s: /app/src/hello/job.py -> /app/.env
# In local dev: backend/src/hello/job.py -> backend/.env
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ENV_FILE = BACKEND_DIR / ".env"

# Ensure console logs are configured immediately
setup_logging()

# Load environment variables from .env file if it exists
if ENV_FILE.exists():
    loaded = load_dotenv(ENV_FILE, override=False)  # Don't override existing env vars
    log.info(f"Loaded .env file from: {ENV_FILE} (loaded={loaded})")
else:
    log.warning(f".env file not found at: {ENV_FILE} - will rely on environment variables")

_snowflake_connector: SnowflakeConnector | None = None
 
 
def _utcnow() -> datetime:
    # SQLAlchemy models use datetime.utcnow(); keep naive UTC for comparisons
    return datetime.utcnow()
 
 
def _parse_recipients_csv(csv_str: Optional[str]) -> list[str]:
    if not csv_str:
        return []
    return [s.strip() for s in csv_str.split(",") if s.strip()]
 
 
def _parse_time_of_day(value: Optional[str]) -> tuple[int, int] | None:
    if not value:
        return None
    try:
        parts = value.strip().split(":")
        hh = int(parts[0])
        mm = int(parts[1]) if len(parts) > 1 else 0
        hh = max(0, min(23, hh))
        mm = max(0, min(59, mm))
        return hh, mm
    except Exception:
        return None
 
 
async def _ensure_multi_agent_workflow_ready() -> None:
    """Initialize the multi-agent workflow service when the scheduler runs outside FastAPI."""
    if workflow_service.is_parallel_ready():
        return
 
    log.info("[scheduler] initializing multi-agent workflow service...")
    success = await workflow_service.initialize()
    if not success or not workflow_service.is_parallel_ready():
        raise RuntimeError("Multi-agent workflow service failed to initialize")
 
 
async def _ensure_snowflake_connector_ready() -> None:
    """Lazily initialize the Snowflake connector so jobs can fetch data."""
    global _snowflake_connector
    if _snowflake_connector is not None:
        return
    if not _snowflake_configured():
        log.info("[scheduler] Snowflake settings missing; skipping connector initialization")
        return
    log.info("[scheduler] initializing Snowflake connector for jobs...")
    try:
        connector = SnowflakeConnector()
        await asyncio.to_thread(connector.connect)
        _snowflake_connector = connector
        log.info("[scheduler] Snowflake connector initialized successfully")
    except Exception as exc:
        log.exception("[scheduler] Failed to initialize Snowflake connector; downstream Snowflake queries may fail", exc_info=exc)
 
 
def _snowflake_configured() -> bool:
    """Return True if the minimum Snowflake settings are provided."""
    required = [
        settings.snowflake_account,
        settings.snowflake_user,
    ]
    if not all(required):
        return False
    if not (settings.snowflake_password or settings.snowflake_private_key_path):
        return False
    return True
 
 
def _next_weekday(after: datetime, weekday_name: Optional[str]) -> datetime:
    mapping = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    if not weekday_name:
        return after + timedelta(days=7)
    idx = mapping.get(weekday_name.strip().lower())
    if idx is None:
        return after + timedelta(days=7)
    days_ahead = (idx - after.weekday() + 7) % 7
    days_ahead = 7 if days_ahead == 0 else days_ahead
    return after + timedelta(days=days_ahead)
 
 
def _bump_month(dt: datetime, day_of_month: Optional[int]) -> datetime:
    # naive simple month bump (+1 month) with best-effort day-of-month clamping
    import calendar
    m = dt.month + 1
    y = dt.year + (1 if m > 12 else 0)
    m = 1 if m > 12 else m
    days_in_month = calendar.monthrange(y, m)[1]
    dom = max(1, min(days_in_month, (day_of_month or dt.day)))
    return dt.replace(year=y, month=m, day=dom)


def _bump_quarters(dt: datetime, day_of_month: int = 1, month_of_quarter: int = 1) -> datetime:
    """Advance to the target month of the next quarter on the specified day.
    
    Args:
        dt: Reference datetime
        day_of_month: Day of the month (1-31)
        month_of_quarter: Which month within the quarter (1=first, 2=second, 3=third)
    """
    import calendar
    
    # Clamp month_of_quarter to 1-3
    moq = max(1, min(3, month_of_quarter))
    month_offset = moq - 1  # 0, 1, or 2
    
    # Current quarter (0-based): Q1=0, Q2=1, Q3=2, Q4=3
    current_quarter = (dt.month - 1) // 3
    
    # Target month in current quarter
    target_month = current_quarter * 3 + month_offset + 1  # 1-indexed
    y = dt.year
    
    # Create candidate date in current quarter
    days_in_month = calendar.monthrange(y, target_month)[1]
    dom = max(1, min(days_in_month, day_of_month))
    candidate = dt.replace(year=y, month=target_month, day=dom)
    
    # If candidate is in the past or today, move to next quarter
    if candidate <= dt:
        target_month += 3
        if target_month > 12:
            y += 1
            target_month -= 12
        days_in_month = calendar.monthrange(y, target_month)[1]
        dom = max(1, min(days_in_month, day_of_month))
        candidate = dt.replace(year=y, month=target_month, day=dom)
    
    return candidate


def _bump_year(dt: datetime, day_of_month: int = 1, month_of_year: Optional[int] = None) -> datetime:
    """Advance to the next year on the specified month and day.
    
    If month_of_year is provided, use that month (1-12).
    Otherwise, use the current month and advance by 1 year.
    """
    import calendar
    target_month = month_of_year or dt.month
    target_month = max(1, min(12, target_month))
    
    # Try this year first
    y = dt.year
    days_in_month = calendar.monthrange(y, target_month)[1]
    dom = max(1, min(days_in_month, day_of_month))
    try:
        cand = dt.replace(year=y, month=target_month, day=dom)
        # If the candidate is in the past or present, move to next year
        if cand <= dt:
            days_in_month_next = calendar.monthrange(y + 1, target_month)[1]
            dom_next = max(1, min(days_in_month_next, day_of_month))
            cand = dt.replace(year=y + 1, month=target_month, day=dom_next)
        return cand
    except ValueError:
        # Invalid date, use last valid day
        days_in_month = calendar.monthrange(y, target_month)[1]
        cand = dt.replace(year=y, month=target_month, day=days_in_month)
        if cand <= dt:
            days_in_month_next = calendar.monthrange(y + 1, target_month)[1]
            cand = dt.replace(year=y + 1, month=target_month, day=days_in_month_next)
        return cand
 
 
def _apply_tod(base: datetime, tod: tuple[int, int] | None) -> datetime:
    if not tod:
        return base
    h, m = tod
    return base.replace(hour=h, minute=m, second=0, microsecond=0)
 
 
def compute_next_run_at(s: models.Schedule, ref_utc: datetime) -> Optional[datetime]:
    """Compute next run as naive UTC. All times are in UTC, no timezone conversions.

    ref_utc: naive UTC datetime (scheduler's current time)
    """
    freq = (s.frequency or "").strip().lower()
    hhmm = _parse_time_of_day(s.time_of_day)
    h, m = hhmm if hhmm else (9, 0)
    start_boundary = getattr(s, "start_date", None)
    if start_boundary and start_boundary.tzinfo:
        start_boundary = start_boundary.replace(tzinfo=None)
    if (
        start_boundary
        and hhmm
        and start_boundary.hour == 0
        and start_boundary.minute == 0
        and start_boundary.second == 0
        and start_boundary.microsecond == 0
    ):
        start_boundary = start_boundary.replace(hour=h, minute=m, second=0, microsecond=0)
    ref_point = start_boundary if start_boundary and start_boundary > ref_utc else ref_utc

    if freq in {"daily", "day", "everyday"}:
        cand = ref_point.replace(hour=h, minute=m, second=0, microsecond=0)
        if cand <= ref_point:
            cand = cand + timedelta(days=1)
        return cand

    if freq in {"weekly", "week"}:
        base = _next_weekday(ref_point, s.day_of_week)
        cand = base.replace(hour=h, minute=m, second=0, microsecond=0)
        return cand

    if freq in {"monthly", "month"}:
        base = _bump_month(ref_point, s.day_of_month)
        cand = base.replace(hour=h, minute=m, second=0, microsecond=0)
        return cand

    if freq in {"quarterly", "quarter"}:
        # Quarterly = target month within quarter
        dom = s.day_of_month or 1
        dom = max(1, min(31, dom))  # Allow up to 31 days
        moq = getattr(s, 'month_of_quarter', None) or 1
        base = _bump_quarters(ref_point, dom, moq)
        cand = base.replace(hour=h, minute=m, second=0, microsecond=0)
        return cand

    if freq in {"yearly", "year", "annual", "annually"}:
        # Yearly = specific month and day each year
        dom = s.day_of_month or 1
        dom = max(1, min(31, dom))  # Allow up to 31 days
        month = getattr(s, 'month_of_year', None)
        base = _bump_year(ref_point, dom, month)
        cand = base.replace(hour=h, minute=m, second=0, microsecond=0)
        return cand
 
    # Once or unknown
    return None
 
 
async def _fetch_due_schedules(session: AsyncSession) -> list[models.Schedule]:
    """Return schedules that are due to run now.
 
    Logic (all times in naive UTC, no timezone conversions):
    - Active schedules only
    - Due if next_run_at <= now (picks up all overdue schedules)
    - Or if run_date <= now
    - Or one-time schedules with both next_run_at and run_date NULL (treat as due now)
    - If next_run_at is NULL but computable from fields, compute and include if overdue
    - Skip if next_run_at <= last_run_at (already processed for this occurrence)
    
    This ensures all missed schedules are picked up regardless of downtime duration.
    All database times are assumed to be in UTC.
    """
    now = _utcnow()
    log.info("[scheduler] checking schedules due at or before %s (UTC)", now)
    # Fetch all schedules and filter in Python to handle case/legacy fields
    res = await session.execute(select(models.Schedule))
    all_scheds: list[models.Schedule] = list(res.scalars().all())
    candidates: list[models.Schedule] = []
    for s in all_scheds:
        status = (getattr(s, "schedule_status", None) or getattr(s, "status", "") or "").strip().lower()
        if status == "active":
            candidates.append(s)
 
    due: list[models.Schedule] = []
    for s in candidates:
        freq = (s.frequency or "").strip().lower()
        hhmm = _parse_time_of_day(s.time_of_day)
        start_boundary = getattr(s, "start_date", None)
        if start_boundary and start_boundary.tzinfo:
            start_boundary = start_boundary.replace(tzinfo=None)
        if (
            start_boundary
            and hhmm
            and start_boundary.hour == 0
            and start_boundary.minute == 0
            and start_boundary.second == 0
            and start_boundary.microsecond == 0
        ):
            start_boundary = start_boundary.replace(
                hour=hhmm[0], minute=hhmm[1], second=0, microsecond=0
            )
        if start_boundary and start_boundary > now:
            # Not started yet
            continue
        
        # Skip if already processed for this occurrence
        # After processing, next_run_at advances to next occurrence (future)
        # If next_run_at <= last_run_at, the schedule was already run
        if s.last_run_at and s.next_run_at and s.next_run_at <= s.last_run_at:
            continue
        
        # Check next_run_at (all times in UTC) - pick up all overdue schedules
        if s.next_run_at:
            if s.next_run_at <= now:
                due.append(s)
                continue
        
        # Check run_date (all times in UTC) - pick up all overdue schedules
        if s.run_date:
            if s.run_date <= now:
                due.append(s)
                continue
        
        # One-time schedules without timestamps: run immediately
        if freq in {"one-time", "one time", "once"} and s.next_run_at is None and s.run_date is None:
            # Set next_run_at in memory; will be properly updated by _process_schedule
            s.next_run_at = now
            log.info(
                "[scheduler] one-time schedule %s missing times; treating as due now (next_run_at=%s)",
                s.id,
                s.next_run_at,
            )
            due.append(s)
            continue
        
        # Compute next_run_at if missing
        nxt = compute_next_run_at(s, now)
        if nxt and nxt <= now:
            # Also check if already processed (computed next_run_at case)
            if s.last_run_at and nxt <= s.last_run_at:
                continue
            s.next_run_at = nxt  # set in-memory so later logs include it
            due.append(s)
 
    if candidates:
        log.info("[scheduler] active schedules=%s, due=%s", len(candidates), [getattr(s, 'id', '?') for s in due])
        # Verbose audit of why not due (all times in UTC)
        not_due = [s for s in candidates if s not in due]
        for s in not_due:
            log.info(
                "[scheduler] not-due id=%s status=%s freq=%s next_run_at=%s run_date=%s last_run_at=%s (now=%s UTC)",
                getattr(s, 'id', '?'),
                (getattr(s, 'schedule_status', None) or getattr(s, 'status', '')),
                getattr(s, 'frequency', ''),
                getattr(s, 'next_run_at', None),
                getattr(s, 'run_date', None),
                getattr(s, 'last_run_at', None),
                now
            )
    else:
        log.info("[scheduler] no active schedules found")
    return due
 
 
async def _process_schedule(session: AsyncSession, s: models.Schedule) -> tuple[bool, str]:
    """Process a single schedule. Returns (success, message) tuple.
    
    Note: This function commits transactions multiple times. The session should
    be refreshed or a new session should be used for each schedule to avoid
    stale object issues.
    """
    now = _utcnow()
    if not s.report_id:
        msg = f"schedule {s.id} has no report_id; skipping"
        log.warning("[scheduler] %s", msg)
        return False, msg
 
    # 1) Update next_run_at and last_run_at BEFORE running (prevents duplicate runs)
    freq = (s.frequency or "").strip().lower()
    try:
        next_at = compute_next_run_at(s, now)
        old_next_run_at = s.next_run_at
        s.next_run_at = next_at
        s.last_run_at = now
        
        # Mark one-time schedules as completed
        if next_at is None:
            if freq in {"one-time", "one time", "once"}:
                s.schedule_status = "completed"
            elif s.run_date and s.run_date <= now:
                s.schedule_status = "completed"
        
        await session.commit()
        log.info(
            "[scheduler] schedule %s pre-run update: next_run_at %s -> %s, last_run_at=%s, status=%s",
            s.id, old_next_run_at, s.next_run_at, s.last_run_at, s.schedule_status
        )
    except Exception as e:
        log.exception("[scheduler] failed to update schedule timing for %s before run", s.id, exc_info=e)
        await session.rollback()
        return False, f"schedule {s.id} failed to update timing: {str(e)}"
 
    # 2) Run the report now (generate PPT, upload, persist ReportRun)
    log.info(
        "[scheduler] running schedule id=%s name=%s report_id=%s freq=%s",
        getattr(s, "id", "?"), getattr(s, "name", ""), getattr(s, "report_id", None), freq
    )
    
    # Fetch report name for notifications
    try:
        report_result = await session.execute(
            select(models.Report).where(models.Report.id == s.report_id)
        )
        report = report_result.scalar_one_or_none()
        report_name = report.name if report else f"Report {s.report_id}"
    except Exception:
        report_name = f"Report {s.report_id}"
    
    try:
        # Add timeout protection: max 10 minutes per schedule
        # (K8s activeDeadlineSeconds is 15min for entire job)
        log.info(
            "[scheduler] Running scheduled report - report_id=%s, schedule_id=%s, "
            "trigger_source=scheduled, created_by=%s",
            s.report_id, getattr(s, "id", None), getattr(s, "created_by", None)
        )
        
        result = await asyncio.wait_for(
            run_report_now(
                session,
                s.report_id,
                trigger_source="scheduled",
                schedule_id=getattr(s, "id", None),
                created_by=getattr(s, "created_by", None),
            ),
            timeout=600.0  # 10 minutes
        )
    except asyncio.TimeoutError:
        log.error(
            "[scheduler] timeout (10min) for schedule %s (report_id=%s)",
            s.id, s.report_id
        )
        # Send failure notification
        recipients = _parse_recipients_csv(s.recipients)
        if recipients:
            try:
                await send_report_failure_notification(
                    to_emails=recipients,
                    report_name=report_name,
                    trigger_source="scheduled"
                )
                log.info("[scheduler] Sent failure notification for timeout to %s", recipients)
            except Exception as notify_err:
                log.exception("[scheduler] Failed to send timeout notification", exc_info=notify_err)
        return False, f"schedule {s.id} timed out after 10 minutes"
    except Exception as e:
        log.exception("[scheduler] run failed for schedule %s (report_id=%s)", s.id, s.report_id, exc_info=e)
        # Send failure notification
        recipients = _parse_recipients_csv(s.recipients)
        if recipients:
            try:
                await send_report_failure_notification(
                    to_emails=recipients,
                    report_name=report_name,
                    trigger_source="scheduled"
                )
                log.info("[scheduler] Sent failure notification to %s", recipients)
            except Exception as notify_err:
                log.exception("[scheduler] Failed to send failure notification", exc_info=notify_err)
        return False, f"run failed for schedule {s.id}: {str(e)}"
    log.info(
        "[scheduler] run completed for schedule id=%s -> run_id=%s url=%s status=%s",
        getattr(s, "id", "?"), result.get("run_id"), result.get("ppt_url") or result.get("s3_path"), result.get("status")
    )

    # 3) Email the recipients
    run_id = None  # Initialize to avoid UnboundLocalError in exception handler
    try:
        recipients = _parse_recipients_csv(s.recipients)
        run_id = result.get("run_id")
        market_ppt_info = result.get("market_ppt_info", [])
        
        # Check if all markets failed
        if result.get("status") == "Failed":
            # All markets failed - send failure notification
            if recipients:
                await send_report_failure_notification(
                    to_emails=recipients,
                    report_name=report_name,
                    trigger_source="scheduled"
                )
                delivery_details = {email: "Success" for email in recipients}
                log.info("[scheduler] Sent failure notification (all markets failed) to %s", recipients)
        elif run_id and recipients:
            # Some or all markets succeeded - send status notification
            if len(market_ppt_info) > 1:
                # Multi-market report - use multi-market notification (handles mixed success/failure)
                delivery_details = await send_multi_market_report_notification(
                    to_emails=recipients,
                    market_ppt_info=market_ppt_info,
                    report_name=report_name,
                    trigger_source="scheduled"
                )
            else:
                # Single market - use simple notification
                s3_path = result.get("s3_path") or ""
                if s3_path:
                    # Extract presigned URL from market_ppt_info for email
                    ppt_url_for_email = None
                    if market_ppt_info and len(market_ppt_info) > 0:
                        ppt_url_for_email = market_ppt_info[0].get("ppt_url")
                    
                    delivery_details = await send_report_notification(
                        recipients, 
                        s3_path, 
                        ppt_url_for_email, 
                        "scheduled",
                        report_name=report_name,
                        schedule_name=getattr(s, "name", None)
                    )
                else:
                    # No s3_path available, skip email
                    delivery_details = {}
                    log.warning("[scheduler] Skipping email - no s3_path available for report")
        else:
            # No recipients or no run_id
            delivery_details = {}
            log.info("[scheduler] email delivery skipped for schedule %s (no run_id or recipients)", s.id)
            
        if delivery_details:
            # Check if all emails succeeded
            all_success = all(status == "Success" for status in delivery_details.values())
            all_failed = all(status == "Failed" for status in delivery_details.values())
            all_skipped = all(status == "Skipped" for status in delivery_details.values())
            
            if all_success:
                email_status = "Success"
                log.info("[scheduler] Email sent successfully to all %d recipients for run_id=%s", len(delivery_details), run_id)
            elif all_skipped:
                email_status = "Skipped"
                log.warning("[scheduler] ⚠️  Email delivery SKIPPED for run_id=%s - SMTP not configured! Configure SMTP_HOST, SMTP_PORT, and SMTP_FROM_EMAIL in .env file", run_id)
            elif all_failed:
                email_status = "Failed"
                log.warning("[scheduler] Email failed to send to all recipients for run_id=%s", run_id)
            else:
                email_status = "Partial"
                success_count = sum(1 for s in delivery_details.values() if s == "Success")
                skipped_count = sum(1 for s in delivery_details.values() if s == "Skipped")
                log.warning("[scheduler] Email partially delivered for run_id=%s: %d successful, %d skipped, %d failed",
                           run_id, success_count, skipped_count, len(delivery_details) - success_count - skipped_count)
            
            # Update email status for all run IDs (multi-market reports have multiple)
            all_run_ids = result.get("all_run_ids", [run_id] if run_id else [])
            for rid in all_run_ids:
                if rid:
                    await session.execute(
                        update(models.ReportRun)
                        .where(models.ReportRun.id == rid)
                        .values(email_status=email_status, email_delivery_details=delivery_details)
                    )
            await session.commit()
            log.info("[scheduler] updated %d run_id(s) email_status=%s delivery_details=%s", len(all_run_ids), email_status, delivery_details)
        else:
            log.info("[scheduler] email delivery skipped for schedule %s (no run_id or recipients)", s.id)
    except Exception as e:
        log.exception("[scheduler] email delivery failed for schedule %s", s.id, exc_info=e)
        # Mark email as failed in database if we have a run_id
        if run_id:
            try:
                await session.rollback()  # Clean up any partial transaction
                await session.execute(
                    update(models.ReportRun).where(models.ReportRun.id == run_id).values(email_status="Failed")
                )
                await session.commit()
                log.info("[scheduler] updated run_id=%s email_status=Failed", run_id)
            except Exception as inner_e:
                log.exception("[scheduler] failed to update email_status for run_id=%s", run_id, exc_info=inner_e)
    
    return True, f"schedule {s.id} processed successfully"
 
 
async def run_once() -> int:
    """Run the scheduler once and return exit code.
    
    Returns:
        0: Success (at least one schedule processed successfully, or no schedules were due)
        1: Failure (all schedules failed to process)
    """
    start_time = _utcnow()
    log.info("[scheduler] ========== CronJob execution started at %s (UTC) ==========", start_time)
    
    # Debug: Log SMTP configuration status
    log.info("[scheduler] SMTP Configuration Check:")
    log.info("[scheduler]   smtp_host: %s", settings.smtp_host or "(not set)")
    log.info("[scheduler]   smtp_port: %s", settings.smtp_port or "(not set)")
    log.info("[scheduler]   smtp_from_email: %s", settings.smtp_from_email or "(not set)")
    smtp_configured = bool(settings.smtp_host and settings.smtp_port and settings.smtp_from_email)
    log.info("[scheduler]   SMTP Configured: %s", smtp_configured)
 
    try:
        await _ensure_multi_agent_workflow_ready()
    except Exception:
        log.exception("[scheduler] failed to initialize multi-agent workflow service; aborting run")
        return 1
    
    try:
        await _ensure_snowflake_connector_ready()
    except Exception:
        log.warning("[scheduler] proceeding without an initialized Snowflake connector")
 
    success_count = 0
    failure_count = 0
    
    try:
        async with async_session() as session:
            due = await _fetch_due_schedules(session)
            
            if not due:
                log.info("[scheduler] no schedules due at this time")
                end_time = _utcnow()
                duration = (end_time - start_time).total_seconds()
                log.info("[scheduler] ========== CronJob execution completed at %s (duration: %.2fs) ==========", end_time, duration)
                return 0  # Success: nothing to do
            
            log.info("[scheduler] found %s due schedule(s), processing sequentially...", len(due))
            
            # Extract schedule IDs for processing
            schedule_ids = [s.id for s in due]
            
            # Process all schedules sequentially with individual sessions
            # This prevents session state pollution across schedules
            for schedule_id in schedule_ids:
                try:
                    # Use a fresh session for each schedule to avoid state issues
                    async with async_session() as sched_session:
                        # Reload the schedule in this session
                        result = await sched_session.execute(
                            select(models.Schedule).where(models.Schedule.id == schedule_id)
                        )
                        s = result.scalar_one_or_none()
                        
                        if not s:
                            failure_count += 1
                            log.error("[scheduler] schedule %s not found when reloading", schedule_id)
                            continue
                        
                        # Process with dedicated session
                        result = await _process_schedule(sched_session, s)
                        if isinstance(result, tuple):
                            success, msg = result
                            if success:
                                success_count += 1
                                log.info("[scheduler] ✓ schedule %s: %s", schedule_id, msg)
                            else:
                                failure_count += 1
                                log.warning("[scheduler] ✗ schedule %s: %s", schedule_id, msg)
                        else:
                            failure_count += 1
                            log.error("[scheduler] schedule %s returned unexpected result: %s", schedule_id, result)
                except Exception as e:
                    failure_count += 1
                    log.error("[scheduler] schedule %s raised exception: %s", schedule_id, e)
                    log.exception("[scheduler] detailed exception for schedule %s", schedule_id)
    
    except Exception:
        log.exception("[scheduler] critical error in run_once")
        failure_count += 1
    
    # Compute exit code
    total = success_count + failure_count
    end_time = _utcnow()
    duration = (end_time - start_time).total_seconds()
    
    log.info("[scheduler] ========== Execution Summary ==========")
    log.info("[scheduler] Total schedules processed: %d", total)
    log.info("[scheduler] Successful: %d", success_count)
    log.info("[scheduler] Failed: %d", failure_count)
    log.info("[scheduler] Duration: %.2f seconds", duration)
    log.info("[scheduler] ========== CronJob execution completed at %s ==========", end_time)
    
    # Exit with 0 if any success or nothing to do
    # Exit with 1 only if all failed
    if total == 0:
        return 0  # Nothing to process
    elif success_count > 0:
        return 0  # At least one success
    else:
        return 1  # All failed
 
 
async def main() -> None:
    """Entry point for CronJob execution."""
    setup_logging()
    exit_code = await run_once()
    import sys
    sys.exit(exit_code)
 
 
if __name__ == "__main__":
    asyncio.run(main())

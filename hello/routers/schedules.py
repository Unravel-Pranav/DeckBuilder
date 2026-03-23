from __future__ import annotations

from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException
from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy import select, and_, func, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from hello.services.database import get_session
from hello import models
from hello.schemas import ScheduleIn, ScheduleOut, ScheduleUpdate, SchedulesListResponse
from hello.services.error_handlers import handle_db_error
from hello.services.config import settings
from hello.ml.logger import GLOBAL_LOGGER as logger
from hello.utils.auth_utils import get_user_from_claims, require_auth
from hello.utils.user_utils import get_user_email_map

router = APIRouter(dependencies=[Depends(require_auth)])

# ==============================
# Helpers to compute next run
# ==============================
WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def _parse_time(hhmm: str | None) -> time | None:
    if not hhmm:
        return None
    try:
        hh, mm = str(hhmm).split(":", 1)
        return time(hour=int(hh), minute=int(mm))
    except Exception:
        return None


def _advance_month(year: int, month: int, delta_months: int) -> tuple[int, int]:
    total_months = (month - 1) + delta_months
    new_year = year + total_months // 12
    new_month = (total_months % 12) + 1
    return new_year, new_month


def _get_days_in_month(year: int, month: int) -> int:
    """Return the number of days in a given month."""
    import calendar
    return calendar.monthrange(year, month)[1]


def _normalize_and_validate_recipients(raw: list[str] | str | None) -> list[str]:
    """Normalize, de-duplicate, and validate email recipients."""
    email_adapter = TypeAdapter(EmailStr)
    if raw is None:
        return []
    candidates = raw.split(",") if isinstance(raw, str) else raw

    seen: set[str] = set()
    cleaned: list[str] = []
    invalid: list[str] = []

    for candidate in candidates:
        value = (candidate or "").strip()
        if not value:
            continue
        try:
            email = email_adapter.validate_python(value)
        except (ValidationError, ValueError, TypeError):
            invalid.append(value)
            continue
        key = email.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(email)

    if invalid:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid email address(es): {', '.join(invalid)}",
        )
    if not cleaned:
        raise HTTPException(
            status_code=422, detail="At least one valid recipient is required"
        )
    return cleaned


def _compute_next_run(
    recurrence: str | None,
    *,
    time_of_day: str | None = None,
    day_of_week: str | None = None,
    day_of_month: int | None = None,
    month_of_year: int | None = None,
    month_of_quarter: int | None = None,
    run_date: datetime | None = None,
    start_date: datetime | None = None,
    now: datetime | None = None,
) -> datetime | None:
    """Compute the next run datetime as naive UTC using app timezone for local inputs."""
    tzname = settings.app_timezone or "UTC"
    try:
        app_tz = ZoneInfo(tzname)
    except Exception:
        app_tz = ZoneInfo("UTC")
    now = now or datetime.utcnow()
    # treat now as UTC
    now_local = now.replace(tzinfo=ZoneInfo("UTC")).astimezone(app_tz)
    rec = (recurrence or "").strip().lower()
    t = _parse_time(time_of_day) or time(hour=9, minute=0)

    def _normalize_start_local() -> datetime | None:
        if not start_date:
            return None
        base_local = (
            start_date.astimezone(app_tz)
            if start_date.tzinfo
            else start_date.replace(tzinfo=app_tz)
        )
        if (
            base_local.hour == 0
            and base_local.minute == 0
            and base_local.second == 0
            and base_local.microsecond == 0
        ):
            return base_local.replace(
                hour=t.hour, minute=t.minute, second=0, microsecond=0
            )
        return base_local

    start_local = _normalize_start_local()
    start_boundary_utc = (
        start_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        if start_local
        else None
    )
    ref_local = start_local if start_local and start_local > now_local else now_local

    if rec in ("one-time", "one time", "once"):
        # One-time semantics:
        # - If run_date is provided and in the future, schedule for that moment
        # - If run_date is missing, use today's time_of_day if provided; otherwise run now
        # - If the resulting candidate is in the past, run now
        if run_date:
            # interpret naive run_date as local time
            rd_local = run_date if run_date.tzinfo else run_date.replace(tzinfo=app_tz)
            rd_utc = rd_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
            candidate = rd_utc
            if start_boundary_utc:
                candidate = max(candidate, start_boundary_utc)
            return candidate if candidate > now else None
        # No run_date provided
        candidate_local = datetime(ref_local.year, ref_local.month, ref_local.day, t.hour, t.minute, tzinfo=app_tz)
        candidate_utc = candidate_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        if start_boundary_utc and candidate_utc < start_boundary_utc:
            candidate_utc = start_boundary_utc
        return candidate_utc if candidate_utc > now else now

    if rec == "daily":
        cand_local = datetime(ref_local.year, ref_local.month, ref_local.day, t.hour, t.minute, tzinfo=app_tz)
        if cand_local <= ref_local:
            cand_local = cand_local + timedelta(days=1)
        return cand_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    if rec == "weekly":
        wd = WEEKDAY_INDEX.get((day_of_week or "monday").lower(), 0)
        days_ahead = wd - ref_local.weekday()
        if days_ahead < 0:
            days_ahead += 7
        cand_local = datetime(ref_local.year, ref_local.month, ref_local.day, t.hour, t.minute, tzinfo=app_tz) + timedelta(days=days_ahead)
        if cand_local <= ref_local:
            cand_local = cand_local + timedelta(days=7)
        return cand_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    if rec == "monthly":
        dom = day_of_month or ref_local.day
        dom = max(1, min(31, int(dom)))

        year, month = ref_local.year, ref_local.month
        # Clamp to actual days in month
        actual_dom = min(dom, _get_days_in_month(year, month))
        cand_local = datetime(year, month, actual_dom, t.hour, t.minute, tzinfo=app_tz)
        while cand_local <= ref_local:
            year, month = _advance_month(year, month, 1)
            actual_dom = min(dom, _get_days_in_month(year, month))
            cand_local = datetime(year, month, actual_dom, t.hour, t.minute, tzinfo=app_tz)
        return cand_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    if rec == "quarterly":
        dom = day_of_month or ref_local.day
        dom = max(1, min(31, int(dom)))
        moq = month_of_quarter or 1  # default to first month of quarter
        moq = max(1, min(3, int(moq)))  # clamp to 1-3

        # Current quarter (0-based): Q1=0, Q2=1, Q3=2, Q4=3
        current_quarter = (ref_local.month - 1) // 3
        # Target month within the quarter (0-based offset: 0, 1, or 2)
        month_offset = moq - 1

        # Calculate target month (1-indexed)
        year = ref_local.year
        target_month = current_quarter * 3 + month_offset + 1  # 1-indexed

        # Clamp day to actual days in target month
        actual_dom = min(dom, _get_days_in_month(year, target_month))
        cand_local = datetime(year, target_month, actual_dom, t.hour, t.minute, tzinfo=app_tz)

        # If candidate is in the past, move to next quarter
        while cand_local <= ref_local:
            target_month += 3
            if target_month > 12:
                year += 1
                target_month = target_month - 12
            actual_dom = min(dom, _get_days_in_month(year, target_month))
            cand_local = datetime(year, target_month, actual_dom, t.hour, t.minute, tzinfo=app_tz)
        return cand_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    
    if rec in {"yearly", "annual", "annually"}:
        dom = day_of_month or ref_local.day
        dom = max(1, min(31, int(dom)))
        target_month = month_of_year or ref_local.month
        target_month = max(1, min(12, target_month))
        
        # Try current year first
        year = ref_local.year
        actual_dom = min(dom, _get_days_in_month(year, target_month))
        cand_local = datetime(year, target_month, actual_dom, t.hour, t.minute, tzinfo=app_tz)
        
        # If the candidate is in the past, move to next year
        if cand_local <= ref_local:
            actual_dom = min(dom, _get_days_in_month(year + 1, target_month))
            cand_local = datetime(year + 1, target_month, actual_dom, t.hour, t.minute, tzinfo=app_tz)
        
        return cand_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)

    # Fallback: daily
    cand_local = datetime(ref_local.year, ref_local.month, ref_local.day, t.hour, t.minute, tzinfo=app_tz)
    if cand_local <= ref_local:
        cand_local = cand_local + timedelta(days=1)
    return cand_local.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)


@router.get("/", response_model=SchedulesListResponse)
async def list_schedules(
    session: AsyncSession = Depends(get_session),
    page: int = 1,
    page_size: int = 20,
    q: str | None = None,
    recurrence: str | None = None,
    schedule_status: str | None = None,
    report_id: int | None = None,
    day_of_week: str | None = None,
):
    logger.info(
        "#schedules: Listing schedules for page=%s page_size=%s q=%s recurrence=%s schedule_status=%s report_id=%s day_of_week=%s",
        page,
        page_size,
        q,
        recurrence,
        schedule_status,
        report_id,
        day_of_week,
    )
    # Clamp page to minimum 1
    page = 1 if page is None or page < 1 else int(page)
    # Clamp page_size to reasonable bounds
    page_size = max(1, min(100, int(page_size))) if page_size else 20

    base_stmt = select(models.Schedule)
    conds = []
    if q:
        conds.append(models.Schedule.name.ilike(f"%{q}%"))
    if recurrence:
        conds.append(func.lower(models.Schedule.frequency) == recurrence.lower())
    if schedule_status:
        conds.append(func.lower(models.Schedule.schedule_status) == schedule_status.lower())
    if report_id is not None:
        conds.append(models.Schedule.report_id == report_id)
    if day_of_week:
        conds.append(func.lower(models.Schedule.day_of_week) == day_of_week.lower())
    if conds:
        base_stmt = base_stmt.where(and_(*conds))

    # Get total count
    count_stmt = select(func.count()).select_from(base_stmt.subquery())
    count_res = await session.execute(count_stmt)
    total_count = count_res.scalar() or 0

    # Get paginated data
    stmt = base_stmt.order_by(models.Schedule.created_at.desc()).limit(page_size).offset((page - 1) * page_size)

    res = await session.execute(stmt)
    items: list[models.Schedule] = list(res.scalars().all())
    email_map = await get_user_email_map(
        session, {s.created_by for s in items} | {s.modified_by for s in items}
    )
    # Fetch report names for all referenced report_ids
    report_ids = sorted({s.report_id for s in items if s.report_id})
    name_by_id: dict[int, str] = {}
    if report_ids:
        rres = await session.execute(
            select(models.Report.id, models.Report.name).where(
                models.Report.id.in_(report_ids)
            )
        )
        for rid, rname in rres.all():
            name_by_id[int(rid)] = str(rname)
    out: list[ScheduleOut] = []
    for s in items:
        recipients_list: list[str] = []
        if s.recipients:
            recipients_list = [
                part.strip() for part in s.recipients.split(",") if part.strip()
            ]
        # Compute next run dynamically for display when active
        computed_next = None
        status_flag = (s.schedule_status or (s.status or "")).lower()
        if status_flag == "active":
            computed_next = _compute_next_run(
                s.frequency,
                time_of_day=s.time_of_day,
                day_of_week=s.day_of_week,
                day_of_month=s.day_of_month,
                month_of_year=getattr(s, 'month_of_year', None),
                month_of_quarter=getattr(s, 'month_of_quarter', None),
                run_date=s.run_date,
                start_date=getattr(s, "start_date", None),
            )
        out.append(
            ScheduleOut(
                id=s.id,
                name=s.name,
                recurrence=s.frequency,
                schedule_status=s.schedule_status
                or (s.status.lower() if s.status else "active"),
                next_run_at=computed_next or s.next_run_at,
                last_run_at=s.last_run_at,
                report_id=s.report_id,
                report_name=name_by_id.get(s.report_id or -1),
                recipients=recipients_list,
                created_at=s.created_at,
                created_by_email=email_map.get(s.created_by or -1),
                modified_by_email=email_map.get(s.modified_by or -1),
                time_of_day=s.time_of_day,
                day_of_week=s.day_of_week,
                day_of_month=s.day_of_month,
                month_of_year=getattr(s, "month_of_year", None),
                month_of_quarter=getattr(s, 'month_of_quarter', None),
                start_date=getattr(s, "start_date", None),
                run_date=s.run_date,
            )
        )
    return SchedulesListResponse(totalCount=total_count, items=out)


@router.post("/bulk-delete")
async def bulk_delete_schedules(
    payload: dict,
    session: AsyncSession = Depends(get_session),
):
    ids = payload.get("ids", [])
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="ids list is required")
    numeric_ids = [int(i) for i in ids if isinstance(i, (int, str)) and str(i).isdigit()]
    if not numeric_ids:
        raise HTTPException(status_code=400, detail="No valid ids provided")
    try:
        result = await session.execute(
            delete(models.Schedule).where(models.Schedule.id.in_(numeric_ids))
        )
        await session.commit()
        return {"deleted": result.rowcount or 0}
    except Exception as err:
        await session.rollback()
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise


@router.post("/", response_model=list[ScheduleOut], status_code=201)
async def create_schedule(
    payload: ScheduleIn,
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
):
    logger.info(
        "#schedules: Creating schedule name=%s report_id=%s report_ids=%s",
        payload.name,
        payload.report_id,
        payload.report_ids,
    )
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="Schedule name is required")

    recipients_list = _normalize_and_validate_recipients(payload.recipients)
    recipients_csv = ",".join(recipients_list)

    # Validate recurrence
    valid_recurrences = {
        "daily",
        "weekly",
        "monthly",
        "quarterly",
        "yearly",
        "annual",
        "annually",
        "one-time",
        "one time",
        "once",
    }
    if (payload.recurrence or "").strip().lower() not in valid_recurrences:
        raise HTTPException(
            status_code=422,
            detail="Invalid recurrence; expected Daily/Weekly/Monthly/One-time",
        )

    # Resolve report ids (single + multi-select + optional report_name)
    resolved_report_id = payload.report_id
    if resolved_report_id is None and payload.report_name:
        resolved_report_id = await session.scalar(
            select(models.Report.id).where(models.Report.name == payload.report_name)
        )
    report_ids: list[int] = []
    if payload.report_ids:
        report_ids.extend([rid for rid in payload.report_ids if rid is not None])
    if resolved_report_id is not None:
        report_ids.append(resolved_report_id)

    # Deduplicate while preserving order
    seen_ids: set[int] = set()
    deduped_report_ids: list[int] = []
    for rid in report_ids:
        if rid in seen_ids:
            continue
        seen_ids.add(rid)
        deduped_report_ids.append(rid)
    report_ids = deduped_report_ids

    report_lookup: dict[int, str] = {}
    if report_ids:
        rows = await session.execute(
            select(models.Report.id, models.Report.name).where(
                models.Report.id.in_(report_ids)
            )
        )
        report_lookup = {rid: rname for rid, rname in rows.all()}
        missing = [rid for rid in report_ids if rid not in report_lookup]
        if missing:
            raise HTTPException(
                status_code=404, detail=f"Report(s) {missing} not found"
            )

    if not report_ids:
        raise HTTPException(
            status_code=422, detail="A report_id or report_ids is required"
        )

    multiple_reports = len(report_ids) > 1
    candidates: list[tuple[str, int | None]] = []
    if report_ids:
        for rid in report_ids:
            suffix = report_lookup.get(rid)
            schedule_name = (
                f"{name} - {suffix}" if multiple_reports and suffix else name
            )
            candidates.append((schedule_name[:255], rid))

    unique_lower_names = {cand[0].lower() for cand in candidates}
    dup_stmt = select(models.Schedule.name).where(
        func.lower(models.Schedule.name).in_(unique_lower_names)
    )
    dup_existing = list(await session.scalars(dup_stmt))
    if dup_existing:
        raise HTTPException(
            status_code=409,
            detail=f"Schedule with this name {dup_existing[0]} already exists",
        )

    try:
        current_user = await get_user_from_claims(session, claims)
        current_user_id = current_user.id if current_user else None
        next_run = _compute_next_run(
            payload.recurrence,
            time_of_day=payload.time_of_day,
            day_of_week=payload.day_of_week,
            day_of_month=payload.day_of_month,
            month_of_year=payload.month_of_year,
            month_of_quarter=payload.month_of_quarter,
            run_date=payload.run_date,
            start_date=payload.start_date,
        )

        new_items: list[models.Schedule] = []
        for schedule_name, rid in candidates:
            item = models.Schedule(
                name=schedule_name,
                report_id=rid,
                frequency=payload.recurrence,
                recipients=recipients_csv,
                status="Active",
                schedule_status="active",
                time_of_day=payload.time_of_day,
                day_of_week=payload.day_of_week,
                day_of_month=payload.day_of_month,
                month_of_year=payload.month_of_year,
                month_of_quarter=payload.month_of_quarter,
                start_date=payload.start_date,
                run_date=payload.run_date,
                next_run_at=next_run,
                created_by=current_user_id,
                modified_by=current_user_id,
            )
            session.add(item)
            new_items.append(item)

        await session.commit()
        for item in new_items:
            await session.refresh(item)

        updated_reports = {item.report_id for item in new_items if item.report_id}
        if updated_reports:
            rpt_rows = await session.execute(
                select(models.Report).where(models.Report.id.in_(updated_reports))
            )
            for rpt in rpt_rows.scalars().unique():
                rpt.schedule_status = "scheduled"
            try:
                await session.commit()
            except Exception:
                await session.rollback()

        out: list[ScheduleOut] = []
        for item in new_items:
            recipients_list = [
                part.strip()
                for part in (item.recipients or "").split(",")
                if part.strip()
            ]
            out.append(
                ScheduleOut(
                    id=item.id,
                    name=item.name,
                    recurrence=item.frequency,
                    schedule_status=item.schedule_status,
                    next_run_at=item.next_run_at,
                    report_id=item.report_id,
                    report_name=report_lookup.get(item.report_id)
                    if item.report_id
                    else None,
                    recipients=recipients_list,
                    created_at=item.created_at,
                    created_by_email=current_user.email if current_user else None,
                    modified_by_email=current_user.email if current_user else None,
                    time_of_day=item.time_of_day,
                    day_of_week=item.day_of_week,
                    day_of_month=item.day_of_month,
                    month_of_year=item.month_of_year,
                    month_of_quarter=item.month_of_quarter,
                    start_date=item.start_date,
                    run_date=item.run_date,
                )
            )
        return out
    except Exception as err:
        logger.error(
            "#schedules: Schedule creation failed for name=%s",
            getattr(payload, "name", None),
            exc_info=err,
        )
        await session.rollback()
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(
                session, err, conflict_message="Schedule name already exists"
            )
        raise


@router.get("/{schedule_id}", response_model=ScheduleOut)
async def get_schedule(schedule_id: int, session: AsyncSession = Depends(get_session)):
    logger.info("#schedules: Getting schedule with id=%s", schedule_id)
    item = await session.get(models.Schedule, schedule_id)
    if not item:
        raise HTTPException(status_code=404, detail="Schedule not found")
    recipients_list = [
        part.strip() for part in (item.recipients or "").split(",") if part.strip()
    ]
    report_name = None
    if item.report_id:
        r = await session.get(models.Report, item.report_id)
        if r:
            report_name = r.name
    email_map = await get_user_email_map(session, {item.created_by, item.modified_by})
    return ScheduleOut(
        id=item.id,
        name=item.name,
        recurrence=item.frequency,
        schedule_status=item.schedule_status
        or (item.status.lower() if item.status else "active"),
        next_run_at=item.next_run_at,
        report_id=item.report_id,
        report_name=report_name,
        recipients=recipients_list,
        created_at=item.created_at,
        created_by_email=email_map.get(item.created_by or -1),
        modified_by_email=email_map.get(item.modified_by or -1),
        time_of_day=item.time_of_day,
        day_of_week=item.day_of_week,
        day_of_month=item.day_of_month,
        month_of_year=item.month_of_year,
        month_of_quarter=item.month_of_quarter,
        start_date=item.start_date,
        run_date=item.run_date,
    )


@router.patch("/{schedule_id}", response_model=ScheduleOut)
async def patch_schedule(
    schedule_id: int,
    payload: ScheduleUpdate,
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
):
    logger.info("#schedules: Updating(patch) schedule with id=%s", schedule_id)
    item = await session.get(models.Schedule, schedule_id)
    if not item:
        raise HTTPException(status_code=404, detail="Schedule not found")
    try:
        current_user = await get_user_from_claims(session, claims)
        current_user_id = current_user.id if current_user else None
        data = payload.model_dump(exclude_unset=True)
        # Map allowed fields
        if "name" in data:
            item.name = data["name"]
        if "status" in data:
            item.status = data["status"]
            item.schedule_status = (data["status"] or "").lower()
        # Support either 'recurrence' or 'frequency'
        if "recurrence" in data and data["recurrence"] is not None:
            item.frequency = data["recurrence"]
        elif "frequency" in data and data["frequency"] is not None:
            item.frequency = data["frequency"]
        if "recipients" in data and data["recipients"] is not None:
            normalized_recipients = _normalize_and_validate_recipients(
                data["recipients"]
            )
            item.recipients = ",".join(normalized_recipients)
        if "time_of_day" in data:
            item.time_of_day = data["time_of_day"]
        if "day_of_week" in data:
            item.day_of_week = data["day_of_week"]
        if "day_of_month" in data:
            try:
                item.day_of_month = (
                    int(data["day_of_month"])
                    if data["day_of_month"] is not None
                    else None
                )
            except Exception:
                item.day_of_month = None
        if "month_of_year" in data:
            try:
                item.month_of_year = (
                    int(data["month_of_year"])
                    if data["month_of_year"] is not None
                    else None
                )
            except Exception:
                item.month_of_year = None
        if "month_of_quarter" in data:
            try:
                item.month_of_quarter = (
                    int(data["month_of_quarter"])
                    if data["month_of_quarter"] is not None
                    else None
                )
            except Exception:
                item.month_of_quarter = None
        if "start_date" in data:
            item.start_date = data["start_date"]
        if "run_date" in data:
            item.run_date = data["run_date"]

        if current_user_id:
            item.modified_by = current_user_id
            # Don't backfill created_by for historical schedules

        # Recompute next run if active
        if (item.schedule_status or "active").lower() == "active":
            item.next_run_at = _compute_next_run(
                item.frequency,
                time_of_day=item.time_of_day,
                day_of_week=item.day_of_week,
                day_of_month=item.day_of_month,
                month_of_year=getattr(item, 'month_of_year', None),
                month_of_quarter=getattr(item, 'month_of_quarter', None),
                start_date=item.start_date,
                run_date=item.run_date,
            )
        await session.commit()
        await session.refresh(item)
        recipients_list = [
            part.strip() for part in (item.recipients or "").split(",") if part.strip()
        ]
        rname = None
        if item.report_id:
            r = await session.get(models.Report, item.report_id)
            if r:
                rname = r.name
        email_map = await get_user_email_map(session, {item.created_by, item.modified_by})
        return ScheduleOut(
            id=item.id,
            name=item.name,
            recurrence=item.frequency,
            schedule_status=item.schedule_status
            or (item.status.lower() if item.status else "active"),
            next_run_at=item.next_run_at,
            report_id=item.report_id,
            report_name=rname,
            recipients=recipients_list,
            created_at=item.created_at,
            created_by_email=email_map.get(item.created_by or -1),
            modified_by_email=email_map.get(item.modified_by or -1),
            time_of_day=item.time_of_day,
            day_of_week=item.day_of_week,
            day_of_month=item.day_of_month,
            month_of_year=item.month_of_year,
            month_of_quarter=item.month_of_quarter,
            start_date=item.start_date,
            run_date=item.run_date,
        )
    except Exception as err:
        logger.error("#schedules: Schedule updation(patch) failed for id=%s", schedule_id, exc_info=err)
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise


@router.put("/{schedule_id}", response_model=ScheduleOut)
async def put_schedule(
    schedule_id: int,
    payload: ScheduleIn,
    session: AsyncSession = Depends(get_session),
    claims: dict | None = Depends(require_auth),
):
    item = await session.get(models.Schedule, schedule_id)
    if not item:
        raise HTTPException(status_code=404, detail="Schedule not found")
    try:
        current_user = await get_user_from_claims(session, claims)
        current_user_id = current_user.id if current_user else None
        normalized_recipients = _normalize_and_validate_recipients(payload.recipients)
        for k, v in payload.model_dump().items():
            if k == "recipients":
                continue
            if k == "recurrence":
                item.frequency = v
                continue
            setattr(item, k, v)
        item.recipients = ",".join(normalized_recipients)
        if current_user_id:
            item.modified_by = current_user_id
            logger.debug(
                "put_schedule: Set modified_by=%s for schedule_id=%s (created_by=%s)",
                current_user_id, schedule_id, item.created_by
            )
            # Don't backfill created_by for historical schedules
        if (item.schedule_status or "active").lower() == "active":
            item.next_run_at = _compute_next_run(
                item.frequency,
                time_of_day=item.time_of_day,
                day_of_week=item.day_of_week,
                day_of_month=item.day_of_month,
                month_of_year=getattr(item, "month_of_year", None),
                month_of_quarter=getattr(item, "month_of_quarter", None),
                start_date=item.start_date,
                run_date=item.run_date,
            )
        await session.commit()
        await session.refresh(item)
        email_map = await get_user_email_map(session, {item.created_by, item.modified_by})
        recipients_list = [
            part.strip() for part in (item.recipients or "").split(",") if part.strip()
        ]
        rname = None
        if item.report_id:
            r = await session.get(models.Report, item.report_id)
            if r:
                rname = r.name
        return ScheduleOut(
            id=item.id,
            name=item.name,
            recurrence=item.frequency,
            schedule_status=item.schedule_status
            or (item.status.lower() if item.status else "active"),
            next_run_at=item.next_run_at,
            report_id=item.report_id,
            report_name=rname,
            recipients=recipients_list,
            created_at=item.created_at,
            created_by_email=email_map.get(item.created_by or -1),
            modified_by_email=email_map.get(item.modified_by or -1),
            time_of_day=item.time_of_day,
            day_of_week=item.day_of_week,
            day_of_month=item.day_of_month,
            month_of_year=getattr(item, "month_of_year", None),
            month_of_quarter=getattr(item, "month_of_quarter", None),
            start_date=item.start_date,
            run_date=item.run_date,
        )
    except Exception as err:
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise


@router.delete("/{schedule_id}", status_code=204)
async def delete_schedule(
    schedule_id: int, session: AsyncSession = Depends(get_session)
):
    logger.info("#schedules: Deleting schedule with id=%s", schedule_id)
    item = await session.get(models.Schedule, schedule_id)
    if not item:
        raise HTTPException(status_code=404, detail="Schedule not found")
    try:
        await session.delete(item)
        await session.commit()
        return None
    except Exception as err:
        logger.error("#schedules: Schedule deletion failed for id=%s", schedule_id, exc_info=err)
        if isinstance(err, SQLAlchemyError):
            await handle_db_error(session, err)
        raise

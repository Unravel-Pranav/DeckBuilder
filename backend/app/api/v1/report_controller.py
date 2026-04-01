"""Report controller — thin router, delegates to ReportService."""
from fastapi import APIRouter

from app.core.dependencies import AsyncSessionDep
from app.schemas.report_schema import ReportCreate, ReportListResponse, ReportResponse, ReportUpdate
from app.schemas.response import success_response
from app.services.report_service import ReportService

router = APIRouter()


@router.get("")
async def list_reports(session: AsyncSessionDep):
    result = await ReportService(session).list_reports()
    return success_response(ReportListResponse.model_validate(result).model_dump())


@router.post("", status_code=201)
async def create_report(body: ReportCreate, session: AsyncSessionDep):
    report = await ReportService(session).create_report(body)
    return success_response(ReportResponse.model_validate(report).model_dump())


@router.get("/{report_id}")
async def get_report(report_id: int, session: AsyncSessionDep):
    report = await ReportService(session).get_report(report_id)
    return success_response(ReportResponse.model_validate(report).model_dump())


@router.put("/{report_id}")
async def update_report(report_id: int, body: ReportUpdate, session: AsyncSessionDep):
    report = await ReportService(session).update_report(report_id, body)
    return success_response(ReportResponse.model_validate(report).model_dump())


@router.delete("/{report_id}")
async def delete_report(report_id: int, session: AsyncSessionDep):
    deleted = await ReportService(session).delete_report(report_id)
    return success_response({"deleted": deleted})

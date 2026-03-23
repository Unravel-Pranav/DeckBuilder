"""Report controller — thin router, delegates to ReportService."""
from fastapi import APIRouter
from app.core.dependencies import AsyncSessionDep
from app.schemas.report_schema import ReportCreate, ReportResponse, ReportUpdate, ReportListResponse
from app.services.report_service import ReportService

router = APIRouter()

@router.get("", response_model=ReportListResponse)
async def list_reports(session: AsyncSessionDep):
    return await ReportService(session).list_reports()

@router.post("", response_model=ReportResponse, status_code=201)
async def create_report(body: ReportCreate, session: AsyncSessionDep):
    report = await ReportService(session).create_report(body)
    return ReportResponse.model_validate(report)

@router.get("/{report_id}", response_model=ReportResponse)
async def get_report(report_id: int, session: AsyncSessionDep):
    report = await ReportService(session).get_report(report_id)
    return ReportResponse.model_validate(report)

@router.put("/{report_id}", response_model=ReportResponse)
async def update_report(report_id: int, body: ReportUpdate, session: AsyncSessionDep):
    report = await ReportService(session).update_report(report_id, body)
    return ReportResponse.model_validate(report)

@router.delete("/{report_id}")
async def delete_report(report_id: int, session: AsyncSessionDep):
    return {"deleted": await ReportService(session).delete_report(report_id)}

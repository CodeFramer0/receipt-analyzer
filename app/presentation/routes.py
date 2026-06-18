import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.application.dto import (
    AnalysisResponseDto,
    FileResultDto,
    ForgeryIndicatorDto,
    PdfTechnicalInfoDto,
    ReportDetailDto,
)
from app.config import settings
from app.domain.entities import AnalysisReport, FileResult
from app.domain.enums import AnalysisStatus
from app.infrastructure.celery.tasks import analyze_receipts_task
from app.infrastructure.storage.json_report_repository import JsonReportRepository

router = APIRouter()

PDF_MAGIC_BYTES = b"%PDF-"
MAX_FILE_SIZE = 10 * 1024 * 1024


def _get_repository() -> JsonReportRepository:
    return JsonReportRepository(settings.reports_dir)


def _file_result_to_dto(fr: FileResult) -> FileResultDto:
    indicators = []
    if fr.score:
        indicators = [
            ForgeryIndicatorDto(
                anomaly_type=ind.anomaly_type,
                description=ind.description,
                severity=ind.severity,
                target_field=ind.target_field,
            )
            for ind in fr.score.indicators
        ]

    return FileResultDto(
        filename=fr.filename,
        verdict=fr.verdict,
        score=fr.score.total_score if fr.score else 0,
        reasons=indicators,
    )


def _report_to_dto(report: AnalysisReport) -> ReportDetailDto:
    return ReportDetailDto(
        analysis_id=report.id,
        status=report.status,
        files=[_file_result_to_dto(f) for f in report.files],
        created_at=report.created_at,
    )


async def _validate_pdf(file: UploadFile) -> bytes:
    content = await file.read()

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File {file.filename} exceeds 10MB limit",
        )

    if not content.startswith(PDF_MAGIC_BYTES):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File {file.filename} is not a valid PDF",
        )

    return content


@router.post(
    "/check-receipt",
    response_model=AnalysisResponseDto,
    status_code=status.HTTP_202_ACCEPTED,
)
async def check_receipt(
    files: list[UploadFile] = File(...),
):
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one PDF file is required",
        )

    report_id = str(uuid.uuid4())
    upload_dir = settings.uploads_dir / report_id
    upload_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: list[str] = []
    for i, file in enumerate(files):
        content = await _validate_pdf(file)
        filename = file.filename or f"receipt_{i + 1}.pdf"
        path = upload_dir / filename
        path.write_bytes(content)
        saved_paths.append(str(path))

    repo = _get_repository()
    initial_report = AnalysisReport(id=report_id, status=AnalysisStatus.PENDING)
    repo.save(initial_report)

    analyze_receipts_task.delay(report_id, saved_paths)

    return AnalysisResponseDto(analysis_id=report_id, status=AnalysisStatus.PENDING)


@router.get("/receipt/{analysis_id}", response_model=ReportDetailDto)
async def get_receipt(analysis_id: str):
    repo = _get_repository()
    report = repo.get_by_id(analysis_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis {analysis_id} not found",
        )
    return _report_to_dto(report)

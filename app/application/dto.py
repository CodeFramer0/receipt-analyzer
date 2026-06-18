from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.enums import AnalysisStatus, AnomalyType, ReceiptVerdict


class AnalysisResponseDto(BaseModel):
    analysis_id: str
    status: AnalysisStatus


class ForgeryIndicatorDto(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    anomaly_type: AnomalyType
    description: str
    severity: float
    target_field: str = ""


class PdfTechnicalInfoDto(BaseModel):
    producer: str
    creator: str
    pdf_version: str
    page_height: float
    page_width: float
    is_encrypted: bool
    revision_count: int = 0
    keywords: str = ""


class FileResultDto(BaseModel):
    filename: str
    verdict: ReceiptVerdict
    score: float
    reasons: list[ForgeryIndicatorDto]
    technical_info: PdfTechnicalInfoDto | None = None


class ReportDetailDto(BaseModel):
    analysis_id: str
    status: AnalysisStatus
    files: list[FileResultDto]
    created_at: datetime

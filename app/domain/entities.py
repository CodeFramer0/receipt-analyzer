from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.domain.enums import AnalysisStatus, ReceiptVerdict
from app.domain.value_objects import AnomalyScore, FontInfo, PdfMetadata


@dataclass
class Receipt:
    filename: str
    text_content: str
    metadata: PdfMetadata
    fonts: list[FontInfo] = field(default_factory=list)


@dataclass
class FileResult:
    filename: str
    verdict: ReceiptVerdict
    score: AnomalyScore | None = None


@dataclass
class AnalysisReport:
    id: str
    status: AnalysisStatus
    files: list[FileResult] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

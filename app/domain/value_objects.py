from dataclasses import dataclass, field
from datetime import datetime

from app.domain.enums import AnomalyType


@dataclass(frozen=True)
class PdfMetadata:
    creator: str = ""
    producer: str = ""
    creation_date: datetime | None = None
    modification_date: datetime | None = None
    page_count: int = 0
    pdf_version: str = ""
    is_encrypted: bool = False
    has_xmp: bool = False
    keywords: str = ""
    page_width: float = 0.0
    page_height: float = 0.0
    file_size: int = 0


@dataclass(frozen=True)
class FontInfo:
    name: str
    size: float
    is_embedded: bool
    page_number: int


@dataclass(frozen=True)
class ForgeryIndicator:
    anomaly_type: AnomalyType
    description: str
    severity: float
    target_field: str = ""


@dataclass(frozen=True)
class AnomalyScore:
    receipt_filename: str
    total_score: float
    indicators: tuple[ForgeryIndicator, ...] = field(default_factory=tuple)

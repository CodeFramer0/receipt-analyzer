from abc import ABC, abstractmethod
from pathlib import Path

from app.domain.entities import AnalysisReport, Receipt
from app.domain.value_objects import ForgeryIndicator, PdfMetadata


class PdfTextExtractor(ABC):
    @abstractmethod
    def extract(self, file_path: Path) -> Receipt: ...


class PdfMetadataExtractor(ABC):
    @abstractmethod
    def extract_metadata(self, file_path: Path) -> PdfMetadata: ...

    @abstractmethod
    def count_revisions(self, file_path: Path) -> int: ...


class StructureAnalyzerPort(ABC):
    @abstractmethod
    def analyze(
        self, receipt: Receipt, revision_count: int, object_info: object | None = None
    ) -> list[ForgeryIndicator]: ...


class ReportRepository(ABC):
    @abstractmethod
    def save(self, report: AnalysisReport) -> None: ...

    @abstractmethod
    def get_by_id(self, report_id: str) -> AnalysisReport | None: ...

    @abstractmethod
    def get_all(self) -> list[AnalysisReport]: ...


class ReferenceStore(ABC):
    @abstractmethod
    def get_reference_metadata(self) -> list[PdfMetadata]: ...

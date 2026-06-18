from pathlib import Path

from app.config import settings
from app.domain.enums import AnalysisStatus
from app.infrastructure.analysis.receipt_analyzer import ReceiptAnalyzerService
from app.infrastructure.analysis.reference_store import FileReferenceStore
from app.infrastructure.analysis.scorer import ForgeryScorer
from app.infrastructure.celery.app import celery_app
from app.infrastructure.pdf.metadata_extractor import PikePdfMetadataExtractor
from app.infrastructure.pdf.structure_analyzer import StructureAnalyzer
from app.infrastructure.pdf.text_extractor import PdfPlumberTextExtractor
from app.infrastructure.storage.json_report_repository import JsonReportRepository


def _build_analyzer() -> ReceiptAnalyzerService:
    text_extractor = PdfPlumberTextExtractor()
    metadata_extractor = PikePdfMetadataExtractor()

    return ReceiptAnalyzerService(
        text_extractor=text_extractor,
        metadata_extractor=metadata_extractor,
        structure_analyzer=StructureAnalyzer(),
        scorer=ForgeryScorer(),
        reference_store=FileReferenceStore(
            reference_dir=settings.references_dir,
            text_extractor=text_extractor,
            metadata_extractor=metadata_extractor,
        ),
    )


def _get_repository() -> JsonReportRepository:
    return JsonReportRepository(settings.reports_dir)


@celery_app.task(name="analyze_receipts", bind=True)
def analyze_receipts_task(self, report_id: str, file_paths: list[str]) -> dict:
    repo = _get_repository()

    report = repo.get_by_id(report_id)
    if report:
        report.status = AnalysisStatus.PROCESSING
        repo.save(report)

    try:
        analyzer = _build_analyzer()
        paths = [Path(p) for p in file_paths]
        result = analyzer.analyze(report_id, paths)
        repo.save(result)
        return {"status": "completed", "report_id": report_id}
    except Exception as exc:
        if report:
            report.status = AnalysisStatus.FAILED
            repo.save(report)
        raise self.retry(exc=exc, countdown=5, max_retries=2)

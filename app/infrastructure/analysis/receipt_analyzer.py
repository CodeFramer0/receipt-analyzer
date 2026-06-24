from pathlib import Path

from app.domain.entities import AnalysisReport, FileResult, Receipt
from app.domain.enums import AnalysisStatus, ReceiptVerdict
from app.domain.interfaces import PdfMetadataExtractor, PdfTextExtractor, StructureAnalyzerPort
from app.infrastructure.analysis.reference_store import FileReferenceStore
from app.infrastructure.analysis.scorer import ForgeryScorer
from app.infrastructure.pdf.bank_profiles import detect_bank
from app.infrastructure.pdf.object_extractor import extract_object_info

FAKE_THRESHOLD = 2.0
SUSPICIOUS_THRESHOLD = 0.8


class ReceiptAnalyzerService:
    def __init__(
        self,
        text_extractor: PdfTextExtractor,
        metadata_extractor: PdfMetadataExtractor,
        structure_analyzer: StructureAnalyzerPort,
        scorer: ForgeryScorer,
        reference_store: FileReferenceStore,
    ) -> None:
        self._text_extractor = text_extractor
        self._metadata_extractor = metadata_extractor
        self._structure_analyzer = structure_analyzer
        self._scorer = scorer
        self._reference_store = reference_store

    def analyze(self, report_id: str, file_paths: list[Path]) -> AnalysisReport:
        results: list[FileResult] = []
        for file_path in file_paths:
            result = self._analyze_single(file_path)
            results.append(result)
        return AnalysisReport(
            id=report_id,
            status=AnalysisStatus.COMPLETED,
            files=results,
        )

    def _analyze_single(self, file_path: Path) -> FileResult:
        try:
            receipt = self._build_receipt(file_path)
            rev_count = self._metadata_extractor.count_revisions(file_path)
            obj_info = extract_object_info(file_path)
        except Exception:
            return FileResult(
                filename=file_path.name,
                verdict=ReceiptVerdict.UNKNOWN,
            )

        indicators = self._structure_analyzer.analyze(receipt, rev_count, obj_info)

        ref_indicators = self._reference_store.compare_with_references(receipt, file_path)
        indicators.extend(ref_indicators)

        score = self._scorer.score(receipt.filename, indicators)
        verdict = self._determine_verdict(score.total_score, len(indicators))

        profile = detect_bank(receipt.text_content, receipt.metadata.producer)
        bank_name = profile.name if profile else "unknown"

        return FileResult(
            filename=receipt.filename,
            verdict=verdict,
            score=score,
            metadata=receipt.metadata,
            revision_count=rev_count,
            detected_bank=bank_name,
        )

    def _build_receipt(self, file_path: Path) -> Receipt:
        receipt = self._text_extractor.extract(file_path)
        metadata = self._metadata_extractor.extract_metadata(file_path)
        return Receipt(
            filename=receipt.filename,
            text_content=receipt.text_content,
            metadata=metadata,
            fonts=receipt.fonts,
        )

    @staticmethod
    def _determine_verdict(total_score: float, indicator_count: int) -> ReceiptVerdict:
        if indicator_count == 0:
            return ReceiptVerdict.ORIGINAL
        if total_score >= FAKE_THRESHOLD:
            return ReceiptVerdict.FAKE
        if total_score >= SUSPICIOUS_THRESHOLD:
            return ReceiptVerdict.SUSPICIOUS
        return ReceiptVerdict.ORIGINAL

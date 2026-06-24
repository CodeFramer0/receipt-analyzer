import tempfile
from pathlib import Path

from app.domain.enums import ReceiptVerdict
from app.infrastructure.analysis.receipt_analyzer import ReceiptAnalyzerService
from app.infrastructure.analysis.reference_store import FileReferenceStore
from app.infrastructure.analysis.scorer import ForgeryScorer
from app.infrastructure.pdf.metadata_extractor import PikePdfMetadataExtractor
from app.infrastructure.pdf.structure_analyzer import StructureAnalyzer
from app.infrastructure.pdf.text_extractor import PdfPlumberTextExtractor


def _build_analyzer(ref_dir: Path | None = None):
    te = PdfPlumberTextExtractor()
    me = PikePdfMetadataExtractor()
    return ReceiptAnalyzerService(
        text_extractor=te,
        metadata_extractor=me,
        structure_analyzer=StructureAnalyzer(),
        scorer=ForgeryScorer(),
        reference_store=FileReferenceStore(
            ref_dir or Path("references"), te, me
        ),
    )


def test_corrupted_pdf_returns_unknown():
    analyzer = _build_analyzer()

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"%PDF-1.4 corrupted content that is not a real pdf")
        f.flush()
        result = analyzer.analyze("test-corrupt", [Path(f.name)])

    assert len(result.files) == 1
    assert result.files[0].verdict == ReceiptVerdict.UNKNOWN

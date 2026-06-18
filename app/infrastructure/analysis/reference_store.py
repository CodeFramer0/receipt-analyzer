from pathlib import Path

from app.domain.entities import Receipt
from app.domain.enums import AnomalyType
from app.domain.interfaces import PdfMetadataExtractor, PdfTextExtractor, ReferenceStore
from app.domain.value_objects import ForgeryIndicator, PdfMetadata


class FileReferenceStore(ReferenceStore):
    def __init__(
        self,
        reference_dir: Path,
        text_extractor: PdfTextExtractor,
        metadata_extractor: PdfMetadataExtractor,
    ) -> None:
        self._reference_dir = reference_dir
        self._text_extractor = text_extractor
        self._metadata_extractor = metadata_extractor
        self._ref_metadata: list[PdfMetadata] | None = None

    def get_reference_metadata(self) -> list[PdfMetadata]:
        if self._ref_metadata is not None:
            return self._ref_metadata

        self._ref_metadata = []
        if not self._reference_dir.exists():
            return self._ref_metadata

        for pdf_path in self._reference_dir.glob("*.pdf"):
            meta = self._metadata_extractor.extract_metadata(pdf_path)
            self._ref_metadata.append(meta)

        return self._ref_metadata

    def compare_with_references(self, receipt: Receipt) -> list[ForgeryIndicator]:
        ref_list = self.get_reference_metadata()
        if not ref_list:
            return []

        indicators: list[ForgeryIndicator] = []

        ref_producers = {r.producer for r in ref_list if r.producer}
        if ref_producers and receipt.metadata.producer:
            if receipt.metadata.producer not in ref_producers:
                indicators.append(
                    ForgeryIndicator(
                        anomaly_type=AnomalyType.TOOL_MISMATCH,
                        description=(
                            f"Producer '{receipt.metadata.producer}' does not match "
                            f"any reference producer: {ref_producers}"
                        ),
                        severity=0.9,
                        target_field="producer",
                    )
                )

        ref_heights = {r.page_height for r in ref_list if r.page_height > 0}
        if ref_heights and receipt.metadata.page_height > 0:
            if receipt.metadata.page_height not in ref_heights:
                min_diff = min(
                    abs(receipt.metadata.page_height - rh) for rh in ref_heights
                )
                if min_diff > 5.0:
                    indicators.append(
                        ForgeryIndicator(
                            anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                            description=(
                                f"Page height {receipt.metadata.page_height} does not match "
                                f"any reference height: {ref_heights}"
                            ),
                            severity=0.6,
                            target_field="page_dimensions",
                        )
                    )

        ref_versions = {r.pdf_version for r in ref_list if r.pdf_version}
        if ref_versions and receipt.metadata.pdf_version:
            if receipt.metadata.pdf_version not in ref_versions:
                indicators.append(
                    ForgeryIndicator(
                        anomaly_type=AnomalyType.METADATA_MISMATCH,
                        description=(
                            f"PDF version '{receipt.metadata.pdf_version}' does not match "
                            f"reference versions: {ref_versions}"
                        ),
                        severity=0.5,
                        target_field="pdf_version",
                    )
                )

        return indicators

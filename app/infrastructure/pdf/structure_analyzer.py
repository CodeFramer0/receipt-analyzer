import re

from app.domain.entities import Receipt
from app.domain.enums import AnomalyType
from app.domain.interfaces import StructureAnalyzerPort
from app.domain.value_objects import ForgeryIndicator, PdfMetadata
from app.infrastructure.pdf.bank_profiles import BankProfile, ReceiptSpec, detect_bank
from app.infrastructure.pdf.object_extractor import PdfObjectInfo

UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
MD5_PATTERN = re.compile(r"^[0-9a-f]{32}$")

NON_GENUINE_PRODUCERS = [
    "dompdf", "mpdf", "wkhtmltopdf", "tcpdf", "fpdf",
    "reportlab", "prince", "weasyprint",
]

SUSPICIOUS_PRODUCERS = [
    "nitro", "pdfelement", "foxit phantompdf", "ilovepdf",
    "sejda", "smallpdf", "canva", "adobe photoshop", "gimp",
]

EXPECTED_FILENAME_KEYWORD = "receipt"


class StructureAnalyzer(StructureAnalyzerPort):
    def analyze(
        self, receipt: Receipt, revision_count: int, object_info: PdfObjectInfo | None = None
    ) -> list[ForgeryIndicator]:
        indicators: list[ForgeryIndicator] = []
        indicators.extend(self._check_filename(receipt))
        indicators.extend(self._check_producer_authenticity(receipt.metadata))
        indicators.extend(self._check_bank_specific(receipt, object_info))
        indicators.extend(self._check_metadata_dates(receipt.metadata))
        indicators.extend(self._check_keywords(receipt.metadata))
        indicators.extend(self._check_fonts(receipt))
        indicators.extend(self._check_revisions(revision_count))
        indicators.extend(self._check_text_layer(receipt))
        return indicators

    def _check_filename(self, receipt: Receipt) -> list[ForgeryIndicator]:
        results: list[ForgeryIndicator] = []
        if EXPECTED_FILENAME_KEYWORD not in receipt.filename.lower():
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.METADATA_MISMATCH,
                    description=(
                        f"Filename '{receipt.filename}' does not contain "
                        f"expected keyword '{EXPECTED_FILENAME_KEYWORD}'"
                    ),
                    severity=0.3,
                    target_field="filename",
                )
            )
        return results

    def _check_bank_specific(
        self, receipt: Receipt, object_info: PdfObjectInfo | None
    ) -> list[ForgeryIndicator]:
        results: list[ForgeryIndicator] = []
        profile = detect_bank(receipt.text_content, receipt.metadata.producer)

        if profile is None:
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                    description="Could not identify bank from receipt content or producer",
                    severity=0.5,
                    target_field="bank_detection",
                )
            )
            return results

        if profile.expected_email:
            if profile.expected_email not in receipt.text_content.lower():
                results.append(
                    ForgeryIndicator(
                        anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                        description=(
                            f"Expected email '{profile.expected_email}' "
                            f"not found in {profile.name} receipt text"
                        ),
                        severity=0.9,
                        target_field="text_content",
                    )
                )

        results.extend(self._check_producer_match(receipt.metadata, profile))
        results.extend(self._check_creator_match(receipt.metadata, profile))
        results.extend(self._check_version_match(receipt.metadata, profile))

        if profile.has_keywords and not receipt.metadata.keywords:
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.METADATA_MISMATCH,
                    description=(
                        f"Keywords field is empty - genuine {profile.name} "
                        f"receipts contain receipt metadata"
                    ),
                    severity=0.8,
                    target_field="keywords",
                )
            )

        if profile.specs and object_info:
            results.extend(self._check_spec(receipt, object_info, profile))

        return results

    def _check_producer_match(
        self, meta: PdfMetadata, profile: BankProfile
    ) -> list[ForgeryIndicator]:
        results: list[ForgeryIndicator] = []
        producer_lower = meta.producer.lower()
        if meta.producer and not any(ep in producer_lower for ep in profile.expected_producers):
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.TOOL_MISMATCH,
                    description=(
                        f"Producer '{meta.producer}' does not match "
                        f"expected {profile.name} producer"
                    ),
                    severity=0.85,
                    target_field="producer",
                )
            )
        return results

    def _check_creator_match(
        self, meta: PdfMetadata, profile: BankProfile
    ) -> list[ForgeryIndicator]:
        results: list[ForgeryIndicator] = []
        creator_lower = meta.creator.lower()
        if meta.creator and not any(ec in creator_lower for ec in profile.expected_creators):
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.TOOL_MISMATCH,
                    description=(
                        f"Creator '{meta.creator}' does not match "
                        f"expected {profile.name} creator"
                    ),
                    severity=0.85,
                    target_field="creator",
                )
            )
        return results

    def _check_version_match(
        self, meta: PdfMetadata, profile: BankProfile
    ) -> list[ForgeryIndicator]:
        results: list[ForgeryIndicator] = []
        if meta.pdf_version and meta.pdf_version != profile.expected_pdf_version:
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.METADATA_MISMATCH,
                    description=(
                        f"PDF version '{meta.pdf_version}' does not match "
                        f"expected '{profile.expected_pdf_version}'"
                    ),
                    severity=0.9,
                    target_field="pdf_version",
                )
            )
        return results

    def _check_spec(
        self, receipt: Receipt, obj_info: PdfObjectInfo, profile: BankProfile
    ) -> list[ForgeryIndicator]:
        results: list[ForgeryIndicator] = []

        matching_spec = None
        for spec in profile.specs:
            if (
                receipt.metadata.page_width == spec.page_width
                and receipt.metadata.page_height == spec.page_height
            ):
                matching_spec = spec
                break

        if matching_spec is None:
            page_sizes = [(s.page_width, s.page_height) for s in profile.specs]
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                    description=(
                        f"Page size {receipt.metadata.page_width}x{receipt.metadata.page_height} "
                        f"does not match any known {profile.name} receipt format: {page_sizes}"
                    ),
                    severity=0.95,
                    target_field="page_dimensions",
                )
            )
            return results

        if obj_info.object_count != matching_spec.object_count:
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                    description=(
                        f"Object count {obj_info.object_count} does not match "
                        f"expected {matching_spec.object_count}"
                    ),
                    severity=0.95,
                    target_field="object_count",
                )
            )

        if obj_info.image_count != matching_spec.image_count:
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                    description=(
                        f"Image count {obj_info.image_count} does not match "
                        f"expected {matching_spec.image_count}"
                    ),
                    severity=0.95,
                    target_field="image_count",
                )
            )

        if obj_info.font_count != matching_spec.font_count:
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                    description=(
                        f"Font count {obj_info.font_count} does not match "
                        f"expected {matching_spec.font_count}"
                    ),
                    severity=0.95,
                    target_field="font_count",
                )
            )

        return results

    def _check_producer_authenticity(self, meta: PdfMetadata) -> list[ForgeryIndicator]:
        results: list[ForgeryIndicator] = []
        producer_lower = meta.producer.lower()

        for fake_producer in NON_GENUINE_PRODUCERS:
            if fake_producer in producer_lower:
                results.append(
                    ForgeryIndicator(
                        anomaly_type=AnomalyType.TOOL_MISMATCH,
                        description=(
                            f"Producer '{meta.producer}' is an HTML-to-PDF generator, "
                            f"not a legitimate bank receipt system"
                        ),
                        severity=0.95,
                        target_field="producer",
                    )
                )
                break

        for tool in SUSPICIOUS_PRODUCERS:
            if tool in producer_lower:
                results.append(
                    ForgeryIndicator(
                        anomaly_type=AnomalyType.TOOL_MISMATCH,
                        description=f"Document produced by editing tool: {tool}",
                        severity=0.8,
                        target_field="producer",
                    )
                )
                break

        return results

    def _check_metadata_dates(self, meta: PdfMetadata) -> list[ForgeryIndicator]:
        results: list[ForgeryIndicator] = []
        if meta.creation_date and meta.modification_date:
            if meta.creation_date > meta.modification_date:
                results.append(
                    ForgeryIndicator(
                        anomaly_type=AnomalyType.DATE_ANOMALY,
                        description="Creation date is after modification date",
                        severity=0.9,
                        target_field="dates",
                    )
                )
        if not meta.creator and not meta.producer:
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.METADATA_MISMATCH,
                    description="Both creator and producer metadata are empty",
                    severity=0.6,
                    target_field="metadata",
                )
            )
        return results

    def _check_keywords(self, meta: PdfMetadata) -> list[ForgeryIndicator]:
        results: list[ForgeryIndicator] = []
        if not meta.keywords:
            return results
        parts = [p.strip() for p in meta.keywords.split("|")]
        if len(parts) >= 2:
            hash_part = parts[1].strip()
            if MD5_PATTERN.match(hash_part):
                results.append(
                    ForgeryIndicator(
                        anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                        description=(
                            f"Keywords contain MD5-style hash '{hash_part}' "
                            "instead of expected UUID format"
                        ),
                        severity=0.8,
                        target_field="keywords",
                    )
                )
        return results

    def _check_fonts(self, receipt: Receipt) -> list[ForgeryIndicator]:
        results: list[ForgeryIndicator] = []
        embedded = [f for f in receipt.fonts if f.is_embedded]
        non_embedded = [f for f in receipt.fonts if not f.is_embedded]
        if embedded and non_embedded:
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.FONT_INCONSISTENCY,
                    description="Mix of embedded and non-embedded fonts",
                    severity=0.7,
                    target_field="fonts",
                )
            )
        if receipt.fonts:
            sizes = [f.size for f in receipt.fonts]
            size_range = max(sizes) - min(sizes)
            if size_range > 8.0:
                results.append(
                    ForgeryIndicator(
                        anomaly_type=AnomalyType.FONT_INCONSISTENCY,
                        description=f"Large font size variance: {size_range:.1f}pt range",
                        severity=0.4,
                        target_field="fonts",
                    )
                )
        return results

    def _check_revisions(self, revision_count: int) -> list[ForgeryIndicator]:
        results: list[ForgeryIndicator] = []
        if revision_count > 1:
            severity = min(0.8 * (revision_count - 1), 1.0)
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.REVISION_ANOMALY,
                    description=f"Multiple PDF revisions detected: {revision_count}",
                    severity=severity,
                    target_field="structure",
                )
            )
        return results

    def _check_text_layer(self, receipt: Receipt) -> list[ForgeryIndicator]:
        results: list[ForgeryIndicator] = []
        text = receipt.text_content
        if receipt.metadata.page_count > 0 and not text.strip():
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.TEXT_LAYER_ANOMALY,
                    description="PDF has pages but no extractable text",
                    severity=0.3,
                    target_field="text",
                )
            )
        return results

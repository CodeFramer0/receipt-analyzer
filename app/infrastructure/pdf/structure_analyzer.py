import re

from app.domain.entities import Receipt
from app.domain.enums import AnomalyType
from app.domain.interfaces import StructureAnalyzerPort
from app.domain.value_objects import ForgeryIndicator, PdfMetadata

UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
MD5_PATTERN = re.compile(r"^[0-9a-f]{32}$")

SUSPICIOUS_PRODUCERS = [
    "nitro",
    "pdfelement",
    "foxit phantompdf",
    "ilovepdf",
    "sejda",
    "smallpdf",
    "canva",
    "adobe photoshop",
    "gimp",
    "libreoffice",
    "openoffice",
    "microsoft word",
    "google docs",
]

SYSTEM_FONTS = [
    "arial",
    "timesnewroman",
    "times-roman",
    "calibri",
    "cambria",
    "verdana",
    "tahoma",
    "georgia",
    "comic",
    "impact",
]


EXPECTED_EMAIL = "fb@tbank.ru"
EXPECTED_FILENAME_KEYWORD = "receipt"
EXPECTED_PRODUCER = "openpdf"
EXPECTED_PAGE_HEIGHT = 410.0
PAGE_HEIGHT_TOLERANCE = 5.0
EXPECTED_OBJECT_COUNT_MAX = 27

NON_GENUINE_PRODUCERS = [
    "dompdf",
    "mpdf",
    "wkhtmltopdf",
    "tcpdf",
    "fpdf",
    "reportlab",
    "prince",
    "weasyprint",
]


class StructureAnalyzer(StructureAnalyzerPort):
    def analyze(self, receipt: Receipt, revision_count: int) -> list[ForgeryIndicator]:
        indicators: list[ForgeryIndicator] = []
        indicators.extend(self._check_receipt_identity(receipt))
        indicators.extend(self._check_metadata(receipt.metadata))
        indicators.extend(self._check_producer_authenticity(receipt.metadata))
        indicators.extend(self._check_page_dimensions(receipt.metadata))
        indicators.extend(self._check_keywords(receipt.metadata))
        indicators.extend(self._check_fonts(receipt))
        indicators.extend(self._check_revisions(revision_count))
        indicators.extend(self._check_text_layer(receipt))
        return indicators

    def _check_receipt_identity(self, receipt: Receipt) -> list[ForgeryIndicator]:
        results: list[ForgeryIndicator] = []

        if EXPECTED_FILENAME_KEYWORD not in receipt.filename.lower():
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.METADATA_MISMATCH,
                    description=(
                        f"Filename '{receipt.filename}' does not contain "
                        f"expected keyword '{EXPECTED_FILENAME_KEYWORD}'"
                    ),
                    severity=0.7,
                    target_field="filename",
                )
            )

        if EXPECTED_EMAIL not in receipt.text_content.lower():
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                    description=(
                        f"Expected email '{EXPECTED_EMAIL}' not found in receipt text"
                    ),
                    severity=0.9,
                    target_field="text_content",
                )
            )

        return results

    def _check_producer_authenticity(self, meta: PdfMetadata) -> list[ForgeryIndicator]:
        results: list[ForgeryIndicator] = []
        producer_lower = meta.producer.lower()

        if producer_lower and EXPECTED_PRODUCER not in producer_lower:
            for fake_producer in NON_GENUINE_PRODUCERS:
                if fake_producer in producer_lower:
                    results.append(
                        ForgeryIndicator(
                            anomaly_type=AnomalyType.TOOL_MISMATCH,
                            description=(
                                f"Producer '{meta.producer}' is an HTML-to-PDF generator, "
                                f"not the expected bank receipt system (OpenPDF)"
                            ),
                            severity=0.95,
                            target_field="producer",
                        )
                    )
                    break

        return results

    def _check_page_dimensions(self, meta: PdfMetadata) -> list[ForgeryIndicator]:
        return []

    def _check_metadata(self, meta: PdfMetadata) -> list[ForgeryIndicator]:
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

        producer_lower = meta.producer.lower()
        creator_lower = meta.creator.lower()

        for tool in SUSPICIOUS_PRODUCERS:
            if tool in producer_lower or tool in creator_lower:
                results.append(
                    ForgeryIndicator(
                        anomaly_type=AnomalyType.TOOL_MISMATCH,
                        description=f"Document created/produced by editing tool: {tool}",
                        severity=0.8,
                        target_field="producer",
                    )
                )
                break

        if producer_lower and creator_lower and producer_lower != creator_lower:
            is_jasper_openpdf = "jasperreports" in creator_lower and "openpdf" in producer_lower
            if not is_jasper_openpdf:
                results.append(
                    ForgeryIndicator(
                        anomaly_type=AnomalyType.METADATA_MISMATCH,
                        description=f"Creator '{meta.creator}' differs from producer '{meta.producer}'",
                        severity=0.5,
                        target_field="creator/producer",
                    )
                )

        if not meta.creator and not meta.producer:
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.METADATA_MISMATCH,
                    description="Both creator and producer metadata are empty (possibly stripped)",
                    severity=0.6,
                    target_field="metadata",
                )
            )

        if meta.modification_date and not meta.creation_date:
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.DATE_ANOMALY,
                    description="Modification date present but creation date is missing",
                    severity=0.6,
                    target_field="dates",
                )
            )

        return results

    def _check_keywords(self, meta: PdfMetadata) -> list[ForgeryIndicator]:
        results: list[ForgeryIndicator] = []

        if not meta.keywords and meta.producer:
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.METADATA_MISMATCH,
                    description="Keywords field is empty - genuine Tinkoff receipts contain receipt metadata",
                    severity=0.8,
                    target_field="keywords",
                )
            )
            return results

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

        if len(parts) >= 1:
            date_part = parts[0].strip()
            if meta.creation_date:
                meta_date_str = meta.creation_date.strftime("%d.%m.%Y")
                if meta_date_str not in date_part:
                    results.append(
                        ForgeryIndicator(
                            anomaly_type=AnomalyType.DATE_ANOMALY,
                            description=(
                                f"Keywords date '{date_part}' does not match "
                                f"creation date '{meta_date_str}'"
                            ),
                            severity=0.7,
                            target_field="keywords",
                        )
                    )

        return results

    def _check_fonts(self, receipt: Receipt) -> list[ForgeryIndicator]:
        results: list[ForgeryIndicator] = []

        unique_font_names = {f.name for f in receipt.fonts}

        if len(unique_font_names) > 3:
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.FONT_INCONSISTENCY,
                    description=f"Too many unique fonts for a receipt: {len(unique_font_names)}",
                    severity=0.6,
                    target_field="fonts",
                )
            )

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

        for font_name in unique_font_names:
            name_lower = font_name.lower().replace("-", "").replace(" ", "")
            for system_font in SYSTEM_FONTS:
                if system_font in name_lower:
                    results.append(
                        ForgeryIndicator(
                            anomaly_type=AnomalyType.FONT_INCONSISTENCY,
                            description=f"System font '{font_name}' found in receipt",
                            severity=0.5,
                            target_field="fonts",
                        )
                    )
                    break

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
                    description="PDF has pages but no extractable text (image-only)",
                    severity=0.3,
                    target_field="text",
                )
            )

        if text and "\t" in text:
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                    description="Tab characters found in receipt text",
                    severity=0.4,
                    target_field="text",
                )
            )

        if text:
            double_space_count = text.count("  ")
            if double_space_count > 10:
                results.append(
                    ForgeryIndicator(
                        anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                        description=f"Excessive double spaces: {double_space_count} occurrences",
                        severity=0.4,
                        target_field="text",
                    )
                )

        return results

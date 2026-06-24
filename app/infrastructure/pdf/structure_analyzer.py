from app.domain.entities import Receipt
from app.domain.enums import AnomalyType
from app.domain.interfaces import StructureAnalyzerPort
from app.domain.value_objects import ForgeryIndicator
from app.infrastructure.pdf.bank_profiles import detect_bank
from app.infrastructure.pdf.object_extractor import PdfObjectInfo


class StructureAnalyzer(StructureAnalyzerPort):
    def analyze(
        self, receipt: Receipt, revision_count: int, object_info: PdfObjectInfo | None = None
    ) -> list[ForgeryIndicator]:
        indicators: list[ForgeryIndicator] = []
        indicators.extend(self._check_bank_specific(receipt, object_info))
        indicators.extend(self._check_fonts(receipt))
        indicators.extend(self._check_revisions(revision_count))
        indicators.extend(self._check_text_layer(receipt))
        return indicators

    def _check_bank_specific(
        self, receipt: Receipt, object_info: PdfObjectInfo | None
    ) -> list[ForgeryIndicator]:
        results: list[ForgeryIndicator] = []
        profile = detect_bank(receipt.text_content)

        if profile is None:
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                    description="Could not identify bank from receipt text content",
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

        if profile.specs and object_info:
            results.extend(self._check_spec(receipt, object_info, profile))

        return results

    def _check_spec(
        self, receipt: Receipt, obj_info: PdfObjectInfo, profile
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

        if matching_spec.image_total_raw_bytes > 0:
            diff = abs(obj_info.image_total_raw_bytes - matching_spec.image_total_raw_bytes)
            tolerance = matching_spec.image_total_raw_bytes * 0.05
            if diff > tolerance:
                results.append(
                    ForgeryIndicator(
                        anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                        description=(
                            f"Image raw bytes {obj_info.image_total_raw_bytes} "
                            f"differ from expected {matching_spec.image_total_raw_bytes} "
                            f"(delta {diff})"
                        ),
                        severity=0.9,
                        target_field="image_raw_bytes",
                    )
                )

        if matching_spec.font_raw_bytes_min > 0:
            if not (
                matching_spec.font_raw_bytes_min
                <= obj_info.font_total_raw_bytes
                <= matching_spec.font_raw_bytes_max
            ):
                results.append(
                    ForgeryIndicator(
                        anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                        description=(
                            f"Font raw bytes {obj_info.font_total_raw_bytes} "
                            f"outside expected range "
                            f"[{matching_spec.font_raw_bytes_min}, {matching_spec.font_raw_bytes_max}]"
                        ),
                        severity=0.9,
                        target_field="font_raw_bytes",
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

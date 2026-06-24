from app.domain.enums import AnomalyType
from app.domain.value_objects import AnomalyScore, ForgeryIndicator

WEIGHTS: dict[AnomalyType, float] = {
    AnomalyType.METADATA_MISMATCH: 2.0,
    AnomalyType.FONT_INCONSISTENCY: 1.5,
    AnomalyType.TOOL_MISMATCH: 2.5,
    AnomalyType.REVISION_ANOMALY: 3.0,
    AnomalyType.TEXT_LAYER_ANOMALY: 1.0,
    AnomalyType.DATE_ANOMALY: 2.0,
    AnomalyType.STRUCTURE_ANOMALY: 1.5,
    AnomalyType.JAVASCRIPT_DETECTED: 5.0,
    AnomalyType.CONTENT_STREAM_ANOMALY: 2.5,
    AnomalyType.STREAM_ANOMALY: 1.5,
}

CRITICAL_FIELDS = {"image_bytes": 3.0}


class ForgeryScorer:
    def score(
        self, filename: str, indicators: list[ForgeryIndicator]
    ) -> AnomalyScore:
        total = 0.0
        for ind in indicators:
            weight = CRITICAL_FIELDS.get(ind.target_field, WEIGHTS.get(ind.anomaly_type, 1.0))
            total += ind.severity * weight
        return AnomalyScore(
            receipt_filename=filename,
            total_score=round(total, 2),
            indicators=tuple(indicators),
        )

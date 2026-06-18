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
}


class ForgeryScorer:
    def score(
        self, filename: str, indicators: list[ForgeryIndicator]
    ) -> AnomalyScore:
        total = sum(
            ind.severity * WEIGHTS.get(ind.anomaly_type, 1.0)
            for ind in indicators
        )
        return AnomalyScore(
            receipt_filename=filename,
            total_score=round(total, 2),
            indicators=tuple(indicators),
        )

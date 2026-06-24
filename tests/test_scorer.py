from app.domain.enums import AnomalyType
from app.domain.value_objects import ForgeryIndicator
from app.infrastructure.analysis.scorer import ForgeryScorer


def test_empty_indicators_zero_score():
    scorer = ForgeryScorer()
    result = scorer.score("test.pdf", [])
    assert result.total_score == 0
    assert result.receipt_filename == "test.pdf"
    assert len(result.indicators) == 0


def test_single_indicator_weighted():
    scorer = ForgeryScorer()
    indicators = [
        ForgeryIndicator(
            anomaly_type=AnomalyType.TOOL_MISMATCH,
            description="test",
            severity=0.8,
        )
    ]
    result = scorer.score("test.pdf", indicators)
    assert result.total_score == 2.0


def test_multiple_indicators_sum():
    scorer = ForgeryScorer()
    indicators = [
        ForgeryIndicator(
            anomaly_type=AnomalyType.TOOL_MISMATCH,
            description="test1",
            severity=1.0,
        ),
        ForgeryIndicator(
            anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
            description="test2",
            severity=1.0,
        ),
    ]
    result = scorer.score("test.pdf", indicators)
    assert result.total_score == 4.0

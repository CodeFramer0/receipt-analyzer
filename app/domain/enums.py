from enum import StrEnum


class AnalysisStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ReceiptVerdict(StrEnum):
    ORIGINAL = "original"
    FAKE = "fake"
    SUSPICIOUS = "suspicious"
    UNKNOWN = "unknown"


class AnomalyType(StrEnum):
    METADATA_MISMATCH = "metadata_mismatch"
    FONT_INCONSISTENCY = "font_inconsistency"
    TOOL_MISMATCH = "tool_mismatch"
    REVISION_ANOMALY = "revision_anomaly"
    TEXT_LAYER_ANOMALY = "text_layer_anomaly"
    DATE_ANOMALY = "date_anomaly"
    STRUCTURE_ANOMALY = "structure_anomaly"
    JAVASCRIPT_DETECTED = "javascript_detected"
    CONTENT_STREAM_ANOMALY = "content_stream_anomaly"
    STREAM_ANOMALY = "stream_anomaly"

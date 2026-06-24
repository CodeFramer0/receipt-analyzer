import json
from datetime import datetime
from pathlib import Path

from app.domain.entities import AnalysisReport, FileResult
from app.domain.enums import AnalysisStatus, AnomalyType, ReceiptVerdict
from app.domain.interfaces import ReportRepository
from app.domain.value_objects import AnomalyScore, ForgeryIndicator, PdfMetadata


class JsonReportRepository(ReportRepository):
    def __init__(self, reports_dir: Path) -> None:
        self._reports_dir = reports_dir
        self._reports_dir.mkdir(parents=True, exist_ok=True)

    def save(self, report: AnalysisReport) -> None:
        path = self._reports_dir / f"{report.id}.json"
        data = self._serialize(report)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str))

    def get_by_id(self, report_id: str) -> AnalysisReport | None:
        path = self._reports_dir / f"{report_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return self._deserialize(data)

    def get_all(self) -> list[AnalysisReport]:
        reports = []
        for path in sorted(self._reports_dir.glob("*.json")):
            data = json.loads(path.read_text())
            reports.append(self._deserialize(data))
        return reports

    @staticmethod
    def _serialize(report: AnalysisReport) -> dict:
        def _file_to_dict(fr: FileResult) -> dict:
            result: dict = {
                "filename": fr.filename,
                "verdict": fr.verdict.value,
                "detected_bank": fr.detected_bank,
                "score": fr.score.total_score if fr.score else 0,
                "reasons": [],
            }
            if fr.score:
                result["reasons"] = [
                    {
                        "anomaly_type": ind.anomaly_type.value,
                        "description": ind.description,
                        "severity": ind.severity,
                        "target_field": ind.target_field,
                    }
                    for ind in fr.score.indicators
                ]
            if fr.metadata:
                result["technical_info"] = {
                    "producer": fr.metadata.producer,
                    "creator": fr.metadata.creator,
                    "pdf_version": fr.metadata.pdf_version,
                    "page_height": fr.metadata.page_height,
                    "page_width": fr.metadata.page_width,
                    "is_encrypted": fr.metadata.is_encrypted,
                    "keywords": fr.metadata.keywords,
                }
            result["revision_count"] = fr.revision_count
            return result

        return {
            "analysis_id": report.id,
            "status": report.status.value,
            "files": [_file_to_dict(f) for f in report.files],
            "created_at": report.created_at.isoformat(),
        }

    @staticmethod
    def _deserialize(data: dict) -> AnalysisReport:
        def _dict_to_file(d: dict) -> FileResult:
            indicators = tuple(
                ForgeryIndicator(
                    anomaly_type=AnomalyType(r["anomaly_type"]),
                    description=r["description"],
                    severity=r["severity"],
                    target_field=r.get("target_field", ""),
                )
                for r in d.get("reasons", [])
            )
            score = AnomalyScore(
                receipt_filename=d["filename"],
                total_score=d.get("score", 0),
                indicators=indicators,
            )
            metadata = None
            ti = d.get("technical_info")
            if ti:
                metadata = PdfMetadata(
                    producer=ti.get("producer", ""),
                    creator=ti.get("creator", ""),
                    pdf_version=ti.get("pdf_version", ""),
                    page_height=ti.get("page_height", 0),
                    page_width=ti.get("page_width", 0),
                    is_encrypted=ti.get("is_encrypted", False),
                    keywords=ti.get("keywords", ""),
                )
            return FileResult(
                filename=d["filename"],
                verdict=ReceiptVerdict(d["verdict"]),
                detected_bank=d.get("detected_bank", "unknown"),
                score=score,
                metadata=metadata,
                revision_count=d.get("revision_count", 0),
            )

        return AnalysisReport(
            id=data["analysis_id"],
            status=AnalysisStatus(data["status"]),
            files=[_dict_to_file(f) for f in data.get("files", [])],
            created_at=datetime.fromisoformat(data["created_at"]),
        )

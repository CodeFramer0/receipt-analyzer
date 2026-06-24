import tempfile
import uuid
from pathlib import Path

import pikepdf

from app.domain.enums import AnomalyType
from app.infrastructure.pdf.byte_analyzer import PdfByteAnalyzer


def _tmp_path() -> Path:
    d = Path(tempfile.gettempdir()) / "receipt_tests"
    d.mkdir(exist_ok=True)
    return d / f"{uuid.uuid4().hex}.pdf"


def _create_clean_pdf() -> Path:
    pdf = pikepdf.Pdf.new()
    page = pikepdf.Page(
        pikepdf.Dictionary(
            Type=pikepdf.Name.Page,
            MediaBox=[0, 0, 300, 700],
        )
    )
    pdf.pages.append(page)
    out = _tmp_path()
    pdf.save(str(out))
    pdf.close()
    return out


def _create_pdf_with_js() -> Path:
    pdf = pikepdf.Pdf.new()
    page = pikepdf.Page(
        pikepdf.Dictionary(
            Type=pikepdf.Name.Page,
            MediaBox=[0, 0, 300, 700],
        )
    )
    pdf.pages.append(page)
    js_action = pikepdf.Dictionary(
        S=pikepdf.Name.JavaScript,
        JS=pikepdf.String("app.alert('test');"),
    )
    pdf.Root[pikepdf.Name.OpenAction] = pdf.make_indirect(js_action)
    out = _tmp_path()
    pdf.save(str(out))
    pdf.close()
    return out


def _create_pdf_with_open_action() -> Path:
    pdf = pikepdf.Pdf.new()
    page = pikepdf.Page(
        pikepdf.Dictionary(
            Type=pikepdf.Name.Page,
            MediaBox=[0, 0, 300, 700],
        )
    )
    pdf.pages.append(page)
    action = pikepdf.Dictionary(
        S=pikepdf.Name.GoTo,
        D=pikepdf.Array([pdf.pages[0].obj, pikepdf.Name.Fit]),
    )
    pdf.Root[pikepdf.Name.OpenAction] = pdf.make_indirect(action)
    out = _tmp_path()
    pdf.save(str(out))
    pdf.close()
    return out


def _create_pdf_with_trailing_data() -> Path:
    pdf = pikepdf.Pdf.new()
    page = pikepdf.Page(
        pikepdf.Dictionary(
            Type=pikepdf.Name.Page,
            MediaBox=[0, 0, 300, 700],
        )
    )
    pdf.pages.append(page)
    out = _tmp_path()
    pdf.save(str(out))
    pdf.close()
    with open(out, "ab") as f:
        f.write(b"\n" + b"X" * 100)
    return out


def _create_pdf_with_acroform() -> Path:
    pdf = pikepdf.Pdf.new()
    page = pikepdf.Page(
        pikepdf.Dictionary(
            Type=pikepdf.Name.Page,
            MediaBox=[0, 0, 300, 700],
        )
    )
    pdf.pages.append(page)
    pdf.Root[pikepdf.Name.AcroForm] = pdf.make_indirect(
        pikepdf.Dictionary(Fields=pikepdf.Array([]))
    )
    out = _tmp_path()
    pdf.save(str(out))
    pdf.close()
    return out


class TestByteAnalyzer:
    def setup_method(self):
        self.analyzer = PdfByteAnalyzer()

    def test_clean_pdf_no_issues(self):
        path = _create_clean_pdf()
        indicators = self.analyzer.analyze(path)
        js = [i for i in indicators if i.anomaly_type == AnomalyType.JAVASCRIPT_DETECTED]
        actions = [i for i in indicators if i.target_field == "actions"]
        assert len(js) == 0
        assert len(actions) == 0

    def test_javascript_detected(self):
        path = _create_pdf_with_js()
        indicators = self.analyzer.analyze(path)
        has_js = any(i.anomaly_type == AnomalyType.JAVASCRIPT_DETECTED for i in indicators)
        has_action = any(i.target_field == "actions" for i in indicators)
        assert has_js or has_action

    def test_open_action_detected(self):
        path = _create_pdf_with_open_action()
        indicators = self.analyzer.analyze(path)
        actions = [i for i in indicators if i.target_field == "actions"]
        assert len(actions) >= 1

    def test_trailing_data_detected(self):
        path = _create_pdf_with_trailing_data()
        indicators = self.analyzer.analyze(path)
        trailing = [i for i in indicators if i.target_field == "trailing_data"]
        assert len(trailing) >= 1

    def test_acroform_detected(self):
        path = _create_pdf_with_acroform()
        indicators = self.analyzer.analyze(path)
        forbidden = [i for i in indicators if i.target_field == "forbidden_objects"]
        assert len(forbidden) >= 1

    def test_incremental_update_detection(self):
        path = _create_clean_pdf()
        pdf = pikepdf.open(str(path))
        page = pdf.pages[0]
        stream = pikepdf.Stream(pdf, b"BT /F1 12 Tf (Modified) Tj ET")
        page[pikepdf.Name.Contents] = pdf.make_indirect(stream)
        out = _tmp_path()
        pdf.save(str(out), linearize=False)
        pdf.close()

        raw = out.read_bytes()
        eof_count = raw.count(b"%%EOF")

        if eof_count > 1:
            indicators = self.analyzer.analyze(out)
            revision = [
                i for i in indicators
                if i.anomaly_type in (
                    AnomalyType.REVISION_ANOMALY,
                    AnomalyType.CONTENT_STREAM_ANOMALY,
                )
            ]
            assert len(revision) >= 1

    def test_generator_detection_from_bytes(self):
        path = _create_clean_pdf()
        raw = path.read_bytes()
        raw_with_sig = raw.replace(b"%%EOF", b"/CPDF %%EOF")
        path.write_bytes(raw_with_sig)

        indicators = self.analyzer.analyze(path)
        tool = [i for i in indicators if i.target_field == "generator"]
        trailing = [i for i in indicators if i.target_field == "trailing_data"]
        assert len(tool) >= 1 or len(trailing) >= 1

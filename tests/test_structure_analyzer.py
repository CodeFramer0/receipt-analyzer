import pytest

from app.domain.entities import Receipt
from app.domain.enums import AnomalyType
from app.domain.value_objects import FontInfo, PdfMetadata
from app.infrastructure.pdf.object_extractor import PdfObjectInfo
from app.infrastructure.pdf.structure_analyzer import StructureAnalyzer


@pytest.fixture
def analyzer():
    return StructureAnalyzer()


def _tinkoff_receipt(
    filename="receipt_test.pdf",
    text="Служба поддержки fb@tbank.ru",
    producer="OpenPDF 1.3.30.jaspersoft.2",
    creator="JasperReports Library version 6.20.3",
    fonts=None,
):
    return Receipt(
        filename=filename,
        text_content=text,
        metadata=PdfMetadata(
            creator=creator, producer=producer,
            page_count=1, page_height=410.0,
        ),
        fonts=fonts or [
            FontInfo(name="ABCDEF+TinkoffSans-Regular", size=9.0, is_embedded=True, page_number=1),
        ],
    )


def _sber_receipt(
    filename="receipt_sber.pdf",
    text="Чек по операции\nПеревод клиенту СберБанка\nФИО получателя",
    producer="iText 2.1.7 by 1T3XT",
    creator="JasperReports Library version 6.18.1",
    fonts=None,
):
    return Receipt(
        filename=filename,
        text_content=text,
        metadata=PdfMetadata(
            creator=creator, producer=producer,
            page_count=1, page_height=699.0,
        ),
        fonts=fonts or [
            FontInfo(name="OWAWLX+ArialMT", size=10.0, is_embedded=True, page_number=1),
        ],
    )


class TestTinkoffBankSpecific:
    def test_valid_tinkoff_passes(self, analyzer):
        receipt = _tinkoff_receipt()
        indicators = analyzer.analyze(receipt, 1)
        bank = [i for i in indicators if i.target_field == "text_content"]
        assert len(bank) == 0

    def test_missing_email_detected(self, analyzer):
        receipt = _tinkoff_receipt(text="Операция через Тинькофф без правильного email")
        indicators = analyzer.analyze(receipt, 1)
        emails = [i for i in indicators if i.target_field == "text_content"]
        assert len(emails) == 1


class TestSberBankSpecific:
    def test_valid_sber_passes(self, analyzer):
        receipt = _sber_receipt()
        indicators = analyzer.analyze(receipt, 1)
        bank_issues = [
            i for i in indicators
            if i.target_field == "text_content"
        ]
        assert len(bank_issues) == 0

    def test_sber_no_email_check(self, analyzer):
        receipt = _sber_receipt()
        indicators = analyzer.analyze(receipt, 1)
        emails = [i for i in indicators if "email" in i.description.lower()]
        assert len(emails) == 0


class TestSberSpec:
    def test_image_raw_bytes_mismatch(self, analyzer):
        receipt = Receipt(
            filename="receipt_sber.pdf",
            text_content="Перевод клиенту СберБанка",
            metadata=PdfMetadata(
                creator="", producer="",
                page_count=1,
                page_width=300.0, page_height=699.0,
            ),
            fonts=[FontInfo(name="OWAWLX+ArialMT", size=10.0, is_embedded=True, page_number=1)],
        )
        obj_info = PdfObjectInfo(
            object_count=16, image_count=3,
            image_total_raw_bytes=999,
            image_object_ids=(), font_count=1,
            font_total_raw_bytes=24500,
            font_object_ids=(),
        )
        indicators = analyzer.analyze(receipt, 1, obj_info)
        img_bytes = [i for i in indicators if i.target_field == "image_raw_bytes"]
        assert len(img_bytes) >= 1

    def test_font_raw_bytes_outside_range(self, analyzer):
        receipt = Receipt(
            filename="receipt_sber.pdf",
            text_content="Перевод клиенту СберБанка",
            metadata=PdfMetadata(
                creator="", producer="",
                page_count=1,
                page_width=300.0, page_height=699.0,
            ),
            fonts=[FontInfo(name="OWAWLX+ArialMT", size=10.0, is_embedded=True, page_number=1)],
        )
        obj_info = PdfObjectInfo(
            object_count=16, image_count=3,
            image_total_raw_bytes=15247,
            image_object_ids=(), font_count=1,
            font_total_raw_bytes=10000,
            font_object_ids=(),
        )
        indicators = analyzer.analyze(receipt, 1, obj_info)
        font_bytes = [i for i in indicators if i.target_field == "font_raw_bytes"]
        assert len(font_bytes) >= 1

    def test_all_spec_fields_pass(self, analyzer):
        receipt = Receipt(
            filename="receipt_sber.pdf",
            text_content="Перевод клиенту СберБанка",
            metadata=PdfMetadata(
                creator="", producer="",
                page_count=1,
                page_width=300.0, page_height=699.0,
            ),
            fonts=[FontInfo(name="OWAWLX+ArialMT", size=10.0, is_embedded=True, page_number=1)],
        )
        obj_info = PdfObjectInfo(
            object_count=16, image_count=3,
            image_total_raw_bytes=15247,
            image_object_ids=(), font_count=1,
            font_total_raw_bytes=24500,
            font_object_ids=(),
        )
        indicators = analyzer.analyze(receipt, 1, obj_info)
        spec_fields = {"image_raw_bytes", "font_raw_bytes",
                       "object_count", "image_count", "font_count"}
        spec_issues = [i for i in indicators if i.target_field in spec_fields]
        assert len(spec_issues) == 0

    def test_page_size_mismatch(self, analyzer):
        receipt = Receipt(
            filename="receipt_sber.pdf",
            text_content="Перевод клиенту СберБанка",
            metadata=PdfMetadata(
                creator="", producer="",
                page_count=1,
                page_width=400.0, page_height=600.0,
            ),
            fonts=[FontInfo(name="OWAWLX+ArialMT", size=10.0, is_embedded=True, page_number=1)],
        )
        obj_info = PdfObjectInfo(
            object_count=16, image_count=3,
            image_total_raw_bytes=15247,
            image_object_ids=(), font_count=1,
            font_total_raw_bytes=24500,
            font_object_ids=(),
        )
        indicators = analyzer.analyze(receipt, 1, obj_info)
        dims = [i for i in indicators if i.target_field == "page_dimensions"]
        assert len(dims) >= 1


class TestRevisions:
    def test_single_revision_passes(self, analyzer):
        receipt = _tinkoff_receipt()
        indicators = analyzer.analyze(receipt, 1)
        revs = [i for i in indicators if i.anomaly_type == AnomalyType.REVISION_ANOMALY]
        assert len(revs) == 0

    def test_multiple_revisions_detected(self, analyzer):
        receipt = _tinkoff_receipt()
        indicators = analyzer.analyze(receipt, 3)
        revs = [i for i in indicators if i.anomaly_type == AnomalyType.REVISION_ANOMALY]
        assert len(revs) == 1


class TestFonts:
    def test_mixed_embedding_detected(self, analyzer):
        receipt = _tinkoff_receipt(fonts=[
            FontInfo(name="ABCDEF+TinkoffSans", size=9.0, is_embedded=True, page_number=1),
            FontInfo(name="Arial", size=9.0, is_embedded=False, page_number=1),
        ])
        indicators = analyzer.analyze(receipt, 1)
        mixed = [i for i in indicators if "embedded" in i.description.lower()]
        assert len(mixed) >= 1

    def test_large_font_variance_detected(self, analyzer):
        receipt = _tinkoff_receipt(fonts=[
            FontInfo(name="ABCDEF+Font", size=6.0, is_embedded=True, page_number=1),
            FontInfo(name="ABCDEF+Font", size=20.0, is_embedded=True, page_number=1),
        ])
        indicators = analyzer.analyze(receipt, 1)
        variance = [i for i in indicators if "variance" in i.description.lower()]
        assert len(variance) >= 1


class TestTextLayer:
    def test_empty_text_detected(self, analyzer):
        receipt = Receipt(
            filename="receipt_test.pdf",
            text_content="   ",
            metadata=PdfMetadata(page_count=1),
            fonts=[],
        )
        indicators = analyzer.analyze(receipt, 1)
        text = [i for i in indicators if i.anomaly_type == AnomalyType.TEXT_LAYER_ANOMALY]
        assert len(text) >= 1

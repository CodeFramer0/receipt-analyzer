import pytest

from app.domain.entities import Receipt
from app.domain.enums import AnomalyType
from app.domain.value_objects import FontInfo, PdfMetadata
from app.infrastructure.pdf.structure_analyzer import StructureAnalyzer


@pytest.fixture
def analyzer():
    return StructureAnalyzer()


def _tinkoff_receipt(
    filename="receipt_test.pdf",
    text="Служба поддержки fb@tbank.ru",
    producer="OpenPDF 1.3.30.jaspersoft.2",
    creator="JasperReports Library version 6.20.3",
    keywords="01.01.2026 12:00:00 | a1b2c3d4-e5f6-7890-abcd-ef1234567890 | 123",
    fonts=None,
):
    return Receipt(
        filename=filename,
        text_content=text,
        metadata=PdfMetadata(
            creator=creator, producer=producer,
            keywords=keywords, page_count=1, page_height=410.0,
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
            keywords="", page_count=1, page_height=699.0,
        ),
        fonts=fonts or [
            FontInfo(name="OWAWLX+ArialMT", size=10.0, is_embedded=True, page_number=1),
        ],
    )


class TestFilename:
    def test_valid_filename_passes(self, analyzer):
        receipt = _tinkoff_receipt(filename="receipt_test.pdf")
        indicators = analyzer.analyze(receipt, 1)
        filenames = [i for i in indicators if i.target_field == "filename"]
        assert len(filenames) == 0

    def test_invalid_filename_detected(self, analyzer):
        receipt = _tinkoff_receipt(filename="document.pdf")
        indicators = analyzer.analyze(receipt, 1)
        filenames = [i for i in indicators if i.target_field == "filename"]
        assert len(filenames) == 1


class TestTinkoffBankSpecific:
    def test_valid_tinkoff_passes(self, analyzer):
        receipt = _tinkoff_receipt()
        indicators = analyzer.analyze(receipt, 1)
        bank = [i for i in indicators if i.target_field in ("text_content", "producer", "keywords")]
        assert len(bank) == 0

    def test_missing_email_detected(self, analyzer):
        receipt = _tinkoff_receipt(text="Some random text without email")
        indicators = analyzer.analyze(receipt, 1)
        emails = [i for i in indicators if i.target_field == "text_content"]
        assert len(emails) == 1

    def test_wrong_producer_detected(self, analyzer):
        receipt = _tinkoff_receipt(producer="dompdf 2.0.7 + CPDF", text="fb@tbank.ru")
        indicators = analyzer.analyze(receipt, 1)
        tools = [i for i in indicators if i.anomaly_type == AnomalyType.TOOL_MISMATCH]
        assert len(tools) >= 1

    def test_missing_keywords_detected(self, analyzer):
        receipt = _tinkoff_receipt(keywords="")
        indicators = analyzer.analyze(receipt, 1)
        kw = [i for i in indicators if "Keywords" in i.description]
        assert len(kw) >= 1

    def test_md5_keywords_detected(self, analyzer):
        receipt = _tinkoff_receipt(
            keywords="01.01.2026 12:00:00 | bdf4585b970e0764046d4398e00c49dd | 991"
        )
        indicators = analyzer.analyze(receipt, 1)
        kw = [i for i in indicators if i.target_field == "keywords"]
        assert len(kw) >= 1


class TestSberBankSpecific:
    def test_valid_sber_passes(self, analyzer):
        receipt = _sber_receipt()
        indicators = analyzer.analyze(receipt, 1)
        bank_issues = [
            i for i in indicators
            if i.target_field in ("text_content", "keywords")
        ]
        assert len(bank_issues) == 0

    def test_sber_no_email_check(self, analyzer):
        receipt = _sber_receipt()
        indicators = analyzer.analyze(receipt, 1)
        emails = [i for i in indicators if "email" in i.description.lower()]
        assert len(emails) == 0

    def test_sber_wrong_producer_detected(self, analyzer):
        receipt = _sber_receipt(producer="dompdf 2.0.7")
        indicators = analyzer.analyze(receipt, 1)
        tools = [i for i in indicators if i.anomaly_type == AnomalyType.TOOL_MISMATCH]
        assert len(tools) >= 1


class TestProducerAuthenticity:
    def test_dompdf_detected(self, analyzer):
        receipt = _tinkoff_receipt(producer="dompdf 2.0.7 + CPDF")
        indicators = analyzer.analyze(receipt, 1)
        tools = [i for i in indicators if "HTML-to-PDF" in i.description]
        assert len(tools) >= 1

    def test_mpdf_detected(self, analyzer):
        receipt = _tinkoff_receipt(producer="mPDF 8.1.2")
        indicators = analyzer.analyze(receipt, 1)
        tools = [i for i in indicators if "HTML-to-PDF" in i.description]
        assert len(tools) >= 1


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

from app.infrastructure.pdf.bank_profiles import SBER, TINKOFF, detect_bank


class TestBankDetection:
    def test_detect_tinkoff_by_email(self):
        profile = detect_bank("Служба поддержки fb@tbank.ru", "")
        assert profile == TINKOFF

    def test_detect_tinkoff_by_producer(self):
        profile = detect_bank("some text", "OpenPDF 1.3.30.jaspersoft.2")
        assert profile == TINKOFF

    def test_detect_sber_by_text(self):
        profile = detect_bank("Перевод клиенту СберБанка", "")
        assert profile == SBER

    def test_detect_sber_by_producer(self):
        profile = detect_bank("some text", "iText 2.1.7 by 1T3XT")
        assert profile == SBER

    def test_unknown_bank(self):
        profile = detect_bank("random text", "random producer")
        assert profile is None

    def test_tinkoff_has_expected_email(self):
        assert TINKOFF.expected_email == "fb@tbank.ru"

    def test_sber_has_no_expected_email(self):
        assert SBER.expected_email == ""

    def test_sber_has_no_keywords(self):
        assert SBER.has_keywords is False

    def test_tinkoff_has_keywords(self):
        assert TINKOFF.has_keywords is True

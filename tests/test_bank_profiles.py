from app.infrastructure.pdf.bank_profiles import SBER, TINKOFF, detect_bank


class TestBankDetection:
    def test_detect_tinkoff_by_email(self):
        profile = detect_bank("Служба поддержки fb@tbank.ru")
        assert profile == TINKOFF

    def test_detect_tinkoff_by_name(self):
        profile = detect_bank("Операция через Тинькофф")
        assert profile == TINKOFF

    def test_detect_sber_by_text(self):
        profile = detect_bank("Перевод клиенту СберБанка")
        assert profile == SBER

    def test_unknown_bank(self):
        profile = detect_bank("random text without bank markers")
        assert profile is None

    def test_tinkoff_has_expected_email(self):
        assert TINKOFF.expected_email == "fb@tbank.ru"

    def test_sber_has_no_expected_email(self):
        assert SBER.expected_email == ""

    def test_sber_has_specs(self):
        assert len(SBER.specs) == 2

    def test_tinkoff_has_no_specs(self):
        assert len(TINKOFF.specs) == 0

from dataclasses import dataclass


@dataclass(frozen=True)
class ReceiptSpec:
    page_width: float
    page_height: float
    object_count: int
    image_count: int
    image_total_raw_bytes: int
    font_count: int
    font_raw_bytes_min: int
    font_raw_bytes_max: int


@dataclass(frozen=True)
class BankProfile:
    name: str
    text_markers: tuple[str, ...]
    expected_email: str = ""
    specs: tuple["ReceiptSpec", ...] = ()


SBER_WITHIN_BANK_SPEC = ReceiptSpec(
    page_width=300.0,
    page_height=699.0,
    object_count=16,
    image_count=3,
    image_total_raw_bytes=15247,
    font_count=1,
    font_raw_bytes_min=24100,
    font_raw_bytes_max=25400,
)

SBER_CROSS_BANK_SPEC = ReceiptSpec(
    page_width=300.0,
    page_height=795.0,
    object_count=17,
    image_count=4,
    image_total_raw_bytes=75178,
    font_count=1,
    font_raw_bytes_min=22400,
    font_raw_bytes_max=23400,
)

TINKOFF = BankProfile(
    name="tinkoff",
    text_markers=("fb@tbank.ru", "tinkoff", "тинькофф"),
    expected_email="fb@tbank.ru",
)

SBER = BankProfile(
    name="sber",
    text_markers=("сбербанк", "сбербанка", "сберонлайн", "sberbank"),
    specs=(SBER_WITHIN_BANK_SPEC, SBER_CROSS_BANK_SPEC),
)

ALL_PROFILES = [TINKOFF, SBER]


def detect_bank(text: str) -> BankProfile | None:
    text_lower = text.lower()
    for profile in ALL_PROFILES:
        for marker in profile.text_markers:
            if marker in text_lower:
                return profile
    return None

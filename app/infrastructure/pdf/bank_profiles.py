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
    file_size_min: int
    file_size_max: int


@dataclass(frozen=True)
class BankProfile:
    name: str
    text_markers: tuple[str, ...]
    expected_producers: tuple[str, ...]
    expected_creators: tuple[str, ...]
    expected_pdf_version: str
    expected_email: str = ""
    has_keywords: bool = True
    specs: tuple[ReceiptSpec, ...] = ()


SBER_WITHIN_BANK_SPEC = ReceiptSpec(
    page_width=300.0,
    page_height=699.0,
    object_count=16,
    image_count=3,
    image_total_raw_bytes=15247,
    font_count=1,
    font_raw_bytes_min=24100,
    font_raw_bytes_max=25400,
    file_size_min=43600,
    file_size_max=45000,
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
    file_size_min=101800,
    file_size_max=102850,
)

TINKOFF = BankProfile(
    name="tinkoff",
    text_markers=("fb@tbank.ru", "tinkoff", "тинькофф"),
    expected_producers=("openpdf",),
    expected_creators=("jasperreports library version 6.20",),
    expected_pdf_version="1.5",
    expected_email="fb@tbank.ru",
    has_keywords=True,
)

SBER = BankProfile(
    name="sber",
    text_markers=("сбербанк", "сбербанка", "сберонлайн", "sberbank"),
    expected_producers=("itext 2.1.7",),
    expected_creators=("jasperreports library version 6.18",),
    expected_pdf_version="1.5",
    expected_email="",
    has_keywords=False,
    specs=(SBER_WITHIN_BANK_SPEC, SBER_CROSS_BANK_SPEC),
)

ALL_PROFILES = [TINKOFF, SBER]


def detect_bank(text: str, producer: str) -> BankProfile | None:
    text_lower = text.lower()
    producer_lower = producer.lower()

    for profile in ALL_PROFILES:
        for marker in profile.text_markers:
            if marker in text_lower:
                return profile

    for profile in ALL_PROFILES:
        for expected in profile.expected_producers:
            if expected in producer_lower:
                return profile

    return None

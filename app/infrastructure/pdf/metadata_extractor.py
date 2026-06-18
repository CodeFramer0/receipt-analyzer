import re
from datetime import datetime, timezone
from pathlib import Path

import pikepdf

from app.domain.interfaces import PdfMetadataExtractor
from app.domain.value_objects import PdfMetadata


def _parse_pdf_date(raw: str) -> datetime | None:
    if not raw:
        return None
    cleaned = raw.replace("D:", "").replace("'", "")
    patterns = [
        "%Y%m%d%H%M%S%z",
        "%Y%m%d%H%M%S",
        "%Y%m%d%H%M",
        "%Y%m%d",
    ]
    for pattern in patterns:
        try:
            return datetime.strptime(cleaned[:len(pattern.replace("%", ""))], pattern).replace(
                tzinfo=timezone.utc
            )
        except (ValueError, IndexError):
            continue
    return None


class PikePdfMetadataExtractor(PdfMetadataExtractor):
    def extract_metadata(self, file_path: Path) -> PdfMetadata:
        with pikepdf.open(file_path) as pdf:
            info = pdf.docinfo if pdf.docinfo else {}

            creator = str(info.get("/Creator", ""))
            producer = str(info.get("/Producer", ""))
            creation_date = _parse_pdf_date(str(info.get("/CreationDate", "")))
            modification_date = _parse_pdf_date(str(info.get("/ModDate", "")))

            has_xmp = False
            try:
                has_xmp = pdf.Root.get("/Metadata") is not None
            except (AttributeError, KeyError):
                pass

            keywords = str(info.get("/Keywords", ""))

            page_width = 0.0
            page_height = 0.0
            if pdf.pages:
                mbox = pdf.pages[0].MediaBox
                page_width = float(mbox[2]) - float(mbox[0])
                page_height = float(mbox[3]) - float(mbox[1])

            return PdfMetadata(
                creator=creator,
                producer=producer,
                creation_date=creation_date,
                modification_date=modification_date,
                page_count=len(pdf.pages),
                pdf_version=pdf.pdf_version,
                is_encrypted=pdf.is_encrypted,
                has_xmp=has_xmp,
                keywords=keywords,
                page_width=page_width,
                page_height=page_height,
                file_size=file_path.stat().st_size,
            )

    def count_revisions(self, file_path: Path) -> int:
        raw = file_path.read_bytes()
        return len(re.findall(rb"%%EOF", raw))

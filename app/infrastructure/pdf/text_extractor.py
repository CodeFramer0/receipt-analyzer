from pathlib import Path

import pdfplumber

from app.domain.entities import Receipt
from app.domain.interfaces import PdfTextExtractor
from app.domain.value_objects import FontInfo, PdfMetadata


class PdfPlumberTextExtractor(PdfTextExtractor):
    def extract(self, file_path: Path) -> Receipt:
        pages_text: list[str] = []
        fonts: list[FontInfo] = []

        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                pages_text.append(text)

                seen_fonts: set[tuple[str, float]] = set()
                for char in page.chars:
                    font_key = (char["fontname"], round(char["size"], 1))
                    if font_key not in seen_fonts:
                        seen_fonts.add(font_key)
                        fonts.append(
                            FontInfo(
                                name=char["fontname"],
                                size=round(char["size"], 1),
                                is_embedded="+" in char["fontname"],
                                page_number=page_num,
                            )
                        )

        return Receipt(
            filename=file_path.name,
            text_content="\n".join(pages_text),
            metadata=PdfMetadata(page_count=len(pages_text)),
            fonts=fonts,
        )

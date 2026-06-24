from dataclasses import dataclass
from pathlib import Path

import pikepdf


@dataclass(frozen=True)
class PdfObjectInfo:
    object_count: int
    image_count: int
    image_total_raw_bytes: int
    image_object_ids: tuple[int, ...]
    font_count: int
    font_total_raw_bytes: int
    font_object_ids: tuple[int, ...]


def extract_object_info(file_path: Path) -> PdfObjectInfo:
    with pikepdf.open(file_path) as pdf:
        page = pdf.pages[0]
        resources = page.get("/Resources", {})

        xobjects = resources.get("/XObject", {})
        image_count = 0
        image_raw_bytes = 0
        image_obj_ids: list[int] = []
        for _, xobj in xobjects.items():
            if str(xobj.get("/Subtype", "")) == "/Image":
                image_count += 1
                image_raw_bytes += len(xobj.read_raw_bytes())
                image_obj_ids.append(xobj.objgen[0])

        fonts = resources.get("/Font", {})
        font_count = len(fonts)
        font_raw_bytes = 0
        font_obj_ids: list[int] = []
        for _, fobj in fonts.items():
            desc_fonts = fobj.get("/DescendantFonts", None)
            if desc_fonts:
                for d in desc_fonts:
                    fd = d.get("/FontDescriptor", {})
                    for key in ("/FontFile2", "/FontFile", "/FontFile3"):
                        ff = fd.get(key)
                        if ff:
                            font_raw_bytes += len(ff.read_raw_bytes())
                            font_obj_ids.append(ff.objgen[0])
            else:
                fd = fobj.get("/FontDescriptor", {})
                for key in ("/FontFile2", "/FontFile", "/FontFile3"):
                    ff = fd.get(key)
                    if ff:
                        font_raw_bytes += len(ff.read_raw_bytes())
                        font_obj_ids.append(ff.objgen[0])

        return PdfObjectInfo(
            object_count=len(pdf.objects),
            image_count=image_count,
            image_total_raw_bytes=image_raw_bytes,
            image_object_ids=tuple(sorted(image_obj_ids)),
            font_count=font_count,
            font_total_raw_bytes=font_raw_bytes,
            font_object_ids=tuple(sorted(font_obj_ids)),
        )

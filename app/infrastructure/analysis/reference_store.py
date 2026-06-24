import hashlib
from dataclasses import dataclass
from pathlib import Path

import pikepdf

from app.domain.entities import Receipt
from app.domain.enums import AnomalyType
from app.domain.interfaces import ReferenceStore
from app.domain.value_objects import ForgeryIndicator, PdfMetadata


@dataclass(frozen=True)
class ReferenceFingerprint:
    filename: str
    image_hashes: tuple[str, ...]
    content_stream_hash: str


def _extract_image_hashes(file_path: Path) -> tuple[str, ...]:
    hashes = []
    with pikepdf.open(file_path) as pdf:
        page = pdf.pages[0]
        resources = page.get("/Resources", {})
        xobjects = resources.get("/XObject", {})
        for _, xobj in sorted(xobjects.items()):
            if str(xobj.get("/Subtype", "")) == "/Image":
                raw = xobj.read_raw_bytes()
                hashes.append(hashlib.sha256(raw).hexdigest())
    return tuple(hashes)


def _extract_content_hash(file_path: Path) -> str:
    with pikepdf.open(file_path) as pdf:
        page = pdf.pages[0]
        contents = page.get("/Contents")
        if contents and isinstance(contents, pikepdf.Stream):
            raw = contents.read_raw_bytes()
            return hashlib.sha256(raw).hexdigest()
    return ""


class FileReferenceStore(ReferenceStore):
    def __init__(
        self,
        reference_dir: Path,
        text_extractor=None,
        metadata_extractor=None,
    ) -> None:
        self._reference_dir = reference_dir
        self._fingerprints: list[ReferenceFingerprint] | None = None

    def get_reference_metadata(self) -> list[PdfMetadata]:
        return []

    def _load_fingerprints(self) -> list[ReferenceFingerprint]:
        if self._fingerprints is not None:
            return self._fingerprints

        self._fingerprints = []
        if not self._reference_dir.exists():
            return self._fingerprints

        for pdf_path in self._reference_dir.glob("*.pdf"):
            self._fingerprints.append(
                ReferenceFingerprint(
                    filename=pdf_path.name,
                    image_hashes=_extract_image_hashes(pdf_path),
                    content_stream_hash=_extract_content_hash(pdf_path),
                )
            )

        return self._fingerprints

    def compare_with_references(self, receipt: Receipt, file_path: Path | None = None) -> list[ForgeryIndicator]:
        fingerprints = self._load_fingerprints()
        if not fingerprints or not file_path:
            return []

        indicators: list[ForgeryIndicator] = []

        uploaded_image_hashes = _extract_image_hashes(file_path)
        uploaded_content_hash = _extract_content_hash(file_path)

        for ref in fingerprints:
            if not ref.image_hashes or not uploaded_image_hashes:
                continue

            images_match = ref.image_hashes == uploaded_image_hashes
            content_match = ref.content_stream_hash == uploaded_content_hash

            if images_match and content_match:
                continue

            if images_match and not content_match:
                indicators.append(
                    ForgeryIndicator(
                        anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                        description=(
                            f"Image raw bytes are identical to reference '{ref.filename}' "
                            f"but content stream differs - possible modified copy"
                        ),
                        severity=1.0,
                        target_field="image_bytes",
                    )
                )

        return indicators

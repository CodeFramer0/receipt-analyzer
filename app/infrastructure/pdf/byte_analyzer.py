import re
from pathlib import Path

import pikepdf

from app.domain.enums import AnomalyType
from app.domain.value_objects import ForgeryIndicator

HTML_TO_PDF_STREAM_SIGNATURES = [
    (rb"/CPDF\b", "CPDF (dompdf)"),
    (rb"wkhtmltopdf", "wkhtmltopdf"),
    (rb"/mPDF\b", "mPDF"),
    (rb"WeasyPrint", "WeasyPrint"),
    (rb"Prince", "Prince XML"),
]

PDF_EDITOR_STREAM_SIGNATURES = [
    (rb"NitroPDF", "Nitro PDF"),
    (rb"PDFelement", "PDFelement"),
    (rb"iLovePDF", "iLovePDF"),
]

DOMPDF_FONT_PATTERNS = [
    re.compile(rb"/BaseFont\s*/[A-Z]{6}\+.+?/FontDescriptor"),
    re.compile(rb"/Type\s*/Font\s*/Subtype\s*/Type1\b"),
]

WKHTMLTOPDF_RESOURCE_PATTERN = re.compile(
    rb"/XObject\s*<<.*?/Im\d+\s+\d+\s+0\s+R.*?>>", re.DOTALL
)


class PdfByteAnalyzer:

    def analyze(self, file_path: Path) -> list[ForgeryIndicator]:
        indicators: list[ForgeryIndicator] = []
        raw = file_path.read_bytes()

        indicators.extend(self._check_javascript(file_path))
        indicators.extend(self._check_actions(file_path))
        indicators.extend(self._check_embedded_files(file_path))
        indicators.extend(self._check_incremental_updates(raw))
        indicators.extend(self._check_stream_filters(file_path))
        indicators.extend(self._check_content_stream_operators(file_path))
        indicators.extend(self._check_trailing_data(raw))
        indicators.extend(self._check_annotations(file_path))
        indicators.extend(self._detect_generator_from_bytes(raw, file_path))
        indicators.extend(self._check_stream_length_mismatch(raw))
        indicators.extend(self._check_forbidden_objects(file_path))

        return indicators

    def _check_javascript(self, file_path: Path) -> list[ForgeryIndicator]:
        with pikepdf.open(file_path) as pdf:
            for objgen in pdf.objects:
                try:
                    obj = pdf.get_object(objgen)
                    if not isinstance(obj, pikepdf.Dictionary):
                        continue
                    if "/JS" in obj or "/JavaScript" in obj:
                        return [
                            ForgeryIndicator(
                                anomaly_type=AnomalyType.JAVASCRIPT_DETECTED,
                                description="JavaScript code found — never present in legitimate bank receipts",
                                severity=1.0,
                                target_field="javascript",
                            )
                        ]
                except Exception:
                    continue
        return []

    def _check_actions(self, file_path: Path) -> list[ForgeryIndicator]:
        results: list[ForgeryIndicator] = []
        with pikepdf.open(file_path) as pdf:
            catalog = pdf.Root
            if "/OpenAction" in catalog:
                results.append(
                    ForgeryIndicator(
                        anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                        description="OpenAction in document catalog — unusual for bank receipts",
                        severity=0.9,
                        target_field="actions",
                    )
                )
            if "/AA" in catalog:
                results.append(
                    ForgeryIndicator(
                        anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                        description="Additional Actions (AA) in catalog — unusual for bank receipts",
                        severity=0.9,
                        target_field="actions",
                    )
                )
            for page in pdf.pages:
                if "/AA" in page:
                    results.append(
                        ForgeryIndicator(
                            anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                            description="Page-level actions detected — unusual for bank receipts",
                            severity=0.85,
                            target_field="actions",
                        )
                    )
                    break
        return results

    def _check_embedded_files(self, file_path: Path) -> list[ForgeryIndicator]:
        with pikepdf.open(file_path) as pdf:
            names = pdf.Root.get("/Names")
            if isinstance(names, pikepdf.Dictionary):
                if names.get("/EmbeddedFiles") is not None:
                    return [
                        ForgeryIndicator(
                            anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                            description="Embedded files found — unusual for bank receipts",
                            severity=0.8,
                            target_field="embedded_files",
                        )
                    ]
        return []

    def _check_incremental_updates(self, raw: bytes) -> list[ForgeryIndicator]:
        results: list[ForgeryIndicator] = []
        eof_positions = [m.end() for m in re.finditer(rb"%%EOF", raw)]

        if len(eof_positions) <= 1:
            return results

        later_content = raw[eof_positions[0]:]

        page_obj_re = rb"\d+\s+0\s+obj\b.*?/Type\s*/Page\b"
        if re.search(page_obj_re, later_content, re.DOTALL):
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.REVISION_ANOMALY,
                    description=(
                        f"Page objects modified in incremental update "
                        f"(revision {len(eof_positions)}) — possible content tampering"
                    ),
                    severity=1.0,
                    target_field="incremental_update",
                )
            )

        text_op_re = rb"\d+\s+0\s+obj\b.*?stream\r?\n.*?(?:Tj|TJ)\s"
        if re.search(text_op_re, later_content, re.DOTALL):
            results.append(
                ForgeryIndicator(
                    anomaly_type=AnomalyType.CONTENT_STREAM_ANOMALY,
                    description="Text operators in incremental update — text modified after creation",
                    severity=1.0,
                    target_field="content_stream",
                )
            )

        return results

    def _check_stream_filters(self, file_path: Path) -> list[ForgeryIndicator]:
        unusual_filters = {"/JBIG2Decode", "/Crypt", "/LZWDecode"}

        with pikepdf.open(file_path) as pdf:
            for objgen in pdf.objects:
                try:
                    obj = pdf.get_object(objgen)
                    if not isinstance(obj, pikepdf.Stream):
                        continue
                    filter_val = obj.get("/Filter")
                    if filter_val is None:
                        continue

                    filters: list[str] = []
                    if isinstance(filter_val, pikepdf.Array):
                        filters = [str(f) for f in filter_val]
                    else:
                        filters = [str(filter_val)]

                    for f in filters:
                        if f in unusual_filters:
                            return [
                                ForgeryIndicator(
                                    anomaly_type=AnomalyType.STREAM_ANOMALY,
                                    description=f"Unusual stream filter '{f}' — atypical for bank receipts",
                                    severity=0.7,
                                    target_field="stream_filter",
                                )
                            ]

                    if len(filters) > 2:
                        return [
                            ForgeryIndicator(
                                anomaly_type=AnomalyType.STREAM_ANOMALY,
                                description=f"Complex filter chain ({' + '.join(filters)}) — unusual for receipts",
                                severity=0.6,
                                target_field="stream_filter",
                            )
                        ]
                except Exception:
                    continue
        return []

    def _check_content_stream_operators(self, file_path: Path) -> list[ForgeryIndicator]:
        results: list[ForgeryIndicator] = []

        with pikepdf.open(file_path) as pdf:
            for page in pdf.pages:
                try:
                    data = self._read_page_content(page)
                    if not data:
                        continue

                    text = data.decode("latin-1", errors="ignore")
                    results.extend(self._detect_white_text(text))
                    results.extend(self._detect_invisible_text(text))
                    results.extend(self._detect_form_overlays(text, page))
                    results.extend(self._detect_clipping_masks(text))

                    if results:
                        return results
                except Exception:
                    continue
        return results

    def _read_page_content(self, page: pikepdf.Page) -> bytes:
        contents = page.get("/Contents")
        if contents is None:
            return b""
        if isinstance(contents, pikepdf.Stream):
            return contents.read_bytes()
        if isinstance(contents, pikepdf.Array):
            return b"".join(s.read_bytes() for s in contents)
        return b""

    def _detect_white_text(self, text: str) -> list[ForgeryIndicator]:
        if re.search(r"1\s+1\s+1\s+rg\b.*?(?:Tj|TJ)", text, re.DOTALL):
            return [
                ForgeryIndicator(
                    anomaly_type=AnomalyType.CONTENT_STREAM_ANOMALY,
                    description="Text rendered in white color — possible hidden content",
                    severity=0.9,
                    target_field="content_stream",
                )
            ]
        return []

    def _detect_invisible_text(self, text: str) -> list[ForgeryIndicator]:
        if re.search(r"3\s+Tr\b", text):
            return [
                ForgeryIndicator(
                    anomaly_type=AnomalyType.CONTENT_STREAM_ANOMALY,
                    description="Invisible text rendering mode (Tr 3) detected",
                    severity=0.8,
                    target_field="content_stream",
                )
            ]
        return []

    def _detect_form_overlays(
        self, text: str, page: pikepdf.Page
    ) -> list[ForgeryIndicator]:
        do_ops = re.findall(r"/(\w+)\s+Do\b", text)
        resources = page.get("/Resources", {})
        xobjects = resources.get("/XObject", {})

        form_count = 0
        for name in do_ops:
            xobj = xobjects.get(f"/{name}")
            if xobj is not None and str(xobj.get("/Subtype", "")) == "/Form":
                form_count += 1

        if form_count > 2:
            return [
                ForgeryIndicator(
                    anomaly_type=AnomalyType.CONTENT_STREAM_ANOMALY,
                    description=f"Multiple Form XObjects ({form_count}) as overlays — unusual for receipts",
                    severity=0.7,
                    target_field="content_stream",
                )
            ]
        return []

    def _detect_clipping_masks(self, text: str) -> list[ForgeryIndicator]:
        clip_count = len(re.findall(r"\bW\s+n\b", text))
        if clip_count > 3:
            return [
                ForgeryIndicator(
                    anomaly_type=AnomalyType.CONTENT_STREAM_ANOMALY,
                    description=(
                        f"Excessive clipping operations ({clip_count}) — "
                        f"may indicate content masking"
                    ),
                    severity=0.6,
                    target_field="content_stream",
                )
            ]
        return []

    def _check_trailing_data(self, raw: bytes) -> list[ForgeryIndicator]:
        eof_positions = list(re.finditer(rb"%%EOF", raw))
        if not eof_positions:
            return []
        last_eof = eof_positions[-1].end()
        trailing = raw[last_eof:].strip()
        if len(trailing) > 10:
            return [
                ForgeryIndicator(
                    anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                    description=f"Significant data ({len(trailing)} bytes) after final %%EOF marker",
                    severity=0.8,
                    target_field="trailing_data",
                )
            ]
        return []

    def _check_annotations(self, file_path: Path) -> list[ForgeryIndicator]:
        with pikepdf.open(file_path) as pdf:
            annotation_count = 0
            for page in pdf.pages:
                annots = page.get("/Annots")
                if isinstance(annots, pikepdf.Array):
                    annotation_count += len(annots)

            if annotation_count > 0:
                return [
                    ForgeryIndicator(
                        anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                        description=f"Annotations ({annotation_count}) found — unusual for bank receipts",
                        severity=0.7,
                        target_field="annotations",
                    )
                ]
        return []

    def _detect_generator_from_bytes(
        self, raw: bytes, file_path: Path
    ) -> list[ForgeryIndicator]:
        results: list[ForgeryIndicator] = []

        for pattern, tool_name in HTML_TO_PDF_STREAM_SIGNATURES:
            if re.search(pattern, raw):
                results.append(
                    ForgeryIndicator(
                        anomaly_type=AnomalyType.TOOL_MISMATCH,
                        description=(
                            f"HTML-to-PDF generator '{tool_name}' detected in binary content "
                            f"— not a legitimate bank receipt system"
                        ),
                        severity=0.95,
                        target_field="generator",
                    )
                )
                return results

        for pattern, tool_name in PDF_EDITOR_STREAM_SIGNATURES:
            if re.search(pattern, raw):
                results.append(
                    ForgeryIndicator(
                        anomaly_type=AnomalyType.TOOL_MISMATCH,
                        description=f"PDF editor '{tool_name}' signature found in binary content",
                        severity=0.8,
                        target_field="generator",
                    )
                )
                return results

        try:
            with pikepdf.open(file_path) as pdf:
                for page in pdf.pages:
                    data = self._read_page_content(page)
                    if not data:
                        continue

                    for p in DOMPDF_FONT_PATTERNS:
                        if p.search(raw) and b"CPDF" in raw:
                            results.append(
                                ForgeryIndicator(
                                    anomaly_type=AnomalyType.TOOL_MISMATCH,
                                    description=(
                                        "Font structure patterns consistent with "
                                        "dompdf/CPDF generator"
                                    ),
                                    severity=0.9,
                                    target_field="generator",
                                )
                            )
                            return results
        except Exception:
            pass

        return results

    def _check_stream_length_mismatch(self, raw: bytes) -> list[ForgeryIndicator]:
        length_pattern = re.compile(
            rb"(\d+)\s+0\s+obj\s*<<.*?/Length\s+(\d+)\b.*?>>.*?stream\r?\n",
            re.DOTALL,
        )

        mismatches = 0
        for match in length_pattern.finditer(raw):
            declared_length = int(match.group(2))
            stream_start = match.end()
            endstream_pos = raw.find(b"endstream", stream_start)
            if endstream_pos < 0:
                continue

            actual_data = raw[stream_start:endstream_pos]
            actual_length = len(actual_data.rstrip(b"\r\n"))

            if declared_length > 0 and abs(actual_length - declared_length) > 2:
                mismatches += 1

        if mismatches > 0:
            return [
                ForgeryIndicator(
                    anomaly_type=AnomalyType.STREAM_ANOMALY,
                    description=(
                        f"Stream length mismatch in {mismatches} object(s) — "
                        f"declared /Length differs from actual stream bytes"
                    ),
                    severity=0.85,
                    target_field="stream_length",
                )
            ]
        return []

    def _check_forbidden_objects(self, file_path: Path) -> list[ForgeryIndicator]:
        results: list[ForgeryIndicator] = []
        with pikepdf.open(file_path) as pdf:
            has_acroform = "/AcroForm" in pdf.Root
            has_sig = False

            for objgen in pdf.objects:
                try:
                    obj = pdf.get_object(objgen)
                    if not isinstance(obj, pikepdf.Dictionary):
                        continue
                    obj_type = str(obj.get("/Type", ""))
                    obj_subtype = str(obj.get("/Subtype", ""))

                    if obj_type == "/Sig" or obj_subtype == "/Widget":
                        has_sig = True
                except Exception:
                    continue

            if has_acroform:
                results.append(
                    ForgeryIndicator(
                        anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                        description="AcroForm (interactive forms) found — unusual for bank receipts",
                        severity=0.8,
                        target_field="forbidden_objects",
                    )
                )

            if has_sig:
                results.append(
                    ForgeryIndicator(
                        anomaly_type=AnomalyType.STRUCTURE_ANOMALY,
                        description="Signature/Widget objects found — unusual for bank receipts",
                        severity=0.7,
                        target_field="forbidden_objects",
                    )
                )

        return results

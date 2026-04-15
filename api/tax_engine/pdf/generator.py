"""PDFGenerator — fills IRS PDF templates and merges active forms."""
import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, TextStringObject

from api.tax_engine.models.tax_return import TaxReturn, TaxResult
from api.tax_engine.pdf.field_maps import (
    map_f1040, map_schedule_a, map_schedule_b, map_schedule_d,
    map_schedule_e, map_schedule_se, map_form_8812,
    map_form_8959, map_form_8960, map_form_8995,
    is_schedule_a_active, is_schedule_b_active, is_schedule_d_active,
    is_schedule_e_active, is_schedule_se_active, is_form_8812_active,
    is_form_active,
)

DEFAULT_TEMPLATES_DIR = Path(__file__).parent / "templates"

_FORM_REGISTRY = [
    ("f1040.pdf",    None,   map_f1040,       lambda tr, r: True),
    ("f1040sb.pdf",  "sb",   map_schedule_b,  is_schedule_b_active),
    ("f1040sa.pdf",  "sa",   map_schedule_a,  is_schedule_a_active),
    ("f1040sd.pdf",  "sd",   map_schedule_d,  is_schedule_d_active),
    ("f1040se.pdf",  "se",   map_schedule_e,  is_schedule_e_active),
    ("f1040sse.pdf", "sse",  map_schedule_se, is_schedule_se_active),
    ("f1040s8.pdf",  "s8",   map_form_8812,   is_form_8812_active),
    ("f8959.pdf",    "m89",  map_form_8959,   lambda tr, r: is_form_active(tr, r, "Form 8959")),
    ("f8960.pdf",    "n89",  map_form_8960,   lambda tr, r: is_form_active(tr, r, "Form 8960")),
    ("f8995.pdf",    "q89",  map_form_8995,   lambda tr, r: is_form_active(tr, r, "Form 8995")),
]


class PDFGenerator:
    def __init__(self, templates_dir: Path | None = None):
        self.templates_dir = templates_dir or DEFAULT_TEMPLATES_DIR

    def generate(self, tax_return: TaxReturn, result: TaxResult) -> bytes:
        filled_buffers: list[tuple[str | None, io.BytesIO]] = []
        for template_name, prefix, map_fn, active_fn in _FORM_REGISTRY:
            if not active_fn(tax_return, result):
                continue
            fields_by_page = map_fn(tax_return, result)
            buf = self._fill_form(template_name, fields_by_page)
            if buf is not None:
                filled_buffers.append((prefix, buf))

        final_writer = PdfWriter()
        for prefix, buf in filled_buffers:
            reader = PdfReader(buf)
            if prefix is not None:
                self._rename_fields(reader, prefix)
            final_writer.append(reader)

        output = io.BytesIO()
        final_writer.write(output)
        return output.getvalue()

    def _fill_form(self, template_name: str, fields_by_page: dict[int, dict[str, str]]) -> io.BytesIO | None:
        path = self.templates_dir / template_name
        if not path.exists():
            return None
        reader = PdfReader(str(path))
        writer = PdfWriter()
        writer.append(reader)
        for page_idx, fields in fields_by_page.items():
            cleaned = {k: v for k, v in fields.items() if v not in (None, "")}
            if cleaned and page_idx < len(writer.pages):
                writer.update_page_form_field_values(writer.pages[page_idx], cleaned)
        buf = io.BytesIO()
        writer.write(buf)
        buf.seek(0)
        return buf

    def _rename_fields(self, reader: PdfReader, prefix: str) -> None:
        for page in reader.pages:
            annots = page.get("/Annots")
            if annots:
                for annot in annots:
                    obj = annot.get_object()
                    if "/T" in obj:
                        old_name = str(obj["/T"])
                        obj[NameObject("/T")] = TextStringObject(f"{prefix}_{old_name}")

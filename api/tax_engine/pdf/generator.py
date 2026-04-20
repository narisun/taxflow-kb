"""PDFGenerator — fills IRS PDF templates and merges active forms."""
import io
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, TextStringObject

from api.tax_engine.models.tax_return import TaxReturn, TaxResult
from api.models.tax_return import FormManifestEntry, ReturnManifest
from api.tax_engine.pdf.field_maps import (
    map_f1040, map_schedule_a, map_schedule_b, map_schedule_d,
    map_schedule_e, map_schedule_se, map_form_8812,
    map_form_8959, map_form_8960, map_form_8995,
    is_schedule_a_active, is_schedule_b_active, is_schedule_d_active,
    is_schedule_e_active, is_schedule_se_active, is_form_8812_active,
    is_form_active,
)

DEFAULT_TEMPLATES_DIR = Path(__file__).parent / "templates"

_FORM_LABELS = {
    "f1040.pdf":    ("f1040",  "Form 1040"),
    "f1040sb.pdf":  ("sb",     "Schedule B"),
    "f1040sa.pdf":  ("sa",     "Schedule A"),
    "f1040sd.pdf":  ("sd",     "Schedule D"),
    "f1040se.pdf":  ("se",     "Schedule E"),
    "f1040sse.pdf": ("sse",    "Schedule SE"),
    "f1040s8.pdf":  ("f8812",  "Form 8812"),
    "f8959.pdf":    ("f8959",  "Form 8959"),
    "f8960.pdf":    ("f8960",  "Form 8960"),
    "f8995.pdf":    ("f8995",  "Form 8995"),
}

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

    def generate_manifest(self, tax_return: TaxReturn, result: TaxResult) -> ReturnManifest:
        """Return activation status and page ranges for all registered forms."""
        forms: list[FormManifestEntry] = []
        current_page = 1

        for template_name, _prefix, _map_fn, active_fn in _FORM_REGISTRY:
            form_id, label = _FORM_LABELS[template_name]
            active = active_fn(tax_return, result)

            if active:
                path = self.templates_dir / template_name
                page_count = len(PdfReader(str(path)).pages) if path.exists() else 0
                forms.append(FormManifestEntry(
                    id=form_id, label=label, active=True,
                    start_page=current_page, page_count=page_count,
                ))
                current_page += page_count
            else:
                forms.append(FormManifestEntry(
                    id=form_id, label=label, active=False,
                    start_page=None, page_count=0,
                ))

        return ReturnManifest(total_pages=current_page - 1, forms=forms)

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

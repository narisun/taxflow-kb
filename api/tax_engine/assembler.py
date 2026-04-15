"""DocumentAssembler — builds TaxReturn from approved documents + manual overrides."""
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import ClientModel, DocumentModel, ManualEntryModel
from api.tax_engine.models.people import Person, Address
from api.tax_engine.models.income import (
    W2, Income1099Int, Income1099Div, Income1099B, Income1099NEC, ScheduleK1,
)
from api.tax_engine.models.deductions import Mortgage1098
from api.tax_engine.models.tax_return import TaxReturn

_FORM_MAP: dict[str, tuple[type, str]] = {
    "W-2": (W2, "w2s"),
    "1099-INT": (Income1099Int, "interest_1099s"),
    "1099-DIV": (Income1099Div, "dividend_1099s"),
    "1099-B": (Income1099B, "broker_1099s"),
    "1099-NEC": (Income1099NEC, "nec_1099s"),
    "1098": (Mortgage1098, "mortgages"),
    "K-1": (ScheduleK1, "k1s"),
}

_FILING_STATUS_MAP = {
    "single": "S", "mfj": "MFJ", "mfs": "MFS", "hoh": "HOH", "qw": "QSS",
    "S": "S", "MFJ": "MFJ", "MFS": "MFS", "HOH": "HOH", "QSS": "QSS",
}


class DocumentAssembler:
    async def assemble(self, client_id: int, session: AsyncSession) -> TaxReturn:
        result = await session.execute(select(ClientModel).where(ClientModel.id == client_id))
        client = result.scalar_one()

        doc_result = await session.execute(
            select(DocumentModel).where(DocumentModel.client_id == client_id, DocumentModel.status == "approved"))
        docs = doc_result.scalars().all()

        override_result = await session.execute(
            select(ManualEntryModel).where(ManualEntryModel.client_id == client_id))
        overrides = override_result.scalars().all()

        override_map: dict[tuple[str, int], dict[str, str]] = defaultdict(dict)
        for ov in overrides:
            override_map[(ov.form_type, ov.form_index)][ov.field_name] = ov.value

        form_lists: dict[str, list] = defaultdict(list)
        form_type_counts: dict[str, int] = defaultdict(int)

        for doc in docs:
            form_type = doc.form_type
            if form_type not in _FORM_MAP:
                continue
            model_cls, field_name = _FORM_MAP[form_type]
            raw = json.loads(doc.extracted_data) if doc.extracted_data else {}

            # Handle both structured dict (new) and list of ExtractedField dicts (legacy)
            if isinstance(raw, list):
                data = {}
                for item in raw:
                    if isinstance(item, dict) and "name" in item and "value" in item:
                        data[item["name"]] = item["value"]
            elif isinstance(raw, dict):
                data = raw
            else:
                data = {}
            idx = form_type_counts[form_type]
            if (form_type, idx) in override_map:
                data.update(override_map[(form_type, idx)])
            form_type_counts[form_type] += 1
            try:
                model = model_cls(**data)
                form_lists[field_name].append(model)
            except Exception:
                continue

        filing_status = _FILING_STATUS_MAP.get(client.filing_status, "S")
        name_parts = client.name.split() if client.name else ["Unknown"]
        primary = Person(
            first_name=name_parts[0],
            last_name=name_parts[-1] if len(name_parts) > 1 else "Unknown",
            ssn="999119999",
            date_of_birth=date(1980, 1, 1),
        )

        return TaxReturn(
            tax_year=client.tax_year,
            filing_status=filing_status,
            primary=primary,
            address=Address(street="TBD", city="TBD", state="XX", zip_code="00000"),
            w2s=form_lists.get("w2s", []),
            interest_1099s=form_lists.get("interest_1099s", []),
            dividend_1099s=form_lists.get("dividend_1099s", []),
            broker_1099s=form_lists.get("broker_1099s", []),
            nec_1099s=form_lists.get("nec_1099s", []),
            mortgages=form_lists.get("mortgages", []),
            k1s=form_lists.get("k1s", []),
        )

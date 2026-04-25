"""DocumentAssembler — builds TaxReturn from approved documents + manual overrides."""
import json
import logging
from collections import defaultdict
from datetime import date
from decimal import Decimal  # noqa: F401 — used by imported tax_engine models

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import ClientModel, DocumentModel, ManualEntryModel, DependentModel, FamilyGroupModel
from api.services.pii.encryptor import PIIEncryptor, get_pii_encryptor
from api.tax_engine.models.people import Person, Dependent, Address
from api.tax_engine.models.income import (
    W2, Income1099Int, Income1099Div, Income1099B, Income1099NEC, ScheduleK1,
)
from api.tax_engine.models.deductions import Mortgage1098
from api.tax_engine.models.tax_return import TaxReturn

logger = logging.getLogger(__name__)

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
    """Assembles a :class:`TaxReturn` domain object from DB records.

    The encryptor is injected so tests can pass a fake or a key-specific
    instance. Callers that cannot inject one get the legacy settings-backed
    singleton via :func:`api.services.pii.encryptor.get_pii_encryptor`.
    """

    def __init__(self, encryptor: PIIEncryptor | None = None):
        self._encryptor = encryptor if encryptor is not None else get_pii_encryptor()
        self.skipped_documents: list[dict] = []

    async def assemble(self, client_id: str, session: AsyncSession) -> TaxReturn:
        self.skipped_documents = []

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
            except Exception as e:
                logger.info(
                    "Skipping document_id=%s (%s): %s", doc.id, form_type, e
                )
                self.skipped_documents.append({
                    "document_id": doc.id,
                    "form_type": form_type,
                    "reason": str(e),
                })
                continue

        filing_status = _FILING_STATUS_MAP.get(client.filing_status, "S")

        enc = self._encryptor

        # Primary person
        ssn = enc.decrypt(client.primary_ssn_enc) if client.primary_ssn_enc else "999119999"
        dob_str = enc.decrypt(client.primary_dob_enc) if client.primary_dob_enc else "1980-01-01"
        dob = date.fromisoformat(dob_str)
        primary = Person(
            first_name=client.primary_first_name or "Unknown",
            last_name=client.primary_last_name or "Unknown",
            ssn=ssn,
            date_of_birth=dob,
        )

        # Address
        street = enc.decrypt(client.street_enc) if client.street_enc else "TBD"
        address = Address(
            street=street,
            city=client.city or "TBD",
            state=client.state or "XX",
            zip_code=client.zip_code or "00000",
        )

        # Spouse (if encrypted data exists)
        spouse = None
        if client.spouse_ssn_enc:
            spouse_ssn = enc.decrypt(client.spouse_ssn_enc)
            spouse_dob_str = enc.decrypt(client.spouse_dob_enc) if client.spouse_dob_enc else "1980-01-01"
            spouse_first = "Spouse"
            spouse_last = client.primary_last_name or "Unknown"
            if client.family_group_id:
                fg_result = await session.execute(
                    select(FamilyGroupModel).where(FamilyGroupModel.id == client.family_group_id)
                )
                fg = fg_result.scalar_one_or_none()
                if fg and fg.spouse_first_name:
                    spouse_first = fg.spouse_first_name
                    spouse_last = fg.spouse_last_name or spouse_last
            spouse = Person(
                first_name=spouse_first, last_name=spouse_last,
                ssn=spouse_ssn, date_of_birth=date.fromisoformat(spouse_dob_str),
            )

        # Dependents from DB
        dep_result = await session.execute(
            select(DependentModel).where(DependentModel.client_id == client_id)
        )
        db_deps = dep_result.scalars().all()
        dependents = []
        for dep in db_deps:
            dep_ssn = enc.decrypt(dep.ssn_enc) if dep.ssn_enc else "999999999"
            dep_dob_str = enc.decrypt(dep.dob_enc) if dep.dob_enc else "2000-01-01"
            dependents.append(Dependent(
                first_name=dep.first_name, last_name=dep.last_name,
                ssn=dep_ssn, date_of_birth=date.fromisoformat(dep_dob_str),
                relationship=dep.relationship, months_lived_with=dep.months_lived_with,
                is_student=dep.is_student, is_qualifying_child=dep.is_qualifying_child,
                is_us_citizen=dep.is_us_citizen,
            ))

        return TaxReturn(
            tax_year=client.tax_year,
            filing_status=filing_status,
            primary=primary,
            spouse=spouse,
            dependents=dependents,
            address=address,
            w2s=form_lists.get("w2s", []),
            interest_1099s=form_lists.get("interest_1099s", []),
            dividend_1099s=form_lists.get("dividend_1099s", []),
            broker_1099s=form_lists.get("broker_1099s", []),
            nec_1099s=form_lists.get("nec_1099s", []),
            mortgages=form_lists.get("mortgages", []),
            k1s=form_lists.get("k1s", []),
        )

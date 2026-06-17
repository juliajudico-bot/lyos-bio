from __future__ import annotations
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import List, Optional
from models.database import get_db, Document
from services.claude_service import run_tabular_extraction

router = APIRouter(prefix="/api/tabular", tags=["tabular"])

PRESET_FIELD_SETS = {
    "consent_form": [
        "Patient Full Name",
        "Date of Birth",
        "Collection Date",
        "Hospital/Birth Center",
        "Storage Duration",
        "Annual Storage Fee",
        "Physician Name",
        "Patient Signature Present",
        "Witness Signature Present",
        "Date Signed",
    ],
    "donor_agreement": [
        "Donor Name",
        "Agreement Date",
        "Collection Kit ID",
        "Storage Term (Years)",
        "Initial Processing Fee",
        "Annual Storage Fee",
        "Cancellation Policy",
        "Governing Law (State)",
        "Arbitration Clause",
        "Signature Date",
    ],
    "nda": [
        "Party 1 Name",
        "Party 2 Name",
        "Effective Date",
        "Expiration Date",
        "Confidentiality Period",
        "Permitted Disclosures",
        "Return of Information Clause",
        "Governing Law",
        "Signature Date",
    ],
}


class TabularRequest(BaseModel):
    document_ids: List[str]
    fields: Optional[List[str]] = None
    preset: Optional[str] = None  # "consent_form", "donor_agreement", "nda"


@router.post("/extract")
async def tabular_extract(req: TabularRequest, db: AsyncSession = Depends(get_db)):
    fields = req.fields
    if not fields and req.preset:
        fields = PRESET_FIELD_SETS.get(req.preset)
    if not fields:
        raise HTTPException(400, "Provide fields or a preset")

    results = []
    for doc_id in req.document_ids:
        result = await db.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        if not doc:
            continue
        extracted = await run_tabular_extraction(fields, {"name": doc.name, "content": doc.content})
        results.append({"document_id": doc.id, "document_name": doc.name, "fields": extracted})

    return {"results": results, "fields": fields}


@router.get("/presets")
async def get_presets():
    return [
        {"id": k, "name": k.replace("_", " ").title(), "fields": v}
        for k, v in PRESET_FIELD_SETS.items()
    ]

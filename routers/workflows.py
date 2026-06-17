from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from models.database import get_db, Workflow, Document, gen_id
from services.claude_service import run_workflow

router = APIRouter(prefix="/api/workflows", tags=["workflows"])

BUILTIN_WORKFLOWS = [
    {
        "id": "wf-consent-review",
        "name": "Cord Blood Consent Form Review",
        "description": "Review a cord blood banking consent form for completeness, required disclosures, and patient signature fields.",
        "category": "Consent & Agreements",
        "is_builtin": True,
        "prompt": """Review this cord blood banking consent form and provide:
1. **Completeness Check**: List all required fields and whether they are present (patient name, DOB, collection method, storage term, fees, withdrawal rights, etc.)
2. **Required Disclosures**: Confirm FDA-required disclosures are present (infectious disease testing, limitations of banking, etc.)
3. **Missing Elements**: Any required fields or clauses that are absent
4. **Risk Disclosures**: Are the risks and limitations of cord blood banking clearly disclosed?
5. **Patient Rights**: Are withdrawal/cancellation rights properly stated?
6. **Signature Fields**: Are all required signature lines present (patient, witness, date)?
7. **Overall Assessment**: PASS / NEEDS REVISION / FAIL with brief explanation

Cite specific page numbers and verbatim quotes for each finding.""",
    },
    {
        "id": "wf-donor-agreement",
        "name": "Donor Agreement Analysis",
        "description": "Analyze a donor agreement for key terms, obligations, and potential issues.",
        "category": "Consent & Agreements",
        "is_builtin": True,
        "prompt": """Analyze this donor agreement and provide:
1. **Key Parties**: Identify all parties and their roles
2. **Donor Obligations**: List all obligations placed on the donor
3. **Company Obligations**: List all obligations placed on Americord
4. **Storage Terms**: Duration, conditions, and renewal terms
5. **Fee Structure**: All fees, payment schedules, and late payment provisions
6. **Termination Clauses**: How the agreement can be terminated and consequences
7. **Liability Limitations**: Any caps on liability or indemnification clauses
8. **Unusual or Concerning Clauses**: Flag anything non-standard
9. **Missing Standard Clauses**: What's typically present that's absent here?

Cite page numbers and verbatim quotes for all findings.""",
    },
    {
        "id": "wf-hipaa-review",
        "name": "HIPAA Compliance Review",
        "description": "Review a document for HIPAA compliance requirements and PHI handling.",
        "category": "Compliance",
        "is_builtin": True,
        "prompt": """Review this document for HIPAA compliance and provide:
1. **PHI Identification**: List all Protected Health Information (PHI) elements mentioned
2. **Authorization Requirements**: Are proper patient authorizations for PHI use/disclosure present?
3. **Minimum Necessary Standard**: Does the document limit PHI to what's minimum necessary?
4. **Business Associate Provisions**: If applicable, are BAA requirements addressed?
5. **Patient Rights**: Notice of Privacy Practices, right to access, right to restrict?
6. **Security Safeguards**: Any references to technical, physical, or administrative safeguards?
7. **Breach Notification**: Is breach notification language present and correct?
8. **Compliance Gaps**: List specific HIPAA gaps with citations
9. **Recommendations**: Priority list of remediation steps

Cite specific provisions with page numbers.""",
    },
    {
        "id": "wf-aabb-checklist",
        "name": "AABB Standards Checklist",
        "description": "Check a procedure or protocol document against AABB cord blood standards.",
        "category": "Compliance",
        "is_builtin": True,
        "prompt": """Review this document against AABB cord blood banking standards and provide:
1. **Collection Requirements**: Are collection procedures documented per AABB standards?
2. **Testing Requirements**: Infectious disease testing, HLA typing, cell viability requirements
3. **Processing Standards**: Chain of custody, processing conditions, quality controls
4. **Storage Requirements**: Cryopreservation conditions, temperature monitoring, alarm systems
5. **Labeling Requirements**: Unit ID, volume, cell counts, test results labeling
6. **Release Criteria**: Criteria for releasing units for transplant
7. **Record-Keeping**: Documentation and retention requirements
8. **Non-Conformances**: List specific deviations from AABB standards
9. **AABB Compliance Score**: Estimated compliance percentage with explanation

Reference AABB standards by section where applicable.""",
    },
    {
        "id": "wf-collection-protocol",
        "name": "Collection Protocol Review",
        "description": "Review a cord blood collection protocol for completeness and safety.",
        "category": "Clinical",
        "is_builtin": True,
        "prompt": """Review this cord blood collection protocol and provide:
1. **Protocol Completeness**: Is all required information present?
2. **Collection Timing**: Pre-birth, post-birth, clamp timing instructions
3. **Volume Requirements**: Minimum/target collection volumes
4. **Safety Checks**: Contraindications, maternal screening requirements
5. **Chain of Custody**: Documentation from collection through transport
6. **Transport Instructions**: Temperature, timing, packaging requirements
7. **Rejection Criteria**: When a collection should be rejected
8. **Emergency Procedures**: What to do if collection fails or complications arise
9. **Staff Requirements**: Qualifications required for collection
10. **Protocol Gaps**: What's missing compared to best practices?

Provide a structured summary with citations for all findings.""",
    },
    {
        "id": "wf-insurance-review",
        "name": "Insurance & Billing Document Review",
        "description": "Review insurance or billing documents for accuracy and completeness.",
        "category": "Administrative",
        "is_builtin": True,
        "prompt": """Review this insurance or billing document and provide:
1. **Billing Codes**: Are CPT/ICD codes accurate and appropriate?
2. **Coverage Verification**: What services are covered vs. excluded?
3. **Patient Financial Responsibility**: Clear explanation of what patient owes?
4. **Insurance Coordination**: Primary/secondary insurance coordination provisions
5. **Appeal Rights**: Patient rights to appeal denials
6. **Fraud & Abuse**: Any language that could raise compliance concerns?
7. **Accuracy**: Are all amounts, dates, and identifiers correct?
8. **Missing Information**: Required fields that are blank or incomplete
9. **Recommendations**: Priority corrections needed

Cite specific line items and section references.""",
    },
]


class WorkflowCreate(BaseModel):
    name: str
    description: str = ""
    prompt: str
    category: str = "custom"


class WorkflowRunRequest(BaseModel):
    document_ids: list[str]


@router.get("/")
async def list_workflows(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Workflow).order_by(Workflow.created_at))
    custom = result.scalars().all()
    return BUILTIN_WORKFLOWS + [
        {
            "id": w.id,
            "name": w.name,
            "description": w.description,
            "category": w.category,
            "is_builtin": False,
            "prompt": w.prompt,
        }
        for w in custom
    ]


@router.post("/")
async def create_workflow(data: WorkflowCreate, db: AsyncSession = Depends(get_db)):
    wf = Workflow(id=gen_id(), name=data.name, description=data.description,
                  prompt=data.prompt, category=data.category, is_builtin=False)
    db.add(wf)
    await db.commit()
    await db.refresh(wf)
    return {"id": wf.id, "name": wf.name, "description": wf.description,
            "category": wf.category, "is_builtin": False}


@router.post("/{workflow_id}/run")
async def run_workflow_endpoint(
    workflow_id: str,
    req: WorkflowRunRequest,
    db: AsyncSession = Depends(get_db),
):
    # Find workflow
    wf_data = next((w for w in BUILTIN_WORKFLOWS if w["id"] == workflow_id), None)
    if not wf_data:
        result = await db.execute(select(Workflow).where(Workflow.id == workflow_id))
        wf = result.scalar_one_or_none()
        if not wf:
            raise HTTPException(404, "Workflow not found")
        wf_data = {"prompt": wf.prompt, "name": wf.name}

    # Load documents
    docs = []
    for doc_id in req.document_ids:
        result = await db.execute(select(Document).where(Document.id == doc_id))
        doc = result.scalar_one_or_none()
        if doc:
            docs.append({"name": doc.name, "content": doc.content})

    if not docs:
        raise HTTPException(400, "No valid documents provided")

    result_text = await run_workflow(wf_data["prompt"], docs)
    return {"result": result_text, "workflow_name": wf_data["name"]}

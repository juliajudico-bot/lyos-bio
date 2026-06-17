from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import aiofiles
import os
from pathlib import Path
from models.database import get_db, Document, Project, gen_id
from services.document_service import extract_text, UPLOAD_DIR

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/{project_id}/upload")
async def upload_document(
    project_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")

    doc_id = gen_id()
    ext = Path(file.filename).suffix.lower().lstrip(".")
    save_path = UPLOAD_DIR / f"{doc_id}.{ext}"

    async with aiofiles.open(save_path, "wb") as f:
        content = await file.read()
        await f.write(content)

    try:
        text, page_count = extract_text(str(save_path), ext)
    except Exception as e:
        os.remove(save_path)
        raise HTTPException(400, f"Could not extract text: {e}")

    doc = Document(
        id=doc_id,
        project_id=project_id,
        name=file.filename,
        content=text,
        file_path=str(save_path),
        file_type=ext,
        page_count=page_count,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    return {
        "id": doc.id,
        "name": doc.name,
        "file_type": doc.file_type,
        "page_count": doc.page_count,
        "created_at": doc.created_at,
    }


@router.get("/{document_id}")
async def get_document(document_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    return {
        "id": doc.id,
        "name": doc.name,
        "content": doc.content,
        "file_type": doc.file_type,
        "page_count": doc.page_count,
    }


@router.delete("/{document_id}")
async def delete_document(document_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document).where(Document.id == document_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found")
    if doc.file_path and os.path.exists(doc.file_path):
        os.remove(doc.file_path)
    await db.delete(doc)
    await db.commit()
    return {"ok": True}

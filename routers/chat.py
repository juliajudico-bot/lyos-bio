from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from pydantic import BaseModel
from models.database import get_db, Project, Document, Message, gen_id
from services.claude_service import stream_chat
import json

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    project_id: str
    message: str
    use_documents: bool = True


@router.post("/stream")
async def chat_stream(req: ChatRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Project).options(selectinload(Project.documents), selectinload(Project.messages))
        .where(Project.id == req.project_id)
    )
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")

    # Build conversation history
    history = [
        {"role": m.role, "content": m.content}
        for m in sorted(project.messages, key=lambda x: x.created_at)
    ]
    history.append({"role": "user", "content": req.message})

    # Save user message
    user_msg = Message(id=gen_id(), project_id=req.project_id, role="user", content=req.message)
    db.add(user_msg)
    await db.commit()

    documents = []
    if req.use_documents:
        documents = [{"name": d.name, "content": d.content} for d in project.documents]

    collected = []

    async def generate():
        async for chunk in stream_chat(history, documents):
            collected.append(chunk)
            yield f"data: {json.dumps({'text': chunk})}\n\n"

        # Save assistant response
        full_response = "".join(collected)
        async with db.begin():
            asst_msg = Message(
                id=gen_id(), project_id=req.project_id, role="assistant", content=full_response
            )
            db.add(asst_msg)
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/{project_id}/history")
async def get_history(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Message).where(Message.project_id == project_id).order_by(Message.created_at)
    )
    messages = result.scalars().all()
    return [{"id": m.id, "role": m.role, "content": m.content, "created_at": m.created_at} for m in messages]


@router.delete("/{project_id}/history")
async def clear_history(project_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Message).where(Message.project_id == project_id)
    )
    messages = result.scalars().all()
    for m in messages:
        await db.delete(m)
    await db.commit()
    return {"ok": True}

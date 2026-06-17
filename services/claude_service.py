from __future__ import annotations

import json
import os
from typing import AsyncIterator

import google.generativeai as genai

genai.configure(api_key=os.environ.get("GEMINI_API_KEY", ""))

SYSTEM_PROMPT = """You are a specialized AI assistant for Americord, a cord blood and tissue banking company. You help staff review and analyze documents including:
- Cord blood banking consent forms and donor agreements
- FDA/AABB regulatory compliance documents
- Medical collection protocols and procedures
- Patient eligibility criteria
- Insurance and billing documents
- Clinical trial and research agreements
- HIPAA compliance materials

When answering questions about documents:
1. Always cite specific pages and quote verbatim when referencing document content — use the format [Page X, "exact quote"]
2. Never fabricate information — if something isn't in the documents, say so clearly
3. Flag potential compliance concerns, missing required fields, or unusual clauses
4. Be precise and professional in your medical/regulatory language

If no documents are provided, answer based on general knowledge of cord blood banking and medical practice."""


def build_document_context(documents: list[dict]) -> str:
    if not documents:
        return ""
    parts = ["The following documents are available for reference:\n"]
    for doc in documents:
        parts.append(f"--- DOCUMENT: {doc['name']} ---\n{doc['content']}\n--- END OF {doc['name']} ---")
    return "\n\n".join(parts)


def _to_gemini_history(messages: list[dict]) -> tuple[list[dict], str]:
    """Convert OpenAI-style messages to Gemini history + last user message."""
    history = []
    last_user = ""
    for msg in messages:
        role = "user" if msg["role"] == "user" else "model"
        text = msg["content"]
        if msg == messages[-1] and msg["role"] == "user":
            last_user = text
        else:
            history.append({"role": role, "parts": [text]})
    return history, last_user


async def stream_chat(
    messages: list[dict],
    documents: list[dict],
) -> AsyncIterator[str]:
    doc_context = build_document_context(documents)
    system = SYSTEM_PROMPT + (f"\n\n{doc_context}" if doc_context else "")

    history, last_user = _to_gemini_history(messages)

    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=system,
    )
    chat = model.start_chat(history=history)
    response = await chat.send_message_async(last_user, stream=True)
    async for chunk in response:
        if chunk.text:
            yield chunk.text


async def run_workflow(
    workflow_prompt: str,
    documents: list[dict],
) -> str:
    doc_context = build_document_context(documents)
    system = SYSTEM_PROMPT + (f"\n\n{doc_context}" if doc_context else "")

    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=system,
    )
    response = await model.generate_content_async(workflow_prompt)
    return response.text


async def run_tabular_extraction(
    fields: list[str],
    document: dict,
) -> list[dict]:
    fields_list = "\n".join(f"- {f}" for f in fields)
    prompt = f"""Extract the following fields from the document. For each field, provide:
1. The extracted value
2. The exact page number where it was found
3. A verbatim quote from the document supporting the answer

Fields to extract:
{fields_list}

Respond as a JSON array with this structure:
[
  {{
    "field": "field name",
    "value": "extracted value or null if not found",
    "page": "page number or null",
    "quote": "verbatim quote or null"
  }}
]

Only respond with the JSON array, no other text."""

    doc_context = f"--- DOCUMENT: {document['name']} ---\n{document['content']}\n--- END ---"
    system = SYSTEM_PROMPT + f"\n\n{doc_context}"

    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=system,
    )
    response = await model.generate_content_async(prompt)
    text = response.text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text)

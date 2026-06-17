import pdfplumber
import docx
import os
from pathlib import Path

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)


def extract_text_from_pdf(file_path: str) -> tuple[str, int]:
    text_parts = []
    page_count = 0
    with pdfplumber.open(file_path) as pdf:
        page_count = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            if text.strip():
                text_parts.append(f"[Page {i + 1}]\n{text}")
    return "\n\n".join(text_parts), page_count


def extract_text_from_docx(file_path: str) -> tuple[str, int]:
    doc = docx.Document(file_path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs), 1


def extract_text_from_txt(file_path: str) -> tuple[str, int]:
    with open(file_path, "r", errors="ignore") as f:
        return f.read(), 1


def extract_text(file_path: str, file_type: str) -> tuple[str, int]:
    ext = file_type.lower()
    if ext in ("pdf", "application/pdf"):
        return extract_text_from_pdf(file_path)
    elif ext in ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"):
        return extract_text_from_docx(file_path)
    else:
        return extract_text_from_txt(file_path)

"""Context extraction service — URL fetching, PDF parsing, text storage."""

import logging
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def extract_text_from_url(url: str) -> tuple[str, str]:
    """Fetch a URL and return (title, extracted_text)."""
    resp = httpx.get(url, follow_redirects=True, timeout=30,
                     headers={"User-Agent": "Mozilla/5.0 (compatible; Liminal/1.0)"})
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    # Remove script/style
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()

    title = soup.title.string.strip() if soup.title and soup.title.string else url
    text = soup.get_text(separator="\n", strip=True)

    # Truncate very long pages
    if len(text) > 50_000:
        text = text[:50_000] + "\n\n[Truncated — original page was longer]"

    return title, text


def extract_text_from_pdf(file_bytes: bytes, filename: str) -> tuple[str, str]:
    """Extract text from PDF bytes. Returns (title, extracted_text)."""
    import pdfplumber
    import io

    text_parts = []
    with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

    text = "\n\n".join(text_parts)
    if len(text) > 50_000:
        text = text[:50_000] + "\n\n[Truncated — original PDF was longer]"

    title = filename.rsplit(".", 1)[0] if "." in filename else filename
    return title, text


def get_context_text(
    db,
    user_id: str,
    project_id: Optional[int] = None,
    discovery_domain_id: Optional[int] = None,
) -> str:
    """Return formatted context from all attachments for the given scope."""
    from backend.database import ContextAttachment

    query = db.query(ContextAttachment).filter_by(user_id=user_id)

    if project_id:
        # Include project-specific + global (project_id is null)
        query = query.filter(
            (ContextAttachment.project_id == project_id) | (ContextAttachment.project_id == None)
        )
    elif discovery_domain_id:
        query = query.filter(
            (ContextAttachment.discovery_domain_id == discovery_domain_id) | (ContextAttachment.discovery_domain_id == None)
        )
    else:
        # Global only
        query = query.filter(ContextAttachment.project_id == None, ContextAttachment.discovery_domain_id == None)

    attachments = query.all()
    if not attachments:
        return ""

    parts = ["## Attached context\n"]
    for att in attachments:
        label = att.title or att.source_ref or f"({att.source_type})"
        parts.append(f"### {label}")
        parts.append(att.extracted_text)
        parts.append("")

    return "\n".join(parts)

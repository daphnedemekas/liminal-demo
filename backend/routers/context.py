"""Context upload/list/delete endpoints."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db, ContextAttachment, Artifact

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/context", tags=["context"])


class TextUploadRequest(BaseModel):
    user_id: str
    project_id: Optional[int] = None
    discovery_domain_id: Optional[int] = None
    title: Optional[str] = None
    text: str


class UrlUploadRequest(BaseModel):
    user_id: str
    project_id: Optional[int] = None
    discovery_domain_id: Optional[int] = None
    url: str


class AttachmentOut(BaseModel):
    id: int
    source_type: str
    source_ref: Optional[str]
    title: Optional[str]
    created_at: str
    artifact_id: Optional[int] = None

    class Config:
        from_attributes = True


def _maybe_create_summary(db: Session, project_id: Optional[int], title: str, text: str, source_ref: Optional[str] = None) -> Optional[int]:
    """If text is long enough and project_id is provided, create a summary artifact. Returns artifact_id or None."""
    if not project_id or len(text) <= 500:
        return None
    try:
        from backend.services.context_service import generate_summary
        summary = generate_summary(title, text)
        artifact = Artifact(
            project_id=project_id,
            artifact_type="summary",
            title=f"Summary: {title}",
            content={"markdown": summary},
            sources=[source_ref] if source_ref else [],
        )
        db.add(artifact)
        db.commit()
        db.refresh(artifact)
        return artifact.id
    except Exception as e:
        logger.warning(f"Auto-summary failed for '{title}': {e}")
        return None


@router.post("/upload-text", response_model=AttachmentOut)
def upload_text(req: TextUploadRequest, db: Session = Depends(get_db)):
    if not req.text.strip():
        raise HTTPException(400, "Text cannot be empty")

    att = ContextAttachment(
        user_id=req.user_id,
        project_id=req.project_id,
        discovery_domain_id=req.discovery_domain_id,
        source_type="text",
        title=req.title or "Pasted text",
        extracted_text=req.text.strip(),
    )
    db.add(att)
    db.commit()
    db.refresh(att)

    artifact_id = _maybe_create_summary(db, req.project_id, att.title or "Pasted text", req.text.strip())
    return _to_out(att, artifact_id=artifact_id)


@router.post("/upload-url", response_model=AttachmentOut)
def upload_url(req: UrlUploadRequest, db: Session = Depends(get_db)):
    from backend.services.context_service import extract_text_from_url

    try:
        title, text = extract_text_from_url(req.url)
    except Exception as e:
        logger.error(f"URL fetch failed: {e}")
        raise HTTPException(400, f"Could not fetch URL: {e}")

    if not text.strip():
        raise HTTPException(400, "No text content found at URL")

    att = ContextAttachment(
        user_id=req.user_id,
        project_id=req.project_id,
        discovery_domain_id=req.discovery_domain_id,
        source_type="url",
        source_ref=req.url,
        title=title,
        extracted_text=text,
    )
    db.add(att)
    db.commit()
    db.refresh(att)

    artifact_id = _maybe_create_summary(db, req.project_id, title, text, source_ref=req.url)
    return _to_out(att, artifact_id=artifact_id)


@router.post("/upload-pdf", response_model=AttachmentOut)
async def upload_pdf(
    user_id: str = Form(...),
    project_id: Optional[int] = Form(None),
    discovery_domain_id: Optional[int] = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    from backend.services.context_service import extract_text_from_pdf

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "File must be a PDF")

    content = await file.read()
    try:
        title, text = extract_text_from_pdf(content, file.filename)
    except Exception as e:
        logger.error(f"PDF extraction failed: {e}")
        raise HTTPException(400, f"Could not extract text from PDF: {e}")

    if not text.strip():
        raise HTTPException(400, "No text content found in PDF")

    att = ContextAttachment(
        user_id=user_id,
        project_id=project_id,
        discovery_domain_id=discovery_domain_id,
        source_type="pdf",
        source_ref=file.filename,
        title=title,
        extracted_text=text,
    )
    db.add(att)
    db.commit()
    db.refresh(att)

    artifact_id = _maybe_create_summary(db, project_id, title, text, source_ref=file.filename)
    return _to_out(att, artifact_id=artifact_id)


@router.get("/", response_model=list[AttachmentOut])
def list_attachments(
    user_id: str,
    project_id: Optional[int] = None,
    discovery_domain_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    query = db.query(ContextAttachment).filter_by(user_id=user_id)
    if project_id is not None:
        query = query.filter_by(project_id=project_id)
    if discovery_domain_id is not None:
        query = query.filter_by(discovery_domain_id=discovery_domain_id)
    return [_to_out(a) for a in query.order_by(ContextAttachment.created_at.desc()).all()]


@router.delete("/{attachment_id}")
def delete_attachment(attachment_id: int, db: Session = Depends(get_db)):
    att = db.query(ContextAttachment).get(attachment_id)
    if not att:
        raise HTTPException(404, "Attachment not found")
    db.delete(att)
    db.commit()
    return {"status": "deleted"}


def _to_out(att: ContextAttachment, artifact_id: Optional[int] = None) -> dict:
    return {
        "id": att.id,
        "source_type": att.source_type,
        "source_ref": att.source_ref,
        "title": att.title,
        "created_at": att.created_at.isoformat() if att.created_at else "",
        "artifact_id": artifact_id,
    }

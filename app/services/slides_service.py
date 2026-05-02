"""Slides service — CRUD for LabSlide and image upload."""
import os
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.models.profile import LabSlide
from app.schemas.profile import LabSlideCreate, LabSlideUpdate, LabSlideRead

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MIME_TO_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
SLIDER_IMAGES_DIR = Path("storage") / "slider-images"


def list_slides(lab_id: int, db: Session) -> list[LabSlide]:
    """Return active slides ordered by sort_order asc — public."""
    return (
        db.query(LabSlide)
        .filter_by(lab_id=lab_id, is_active=True)
        .order_by(LabSlide.sort_order.asc())
        .all()
    )


def create_slide(lab_id: int, data: LabSlideCreate, db: Session) -> LabSlide:
    slide = LabSlide(lab_id=lab_id, **data.model_dump())
    db.add(slide)
    db.commit()
    db.refresh(slide)
    return slide


def update_slide(lab_id: int, slide_id: int, data: LabSlideUpdate, db: Session) -> LabSlide:
    slide = db.query(LabSlide).filter_by(id=slide_id, lab_id=lab_id).first()
    if not slide:
        raise HTTPException(404, detail="Slide not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(slide, field, value)
    db.commit()
    db.refresh(slide)
    return slide


def delete_slide(lab_id: int, slide_id: int, db: Session) -> None:
    slide = db.query(LabSlide).filter_by(id=slide_id, lab_id=lab_id).first()
    if not slide:
        raise HTTPException(404, detail="Slide not found")
    db.delete(slide)
    db.commit()


def save_slider_image(file_bytes: bytes, original_filename: str, content_type: str) -> str:
    """Validate and save slider image. Returns public URL path."""
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            422,
            detail=f"Unsupported image type. Allowed: jpeg, png, webp, gif"
        )
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(422, detail="File size exceeds 5 MB limit")

    suffix = Path(original_filename).suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        suffix = MIME_TO_EXT[content_type]

    SLIDER_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{suffix}"
    (SLIDER_IMAGES_DIR / filename).write_bytes(file_bytes)
    return f"/storage/slider-images/{filename}"

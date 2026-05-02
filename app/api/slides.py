"""Slides CRUD and image upload endpoints."""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.admin import require_admin
from app.models.auth import User
from app.schemas.profile import LabSlideCreate, LabSlideUpdate, LabSlideRead
from app.services import slides_service

router = APIRouter(tags=["slides"])


@router.get("/{lab_id}/slides", response_model=list[LabSlideRead])
def list_slides(lab_id: int, db: Session = Depends(get_db)):
    """List active slides ordered by sort_order — public."""
    slides = slides_service.list_slides(lab_id, db)
    return [LabSlideRead.model_validate(s) for s in slides]


@router.post("/{lab_id}/slides", response_model=LabSlideRead, status_code=201)
def create_slide(
    lab_id: int,
    data: LabSlideCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Create a new slide — admin only."""
    slide = slides_service.create_slide(lab_id, data, db)
    return LabSlideRead.model_validate(slide)


@router.patch("/{lab_id}/slides/{slide_id}", response_model=LabSlideRead)
def update_slide(
    lab_id: int,
    slide_id: int,
    data: LabSlideUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Update a slide — admin only."""
    slide = slides_service.update_slide(lab_id, slide_id, data, db)
    return LabSlideRead.model_validate(slide)


@router.delete("/{lab_id}/slides/{slide_id}", status_code=204)
def delete_slide(
    lab_id: int,
    slide_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Delete a slide — admin only."""
    slides_service.delete_slide(lab_id, slide_id, db)


@router.post("/{lab_id}/slides/upload-image")
async def upload_slide_image(
    lab_id: int,
    file: UploadFile = File(...),
    _admin: User = Depends(require_admin),
):
    """Upload a slider image — admin only. Returns {url: ...}."""
    content = await file.read()
    url = slides_service.save_slider_image(
        file_bytes=content,
        original_filename=file.filename or "image",
        content_type=file.content_type or "",
    )
    return {"url": url}

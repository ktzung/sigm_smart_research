from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.paper import Paper, PaperDecision
from app.schemas.paper import PaperRead, PaperDecisionUpdate

router = APIRouter()


def _get_paper_or_404(paper_id: int, db: Session) -> Paper:
    paper = db.query(Paper).filter_by(id=paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


@router.get("/{paper_id}", response_model=PaperRead)
def get_paper(paper_id: int, db: Session = Depends(get_db)):
    return _get_paper_or_404(paper_id, db)


@router.patch("/{paper_id}/decision", response_model=PaperRead)
def override_decision(paper_id: int, payload: PaperDecisionUpdate, db: Session = Depends(get_db)):
    """Allow researcher to manually override a screening decision."""
    paper = _get_paper_or_404(paper_id, db)
    if paper.decision:
        paper.decision.label = payload.label
        paper.decision.reason = payload.reason or paper.decision.reason
        paper.decision.overridden = True
        paper.decision.method = "manual"
    else:
        decision = PaperDecision(
            paper_id=paper.id,
            label=payload.label,
            reason=payload.reason,
            method="manual",
            overridden=True,
        )
        db.add(decision)
    db.commit()
    db.refresh(paper)
    return paper


@router.post("/{paper_id}/ingest")
def ingest_paper(paper_id: int, db: Session = Depends(get_db)):
    from app.services.ingestion import ingest_paper as _ingest
    paper = _get_paper_or_404(paper_id, db)
    result = _ingest(paper, db)
    return {"paper_id": paper_id, **result}

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.news import News
from app.middleware.auth import get_current_user, get_optional_user
from app.models.auth import User
from pydantic import BaseModel

router = APIRouter(prefix="/news", tags=["news"])

class NewsCreate(BaseModel):
    title: str
    content: str
    is_public: bool = True

class NewsUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    is_public: bool | None = None

def require_admin(user: User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

@router.get("")
def list_news(db: Session = Depends(get_db), user: User | None = Depends(get_optional_user)):
    # Guests and users see public news. Admin see all.
    if user and user.role == "admin":
        return db.query(News).all()
    return db.query(News).filter_by(is_public=True).all()

@router.get("/{news_id}")
def get_news(news_id: int, db: Session = Depends(get_db)):
    news = db.query(News).filter_by(id=news_id).first()
    if not news:
        raise HTTPException(status_code=404, detail="News not found")
    return news

@router.post("", status_code=201)
def create_news(
    body: NewsCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    news = News(**body.model_dump(), author_id=admin.id)
    db.add(news)
    db.commit()
    db.refresh(news)
    return news

@router.patch("/{news_id}")
def update_news(
    news_id: int,
    body: NewsUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    news = db.query(News).filter_by(id=news_id).first()
    if not news:
        raise HTTPException(status_code=404, detail="News not found")
    
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(news, k, v)
    
    db.commit()
    return news

@router.delete("/{news_id}", status_code=204)
def delete_news(
    news_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    news = db.query(News).filter_by(id=news_id).first()
    if not news:
        raise HTTPException(status_code=404, detail="News not found")
    db.delete(news)
    db.commit()

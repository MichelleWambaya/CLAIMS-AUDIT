import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.db import get_db
from api.models import SavedView, User
from auth.security import get_current_user

router = APIRouter(prefix="/sessions/{session_id}/saved-views", tags=["saved-views"])


class SaveViewRequest(BaseModel):
    name: str
    view_config: dict  # { "time_range_preset": "last_quarter" | "custom", "date_from", "date_to", dims, measures, filters }


@router.post("")
def create_saved_view(session_id: str, body: SaveViewRequest, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)):
    view = SavedView(
        id=uuid.uuid4(), audit_session_id=session_id, created_by=user.id,
        name=body.name, view_config_json=body.view_config,
    )
    db.add(view)
    db.commit()
    return {"id": str(view.id)}


@router.get("")
def list_saved_views(session_id: str, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)):
    views = db.query(SavedView).filter(SavedView.audit_session_id == session_id).all()
    return [{"id": str(v.id), "name": v.name, "view_config": v.view_config_json} for v in views]


@router.get("/{view_id}")
def get_saved_view(session_id: str, view_id: str, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)):
    view = db.query(SavedView).filter(SavedView.id == view_id).first()
    if not view:
        raise HTTPException(status_code=404, detail="Saved view not found")
    return {"id": str(view.id), "name": view.name, "view_config": view.view_config_json}

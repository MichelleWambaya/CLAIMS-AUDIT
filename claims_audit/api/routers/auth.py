from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from api.config import settings
from api.db import get_db
from api.models import User
from auth.security import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    display_name: str = Field(min_length=1)


@router.post("/signup", status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, db: Session = Depends(get_db)):
    """
    Real self-serve account creation — this is the ONLY way accounts get
    created (no admin-only bootstrap URL). The very first account created
    on a fresh database becomes admin automatically, so there's always a
    real path to a first login without a temporary endpoint hit by hand in
    a browser. Every account after that is created as 'analyst'; an admin
    promotes further admins via a direct DB update or (future work) an
    in-app "manage users" admin screen.
    """
    if not settings.ALLOW_SELF_SIGNUP:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Self-signup is disabled on this deployment. Ask an admin to create your account.",
        )

    existing = db.query(User).filter(User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists.")

    is_first_user = db.query(User).count() == 0
    user = User(
        email=body.email,
        display_name=body.display_name,
        role="admin" if is_first_user else "analyst",
        hashed_password=hash_password(body.password),
    )
    db.add(user)
    db.commit()

    token = create_access_token(str(user.id), user.role)
    return {"access_token": token, "token_type": "bearer", "role": user.role, "email": user.email}


@router.post("/login")
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form.username).first()
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    token = create_access_token(str(user.id), user.role)
    return {"access_token": token, "token_type": "bearer", "role": user.role, "email": user.email}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"id": str(user.id), "email": user.email, "display_name": user.display_name, "role": user.role}

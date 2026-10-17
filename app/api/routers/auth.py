from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.adapters.repositories.sql_repository import write_audit
from app.api.deps import get_current_user
from app.database import get_db
from app.domain.models import User
from app.domain.schemas import Token, UserCreate, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    if db.query(User).filter_by(username=payload.username).first():
        raise HTTPException(409, "El usuario ya existe")
    if db.query(User).filter_by(email=payload.email).first():
        raise HTTPException(409, "El email ya existe")
    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        role="user",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    write_audit(db, username=user.username, action="register", resource=f"user:{user.id}")
    return user


@router.post("/login", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter_by(username=form.username).first()
    if user is None or not verify_password(form.password, user.hashed_password):
        write_audit(
            db,
            username=form.username,
            action="login_failed",
            resource="auth",
        )
        raise HTTPException(401, "Credenciales inválidas")
    token = create_access_token({"sub": user.username, "role": user.role})
    write_audit(db, username=user.username, action="login", resource=f"user:{user.id}")
    return {"access_token": token, "token_type": "bearer"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user

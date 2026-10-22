from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import User
from ..schemas import LoginIn, PasswordChangeIn, PreferencesIn, SignupIn, UserOut
from ..security import clear_session_cookie, create_token, current_user, hash_password, set_session_cookie, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=UserOut, status_code=201)
def signup(body: SignupIn, response: Response, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(email=body.email, name=body.name.strip(), password_hash=hash_password(body.password), preferences={})
    db.add(user)
    db.commit()
    set_session_cookie(response, create_token(user.id))
    return user


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    set_session_cookie(response, create_token(user.id))
    return user


@router.post("/logout", status_code=204)
def logout(response: Response):
    clear_session_cookie(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user


@router.post("/password", status_code=204)
def change_password(body: PasswordChangeIn, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    response.status_code = 204
    return response


@router.put("/preferences", response_model=UserOut)
def set_preferences(body: PreferencesIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    allowed = {k: v for k, v in body.preferences.items() if k in {"onboarding", "currency", "default_goal", "country", "city", "budget", "plan_type", "industry"}}
    user.preferences = {**(user.preferences or {}), **allowed}
    db.commit()
    return user


@router.delete("/account", status_code=204)
def delete_account(response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(user)
    db.commit()
    clear_session_cookie(response)
    response.status_code = 204
    return response

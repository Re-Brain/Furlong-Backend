from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from sqlalchemy.orm import Session
from database import get_db
import models.models as models, schemas.auth as auth
from core.auth import (
    hash_password, verify_password, create_access_token, decode_token,
    create_email_verification_token, decode_email_verification_token,
    create_csrf_token, clear_auth_cookies,
    ACCESS_COOKIE_NAME, REFRESH_COOKIE_NAME, CSRF_COOKIE_NAME,
    ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS, DEBUG,
)
from core.refresh_tokens import issue_refresh_token, rotate_refresh_token, revoke_token
from core.cloudinary import delete_image
from core import email

router = APIRouter()


def get_current_user(email: str = Depends(decode_token), db: Session = Depends(get_db)) -> models.User:
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# 1 - API Route
# 2 - The shape of the response (schemas)
@router.post("/register", response_model=auth.RegistrationResponse)
def register(user: auth.VisitorRegister, db: Session = Depends(get_db)):

    existing = db.query(models.User).filter(models.User.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = models.User(
        name=user.name,
        email=user.email,
        hashed_password=hash_password(user.password)
    )

    # Add the user to the database and commit
    db.add(new_user)
    db.commit()

    # Refresh the instance to get the ID and other generated fields
    db.refresh(new_user)

    # No access token here — the account isn't usable until the email is
    # verified. A verification link is sent instead; POST /login is what
    # issues a real token, and it checks email_verified before doing so.
    verification_token = create_email_verification_token(new_user.email)
    email.send_verification_email(new_user, verification_token)

    return {
        "detail": "Registration successful. Please check your email to verify your account before logging in.",
        "email": new_user.email,
    }

@router.post("/register/farmer", response_model=auth.RegistrationResponse)
def register_farmer(data: auth.FarmerRegister, db: Session = Depends(get_db)):

    existing = db.query(models.User).filter(models.User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    new_user = models.User(
        name=data.name,
        email=data.email,
        hashed_password=hash_password(data.password),
        role="farmer"
    )
    db.add(new_user)
    db.flush()  # get new_user.id without committing yet

    new_farm = models.Farm(
        name=data.farm_name,
        owner_id=new_user.id,
        status="draft"  # Farmer still assembling profile/documents before submitting for review
    )
    db.add(new_farm)
    db.commit()
    db.refresh(new_user)

    verification_token = create_email_verification_token(new_user.email)
    email.send_verification_email(new_user, verification_token)

    return {
        "detail": "Registration successful. Please check your email to verify your account before logging in.",
        "email": new_user.email,
    }


@router.post("/verify-email")
def verify_email(data: auth.EmailVerification, db: Session = Depends(get_db)):
    try:
        user_email = decode_email_verification_token(data.token)
    except JWTError:
        raise HTTPException(status_code=400, detail="Invalid or expired verification link")

    user = db.query(models.User).filter(models.User.email == user_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not user.email_verified:
        user.email_verified = True
        db.commit()

    return {"detail": "Email verified successfully"}


@router.get("/me", response_model=auth.UserMe)
def me(email: str = Depends(decode_token), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@router.patch("/me/password")
def update_my_password(
    data: auth.PasswordUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if len(data.new_password) < 8:
        raise HTTPException(status_code=422, detail="New password must be at least 8 characters.")

    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    current_user.hashed_password = hash_password(data.new_password)
    db.commit()
    return {"detail": "Password updated"}


@router.delete("/me", status_code=204)
def delete_my_account(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.farm:
        for horse in current_user.farm.horses:
            for image in horse.images:
                delete_image(image.image_public_id)

    db.delete(current_user)
    db.commit()
    return Response(status_code=204)


@router.post("/login", response_model=auth.LoginResponse)
def login(response: Response, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):

    # Find the user by email (username in form)
    user = db.query(models.User).filter(models.User.email == form.username).first()

    # If user not found or password doesn't match, raise an error
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.email_verified:
        raise HTTPException(status_code=403, detail="Please verify your email before logging in")

    # Create a token for the user
    token = create_access_token({"sub": user.email})
    refresh_token, _ = issue_refresh_token(db, user.id)
    csrf_token = create_csrf_token()
    access_max_age = ACCESS_TOKEN_EXPIRE_MINUTES * 60
    refresh_max_age = REFRESH_TOKEN_EXPIRE_DAYS * 86400

    # HttpOnly so JS can't read it (mitigates XSS token theft); the CSRF
    # cookie is deliberately readable so the frontend can echo it back.
    response.set_cookie(
        ACCESS_COOKIE_NAME, token,
        httponly=True, secure=not DEBUG, samesite="lax", path="/", max_age=access_max_age,
    )
    # Path=/ (not narrower) so /logout can also see it and revoke it
    # server-side -- Path=/refresh would exclude /logout too, since RFC 6265
    # path-scoping only covers paths nested under the cookie's own path.
    response.set_cookie(
        REFRESH_COOKIE_NAME, refresh_token,
        httponly=True, secure=not DEBUG, samesite="lax", path="/", max_age=refresh_max_age,
    )
    # Tied to the refresh token's lifetime, not the access token's -- otherwise
    # it would already be expired by the time a refresh is actually needed.
    response.set_cookie(
        CSRF_COOKIE_NAME, csrf_token,
        httponly=False, secure=not DEBUG, samesite="lax", path="/", max_age=refresh_max_age,
    )

    return {"detail": "Login successful"}


@router.post("/logout")
def logout(response: Response, refresh_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    # No auth dependency: must succeed even if the cookie is already
    # expired/invalid/missing, so the client can always clear its session.
    if refresh_token:
        revoke_token(db, refresh_token)
    clear_auth_cookies(response)
    return {"detail": "Logged out"}


@router.post("/refresh", response_model=auth.LoginResponse)
def refresh(response: Response, refresh_token: str | None = Cookie(default=None), db: Session = Depends(get_db)):
    if not refresh_token:
        failure = JSONResponse(status_code=401, content={"detail": "Missing refresh token"})
        clear_auth_cookies(failure)
        return failure

    old_row = rotate_refresh_token(db, refresh_token)
    if old_row is None:
        failure = JSONResponse(status_code=401, content={"detail": "Invalid refresh token"})
        clear_auth_cookies(failure)
        return failure

    user = db.query(models.User).filter(models.User.id == old_row.user_id).first()
    if not user:
        failure = JSONResponse(status_code=401, content={"detail": "Invalid refresh token"})
        clear_auth_cookies(failure)
        return failure

    new_access_token = create_access_token({"sub": user.email})
    new_refresh_token, _ = issue_refresh_token(db, user.id, family_id=old_row.family_id)
    csrf_token = create_csrf_token()
    access_max_age = ACCESS_TOKEN_EXPIRE_MINUTES * 60
    refresh_max_age = REFRESH_TOKEN_EXPIRE_DAYS * 86400

    response.set_cookie(
        ACCESS_COOKIE_NAME, new_access_token,
        httponly=True, secure=not DEBUG, samesite="lax", path="/", max_age=access_max_age,
    )
    response.set_cookie(
        REFRESH_COOKIE_NAME, new_refresh_token,
        httponly=True, secure=not DEBUG, samesite="lax", path="/", max_age=refresh_max_age,
    )
    response.set_cookie(
        CSRF_COOKIE_NAME, csrf_token,
        httponly=False, secure=not DEBUG, samesite="lax", path="/", max_age=refresh_max_age,
    )

    return {"detail": "Token refreshed"}

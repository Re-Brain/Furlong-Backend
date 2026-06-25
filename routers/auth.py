from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from database import get_db
import models.models as models, schemas.auth as auth
from core.auth import hash_password, verify_password, create_access_token, decode_token

router = APIRouter()


def get_current_user(email: str = Depends(decode_token), db: Session = Depends(get_db)) -> models.User:
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

# 1 - API Route
# 2 - The shape of the response (schemas)
@router.post("/register", response_model=auth.Token)
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

    # Create a token for the new user using the email as the subject
    token = create_access_token({"sub": user.email})

    # token_type "bearer" = whoever holds this token is allowed in (like a concert ticket)
    return {"access_token": token, "token_type": "bearer"}

@router.post("/register/farmer", response_model=auth.Token)
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
        is_active=False  # Phase 1 — pending documentation
    )
    db.add(new_farm)
    db.commit()

    token = create_access_token({"sub": data.email})
    return {"access_token": token, "token_type": "bearer"}


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
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    if len(data.new_password) < 8:
        raise HTTPException(status_code=422, detail="New password must be at least 8 characters.")

    current_user.hashed_password = hash_password(data.new_password)
    db.commit()
    return {"detail": "Password updated"}


@router.delete("/me", status_code=204)
def delete_my_account(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    db.delete(current_user)
    db.commit()
    return Response(status_code=204)


@router.post("/login", response_model=auth.Token)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    
    # Find the user by email (username in form)
    user = db.query(models.User).filter(models.User.email == form.username).first()
    
    # If user not found or password doesn't match, raise an error
    if not user or not verify_password(form.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Create a token for the user
    token = create_access_token({"sub": user.email})

    # token_type "bearer" = whoever holds this token is allowed in (like a concert ticket)
    return {"access_token": token, "token_type": "bearer"}

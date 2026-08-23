from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
import bcrypt
import secrets
from fastapi import Cookie, HTTPException, Response, status
import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "30"))
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

ACCESS_COOKIE_NAME = "access_token"
REFRESH_COOKIE_NAME = "refresh_token"
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"


def clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE_NAME, path="/")
    response.delete_cookie(REFRESH_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))

def create_access_token(data: dict) -> str:

    # Create a JWT token with an expiration time
    to_encode = data.copy() # Pass by reference
    
    # Set the expiration time for the token
    # Use UTC timezone to avoid issues with daylight saving time and time zones
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode["exp"] = expire

    # to_encode = { "sub": user email, "exp": expiration_time }
    #
    # JWT has 3 parts separated by dots: header.payload.signature
    # - header    : metadata (algorithm used). Not secret, anyone can read it.
    # - payload   : your data (sub, exp). Not secret, anyone can decode it.
    # - signature : HMAC_SHA256(header + payload, SECRET_KEY). Only your server can verify it.
    #
    # JWT is NOT encrypted — it is SIGNED. Data is readable but cannot be tampered with.
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def create_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def create_email_verification_token(email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=24)
    # "purpose" stops this from doubling as a working access token if it
    # ever leaks (e.g. in logs) — decode_email_verification_token checks it.
    return jwt.encode({"sub": email, "purpose": "email_verification", "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def decode_email_verification_token(token: str) -> str:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("purpose") != "email_verification":
        raise JWTError("Wrong token type")
    email = payload.get("sub")
    if email is None:
        raise JWTError("Missing subject")
    return email


def decode_token(access_token: str | None = Cookie(default=None)):

    # Create an exception to raise if token is invalid
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )

    if access_token is None:
        raise credentials_exception

    try:

        # Decode the token and extract the email (subject)
        payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        
        # If email is missing, the token is invalid
        if email is None:
            raise credentials_exception
        
        # Return the email (or you could return a user object or other data as needed)
        return email
    
    except JWTError:

        # If any error occurs during decoding (invalid token, expired, wrong signature), raise the credentials exception
        raise credentials_exception

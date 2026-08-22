from routers import auth, horses, farms, bookings, donations, admin
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import engine, get_db
from core.csrf import CSRFMiddleware
import models.models as models
import uvicorn

app = FastAPI()

# Order matters: CORS must be the outermost middleware so it can answer
# preflight OPTIONS requests before they ever reach the CSRF check.
app.add_middleware(CSRFMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Creates tables if they don't exist
# Tells the session which database to talk to.
models.Base.metadata.create_all(bind=engine)

# Depends calls get_db(), grabs the session, and injects it as db

app.include_router(auth.router)
app.include_router(horses.router)
app.include_router(farms.router)
app.include_router(bookings.router)
app.include_router(donations.router)
app.include_router(admin.router)

@app.get("/")
def read_root():
    return {"message": "Hello, World!"}

if __name__ == "__main__":
    uvicorn.run("main:app", reload=True)
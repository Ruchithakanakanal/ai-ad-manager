from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from backend.auth_security import (
    create_access_token,
    verify_password,
    decode_token,
    hash_password
)

router = APIRouter(prefix="/auth", tags=["auth"])

# ─── FAKE DB (replace later with real DB) ───
fake_users = {
    "admin@example.com": {
        "password": hash_password("admin123"),
        "role": "admin"
    },
    "analyst@example.com": {
        "password": hash_password("analyst123"),
        "role": "analyst"
    },
    "viewer@example.com": {
        "password": hash_password("viewer123"),
        "role": "viewer"
    },
}

# ─── REQUEST MODEL ─────────────────────
class LoginRequest(BaseModel):
    username: str
    password: str

# ─── LOGIN ──────────────────────────────
@router.post("/login")
def login(data: LoginRequest):

    user = fake_users.get(data.username)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(data.password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token({
        "sub": data.username,
        "role": user["role"]
    })

    return {
        "access_token": token,
        "token_type": "bearer"
    }

# ─── GET CURRENT USER ──────────────────
@router.get("/me")
def me(token: str):

    payload = decode_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    return {
        "user": payload["sub"],
        "role": payload["role"]
    }

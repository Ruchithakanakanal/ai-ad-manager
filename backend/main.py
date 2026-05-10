"""
backend/main.py — FastAPI application entry point (UPGRADED SECURE VERSION)
"""

import logging
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.routes.auth import router as auth_router
from backend.routes.campaign_routes import router as campaigns_router
from backend.routes.dashboard import router as dashboard_router
from backend.routes.alerts import router as alerts_router
from backend.routes.campaign_routes import router as legacy_campaign_router

from auth_security import decode_token



logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────

app = FastAPI(
    title="AI Facebook Campaign Optimization API",
    description="AI-powered campaign optimization platform",
    version="2.0.0",
)

# ─────────────────────────────────────────────
# PUBLIC ROUTES
# ─────────────────────────────────────────────

PUBLIC_PATHS = {
    "/",
    "/auth/login",
    "/docs",
    "/openapi.json",
    "/redoc",
}

# ─────────────────────────────────────────────
# JWT MIDDLEWARE (CLEAN + SAFE)
# ─────────────────────────────────────────────

class JWTMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):

        # Allow public routes
        if request.url.path in PUBLIC_PATHS or request.method == "OPTIONS":
            return await call_next(request)

        auth_header = request.headers.get("Authorization")

        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Missing token"},
            )

        token = auth_header.replace("Bearer ", "").strip()

        payload = decode_token(token)

        if not payload:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Invalid or expired token"},
            )

        # attach user safely
        request.state.user = payload
        request.state.role = payload.get("role", "viewer")

        return await call_next(request)


app.add_middleware(JWTMiddleware)

# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.get("/")
def home():
    return {
        "message": "AI Campaign Optimization API Running",
        "status": "healthy"
    }

# Auth (PUBLIC)
app.include_router(auth_router)

# Protected modules
app.include_router(campaigns_router)
app.include_router(dashboard_router)
app.include_router(alerts_router)
app.include_router(legacy_campaign_router)
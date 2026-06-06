from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

import boto3
import json
import re
import requests
import os
from pathlib import Path
from urllib.parse import urlencode

from dotenv import load_dotenv

# Load environment variables before importing modules that read DATABASE_URL.
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

from backend.auth_security import create_access_token, decode_token
from backend.database import engine, get_db, Base
from backend.models.ad_models import Campaign
from backend.models.facebook_connection import FacebookConnection
from backend.services import facebook_oauth
from backend.services.facebook_adset_service import create_adset
from backend.services.facebook_creative_service import create_creative
from backend.services.facebook_service import create_facebook_campaign

# ---------------------------------------------------
# LOAD ENV
# ---------------------------------------------------

# ---------------------------------------------------
# FACEBOOK CONFIG
# ---------------------------------------------------

FACEBOOK_ACCESS_TOKEN = (os.getenv("FACEBOOK_ACCESS_TOKEN") or "").strip()

FACEBOOK_AD_ACCOUNT_ID = (os.getenv("FACEBOOK_AD_ACCOUNT_ID") or "").strip()

# Frontend base URL the OAuth callback redirects back to after connecting.
FRONTEND_URL = (
    os.getenv("FRONTEND_URL")
    or "https://d11f0u0whqm0je.cloudfront.net"
).rstrip("/")

# Optional explicit OAuth redirect (must be registered in the Facebook app).
# When unset, it is derived from the incoming request's base URL.
FACEBOOK_OAUTH_REDIRECT_URI = (os.getenv("FACEBOOK_OAUTH_REDIRECT_URI") or "").strip()


def _oauth_redirect_uri(request: Request) -> str:
    if FACEBOOK_OAUTH_REDIRECT_URI:
        return FACEBOOK_OAUTH_REDIRECT_URI
    base = str(request.base_url).rstrip("/")
    return f"{base}/facebook/callback"


def get_current_identity(request: Request) -> str:
    """Extract the logged-in user's identity from the Bearer JWT."""
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")

    payload = decode_token(auth_header.split(" ", 1)[1].strip())

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    identity = (payload.get("sub") or payload.get("email") or "").strip().lower()

    if not identity:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    return identity


def resolve_fb_credentials(request: Request, db: Session) -> tuple[str, str]:
    """Return (access_token, ad_account_id) for the current request.

    Prefers the logged-in user's connected Facebook account; falls back to
    the server-wide env credentials when the user has not connected one.
    """
    try:
        identity = get_current_identity(request)
    except HTTPException:
        identity = None

    if identity:
        conn = (
            db.query(FacebookConnection)
            .filter(FacebookConnection.user_key == identity)
            .first()
        )
        if conn and conn.access_token:
            return conn.access_token, (conn.ad_account_id or FACEBOOK_AD_ACCOUNT_ID)

    return FACEBOOK_ACCESS_TOKEN, FACEBOOK_AD_ACCOUNT_ID

# ---------------------------------------------------
# LOGIN MODEL
# ---------------------------------------------------

class LoginRequest(BaseModel):
    username: str | None = None
    email: str | None = None
    password: str

# ---------------------------------------------------
# DEMO USERS
# ---------------------------------------------------

DEMO_USERS = {

    "admin@example.com": {
        "passwords": {"123456", "admin123"},
        "role": "admin"
    },

    "ruchitha": {
        "passwords": {"12345", "123456"},
        "role": "admin"
    },
}

# ---------------------------------------------------
# FASTAPI APP
# ---------------------------------------------------

app = FastAPI(
    title="AI Campaign Optimization System",
    description="AI-powered Facebook Campaign Manager",
    version="1.0"
)

# ---------------------------------------------------
# DATABASE
# ---------------------------------------------------

Base.metadata.create_all(bind=engine)

# ---------------------------------------------------
# CORS
# ---------------------------------------------------



app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # later replace with your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



# ---------------------------------------------------
# AWS BEDROCK CLIENT
# ---------------------------------------------------

client = boto3.client(
    "bedrock-runtime",
    region_name="us-east-1"
)

# ---------------------------------------------------
# REQUEST MODEL
# ---------------------------------------------------

class CampaignRequest(BaseModel):
    product: str
    goal: str = "Increase sales"
    tone: str = "Exciting"


class PublishFacebookRequest(BaseModel):
    name: str
    status: str = "PAUSED"
    is_adset_budget_sharing_enabled: bool = False


def build_local_campaign(product: str, goal: str, tone: str) -> dict:
    product_name = product.strip() or "Product"
    goal_text = goal.strip() or "Increase sales"
    tone_text = tone.strip() or "Exciting"

    return {
        "audience": (
            "Small business customers, local buyers, and social media users "
            "who are likely to engage with practical, value-focused offers"
        ),
        "platform": "Facebook and Instagram",
        "budget": "$500 - $2,000 per month",
        "timing": "Evenings and weekends when customers are most active online",
        "strategy": (
            f"Use {tone_text.lower()} short-form creatives for {product_name}, "
            f"optimize the campaign toward '{goal_text}', retarget engaged users, "
            "and test two ad copies to improve click-through rate."
        ),
        "performance_score": 82,
        "headline": f"Discover {product_name} Today",
        "primary_text": (
            f"Make {product_name} part of your next smart choice. Built for "
            "customers who want quality, value, and a simple buying experience."
        ),
        "call_to_action": "Shop Now",
    }

# ---------------------------------------------------
# HOME ROUTE
# ---------------------------------------------------

@app.get("/")
def home():

    return {
        "message": "✅ AI Campaign Backend Running"
    }

# ---------------------------------------------------
# LOGIN API
# ---------------------------------------------------

@app.post("/login")
def login(data: LoginRequest):

    identifier = (
        data.username or
        data.email or
        ""
    ).strip().lower()

    password = data.password.strip()

    user = DEMO_USERS.get(identifier)

    if not user or password not in user["passwords"]:

        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    token = create_access_token({
        "sub": identifier,
        "email": identifier if "@" in identifier else None,
        "role": user["role"],
    })

    return {
        "access_token": token,
        "token_type": "bearer"
    }

# ---------------------------------------------------
# GENERATE AI CAMPAIGN
# ---------------------------------------------------

@app.post("/generate-ad")
def generate_ad(
    request: CampaignRequest,
    db: Session = Depends(get_db)
):

    try:

        prompt = f"""
        You are an expert AI marketing strategist.

        Product: {request.product}
        Campaign Goal: {request.goal}
        Tone: {request.tone}

        Perform ALL the following tasks:

        1. Identify target audience
        2. Recommend best platform
        3. Suggest campaign budget
        4. Suggest posting time
        5. Create marketing strategy
        6. Generate advertisement
        7. Give performance score out of 100

        Return ONLY valid JSON.

        {{
          "audience": "...",
          "platform": "...",
          "budget": "...",
          "timing": "...",
          "strategy": "...",
          "performance_score": 0,
          "headline": "...",
          "primary_text": "...",
          "call_to_action": "..."
        }}
        """

        body = {

            "anthropic_version": "bedrock-2023-05-31",

            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],

            "max_tokens": 500
        }

        try:
            response = client.invoke_model(
                modelId="anthropic.claude-3-sonnet-20240229-v1:0",
                body=json.dumps(body)
            )

            result = json.loads(
                response["body"].read()
            )

            output_text = result["content"][0]["text"]

            match = re.search(
                r"\{.*\}",
                output_text,
                re.DOTALL
            )

            if not match:
                campaign_data = build_local_campaign(
                    request.product,
                    request.goal,
                    request.tone
                )
            else:
                campaign_data = json.loads(
                    match.group()
                )

        except Exception:
            campaign_data = build_local_campaign(
                request.product,
                request.goal,
                request.tone
            )

        # SAVE TO DATABASE

        new_campaign = Campaign(
            product=request.product,
            audience=campaign_data.get("audience"),
            platform=campaign_data.get("platform"),
            budget=campaign_data.get("budget"),
            strategy=campaign_data.get("strategy"),
            performance_score=campaign_data.get("performance_score"),
            headline=campaign_data.get("headline"),
            primary_text=campaign_data.get("primary_text"),
            call_to_action=campaign_data.get("call_to_action")
        )

        db.add(new_campaign)

        db.commit()

        db.refresh(new_campaign)

        return {
            "status": "success",
            "id": new_campaign.id,
            "product": request.product,
            "audience": campaign_data.get("audience"),
            "platform": campaign_data.get("platform"),
            "budget": campaign_data.get("budget"),
            "timing": campaign_data.get("timing"),
            "strategy": campaign_data.get("strategy"),
            "performance_score": campaign_data.get("performance_score"),
            "headline": campaign_data.get("headline"),
            "primary_text": campaign_data.get("primary_text"),
            "call_to_action": campaign_data.get("call_to_action"),
            "campaign": campaign_data
        }

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# ---------------------------------------------------
# GET ALL CAMPAIGNS
# ---------------------------------------------------

@app.get("/campaigns")
def get_campaigns(
    db: Session = Depends(get_db)
):

    campaigns = db.query(Campaign).all()

    return campaigns

# ---------------------------------------------------
# PUBLISH FACEBOOK CAMPAIGN
# ---------------------------------------------------

@app.post("/publish-facebook")
def publish_facebook(request: PublishFacebookRequest):

    result = create_facebook_campaign(
        request.name,
        request.status,
        request.is_adset_budget_sharing_enabled
    )

    return {
        "status": "success",
        "facebook_response": result
    }

# ---------------------------------------------------
# CONNECT FACEBOOK — PER-USER OAUTH
# ---------------------------------------------------


def _serialize_connection(conn: FacebookConnection) -> dict:
    try:
        ad_accounts = json.loads(conn.ad_accounts) if conn.ad_accounts else []
    except (ValueError, TypeError):
        ad_accounts = []

    return {
        "connected": True,
        "fb_user_name": conn.fb_user_name,
        "fb_user_id": conn.fb_user_id,
        "ad_account_id": conn.ad_account_id,
        "ad_accounts": ad_accounts,
    }


@app.get("/facebook/status")
def facebook_status(request: Request, db: Session = Depends(get_db)):
    """Return the current user's Facebook connection status."""
    identity = get_current_identity(request)

    conn = (
        db.query(FacebookConnection)
        .filter(FacebookConnection.user_key == identity)
        .first()
    )

    if not conn:
        return {"connected": False, "configured": facebook_oauth.is_configured()}

    result = _serialize_connection(conn)
    result["configured"] = facebook_oauth.is_configured()
    return result


@app.get("/facebook/oauth-url")
def facebook_oauth_url(request: Request):
    """Build the Facebook login URL for the current user to authorize."""
    identity = get_current_identity(request)

    if not facebook_oauth.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Facebook app is not configured. Set FACEBOOK_APP_ID and "
                   "FACEBOOK_APP_SECRET on the backend.",
        )

    # The state is a short-lived signed token tying the callback to this user.
    state = create_access_token({"sub": identity, "purpose": "fb_oauth"})

    url = facebook_oauth.build_login_url(state, _oauth_redirect_uri(request))

    return {"url": url, "configured": True}


@app.get("/facebook/callback")
def facebook_callback(
    request: Request,
    db: Session = Depends(get_db),
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
):
    """OAuth redirect target. Exchanges the code and stores the user's token."""

    def _redirect(status_value: str, message: str = "") -> RedirectResponse:
        query = {"fb": status_value}
        if message:
            query["message"] = message
        return RedirectResponse(
            url=f"{FRONTEND_URL}/dashboard/connect-facebook?{urlencode(query)}"
        )

    if error:
        return _redirect("error", error_description or error)

    if not code or not state:
        return _redirect("error", "Missing authorization code")

    payload = decode_token(state)
    if not payload or payload.get("purpose") != "fb_oauth":
        return _redirect("error", "Invalid or expired login state")

    identity = (payload.get("sub") or "").strip().lower()
    if not identity:
        return _redirect("error", "Invalid login state")

    try:
        redirect_uri = _oauth_redirect_uri(request)
        short_token = facebook_oauth.exchange_code_for_token(code, redirect_uri)
        access_token = facebook_oauth.get_long_lived_token(short_token)
        profile = facebook_oauth.fetch_user_profile(access_token)
        ad_accounts = facebook_oauth.fetch_ad_accounts(access_token)
    except Exception as exc:  # noqa: BLE001 - surface a friendly message to UI
        return _redirect("error", str(exc))

    default_ad_account = ad_accounts[0]["id"] if ad_accounts else FACEBOOK_AD_ACCOUNT_ID

    conn = (
        db.query(FacebookConnection)
        .filter(FacebookConnection.user_key == identity)
        .first()
    )

    if not conn:
        conn = FacebookConnection(user_key=identity)
        db.add(conn)

    conn.fb_user_id = profile.get("id")
    conn.fb_user_name = profile.get("name")
    conn.access_token = access_token
    conn.ad_account_id = conn.ad_account_id or default_ad_account
    conn.ad_accounts = json.dumps(ad_accounts)

    db.commit()

    return _redirect("connected")


class SelectAdAccountRequest(BaseModel):
    ad_account_id: str


@app.post("/facebook/select-ad-account")
def facebook_select_ad_account(
    payload: SelectAdAccountRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """Set which connected ad account the user wants to use."""
    identity = get_current_identity(request)

    conn = (
        db.query(FacebookConnection)
        .filter(FacebookConnection.user_key == identity)
        .first()
    )

    if not conn:
        raise HTTPException(status_code=404, detail="No Facebook account connected")

    conn.ad_account_id = payload.ad_account_id.strip()
    db.commit()

    return _serialize_connection(conn)


@app.post("/facebook/disconnect")
def facebook_disconnect(request: Request, db: Session = Depends(get_db)):
    """Remove the current user's stored Facebook connection."""
    identity = get_current_identity(request)

    conn = (
        db.query(FacebookConnection)
        .filter(FacebookConnection.user_key == identity)
        .first()
    )

    if conn:
        db.delete(conn)
        db.commit()

    return {"connected": False}


# ---------------------------------------------------
# GET FACEBOOK CAMPAIGNS
# ---------------------------------------------------

@app.get("/facebook-campaigns")
def get_facebook_campaigns(request: Request, db: Session = Depends(get_db)):

    try:

        access_token, ad_account_id = resolve_fb_credentials(request, db)

        if not access_token or not ad_account_id:
            raise HTTPException(
                status_code=400,
                detail="No Facebook account connected. Use Connect Facebook first.",
            )

        url = f"https://graph.facebook.com/v22.0/{ad_account_id}/campaigns"

        params = {
            "access_token": access_token
        }

        response = requests.get(
            url,
            params=params
        )

        return response.json()

    except HTTPException:
        raise

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# ---------------------------------------------------
# CREATE FACEBOOK CAMPAIGN DIRECTLY
# ---------------------------------------------------

# ---------------------------------------------------
# CREATE FACEBOOK CAMPAIGN DIRECTLY
# ---------------------------------------------------

@app.post("/create-facebook-campaign")
def create_fb_campaign(
    request: PublishFacebookRequest,
    http_request: Request,
    db: Session = Depends(get_db),
):

    try:

        access_token, ad_account_id = resolve_fb_credentials(http_request, db)

        if not access_token or not ad_account_id:
            raise HTTPException(
                status_code=400,
                detail="No Facebook account connected. Use Connect Facebook first.",
            )

        url = f"https://graph.facebook.com/v22.0/{ad_account_id}/campaigns"

        payload = {

            "name": request.name,

            "objective": "OUTCOME_TRAFFIC",

            "buying_type": "AUCTION",

            "status": request.status,

            "special_ad_categories": '[]',

            "is_adset_budget_sharing_enabled": (
                "true" if request.is_adset_budget_sharing_enabled else "false"
            ),

            "access_token": access_token
        }

        response = requests.post(
            url,
            data=payload
        )

        result = response.json()

        if not response.ok:
            raise HTTPException(
                status_code=response.status_code,
                detail=result
            )

        return {
            "status": "success",
            "facebook_response": result
        }

    except HTTPException:
        raise

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )

# ---------------------------------------------------
# CREATE FACEBOOK ADSET
# ---------------------------------------------------

@app.post("/create-adset/{campaign_id}")
def create_fb_adset(campaign_id: str):

    result = create_adset(campaign_id)

    return result



# ---------------------------------------------------
# CREATE FACEBOOK CREATIVE
# ---------------------------------------------------

@app.post("/create-creative")
def create_fb_creative():

    result = create_creative()

    return result


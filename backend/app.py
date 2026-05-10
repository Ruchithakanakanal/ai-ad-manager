from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session
from services.facebook_adset_service import create_adset
from services.facebook_creative_service import create_creative

import boto3
import json
import re
import requests
import os

from dotenv import load_dotenv

from auth_security import create_access_token
from database import engine, get_db, Base
from models.ad_models import Campaign
from services.facebook_service import create_facebook_campaign

# ---------------------------------------------------
# LOAD ENV
# ---------------------------------------------------

load_dotenv(dotenv_path="backend/.env")

# ---------------------------------------------------
# FACEBOOK CONFIG
# ---------------------------------------------------

FACEBOOK_ACCESS_TOKEN = (os.getenv("FACEBOOK_ACCESS_TOKEN") or "").strip()

FACEBOOK_AD_ACCOUNT_ID = (os.getenv("FACEBOOK_AD_ACCOUNT_ID") or "").strip()

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

            raise HTTPException(
                status_code=500,
                detail="No valid JSON returned"
            )

        campaign_data = json.loads(
            match.group()
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
# GET FACEBOOK CAMPAIGNS
# ---------------------------------------------------

@app.get("/facebook-campaigns")
def get_facebook_campaigns():

    try:

        url = f"https://graph.facebook.com/v22.0/{FACEBOOK_AD_ACCOUNT_ID}/campaigns"

        params = {
            "access_token": FACEBOOK_ACCESS_TOKEN
        }

        response = requests.get(
            url,
            params=params
        )

        return response.json()

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
def create_fb_campaign(request: PublishFacebookRequest):

    try:

        url = f"https://graph.facebook.com/v22.0/{FACEBOOK_AD_ACCOUNT_ID}/campaigns"

        payload = {

            "name": request.name,

            "objective": "OUTCOME_TRAFFIC",

            "buying_type": "AUCTION",

            "status": request.status,

            "special_ad_categories": '[]',

            "is_adset_budget_sharing_enabled": (
                "true" if request.is_adset_budget_sharing_enabled else "false"
            ),

            "access_token": FACEBOOK_ACCESS_TOKEN
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


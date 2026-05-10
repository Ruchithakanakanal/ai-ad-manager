import requests
import os

from dotenv import load_dotenv
from fastapi import HTTPException

# ------------------------------------------------
# LOAD ENV FILE
# ------------------------------------------------

load_dotenv(dotenv_path="backend/.env")

# ------------------------------------------------
# ENV VARIABLES
# ------------------------------------------------

ACCESS_TOKEN = os.getenv("FACEBOOK_ACCESS_TOKEN")

AD_ACCOUNT_ID = os.getenv("FACEBOOK_AD_ACCOUNT_ID")

# ------------------------------------------------
# CREATE FACEBOOK CAMPAIGN
# ------------------------------------------------

def create_facebook_campaign(
    name: str,
    status: str = "PAUSED",
    is_adset_budget_sharing_enabled: bool = False,
):
    if not ACCESS_TOKEN or not AD_ACCOUNT_ID:
        raise HTTPException(
            status_code=500,
            detail="Facebook access token or ad account id is missing in backend/.env",
        )

    url = f"https://graph.facebook.com/v22.0/{AD_ACCOUNT_ID}/campaigns"

    payload = {

        "name": name,

        "objective": "OUTCOME_TRAFFIC",

        "buying_type": "AUCTION",

        "status": status,

        "special_ad_categories": '[]',

        "is_adset_budget_sharing_enabled": (
            "true" if is_adset_budget_sharing_enabled else "false"
        ),

        "access_token": ACCESS_TOKEN
    }

    response = requests.post(
        url,
        data=payload
    )

    result = response.json()

    if not response.ok:
        raise HTTPException(
            status_code=response.status_code,
            detail=result,
        )

    return result

import requests
import os

from dotenv import load_dotenv

# ---------------------------------------------------
# LOAD ENV
# ---------------------------------------------------

load_dotenv(dotenv_path="backend/.env")

ACCESS_TOKEN = (
    os.getenv("FACEBOOK_ACCESS_TOKEN") or ""
).strip()

AD_ACCOUNT_ID = (
    os.getenv("FACEBOOK_AD_ACCOUNT_ID") or ""
).strip()

# ---------------------------------------------------
# CREATE FACEBOOK ADSET
# ---------------------------------------------------

def create_adset(campaign_id):

    url = f"https://graph.facebook.com/v22.0/{AD_ACCOUNT_ID}/adsets"

    targeting = {
        "geo_locations": {
            "countries": ["IN"]
        }
    }

    
    
    payload = {

        "name": "AI Ad Set",

        "campaign_id": campaign_id,

        "daily_budget": "10000",

        "billing_event": "IMPRESSIONS",

        "optimization_goal": "REACH",

        "bid_amount": "5000",

        "targeting": str(targeting).replace(
            "'",
            '"'
        ),

        "status": "PAUSED",

        "access_token": ACCESS_TOKEN
    }
    
    
  

    response = requests.post(
        url,
        params=payload
    )

    return response.json()
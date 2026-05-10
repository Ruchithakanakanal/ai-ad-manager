import requests
import os

from dotenv import load_dotenv

load_dotenv(dotenv_path="backend/.env")

ACCESS_TOKEN = (
    os.getenv("FACEBOOK_ACCESS_TOKEN") or ""
).strip()

AD_ACCOUNT_ID = (
    os.getenv("FACEBOOK_AD_ACCOUNT_ID") or ""
).strip()

PAGE_ID = (
    os.getenv("FACEBOOK_PAGE_ID") or ""
).strip()

def create_creative():

    url = f"https://graph.facebook.com/v22.0/{AD_ACCOUNT_ID}/adcreatives"

    payload = {

        "name": "AI Creative",

        "object_story_spec": {

            "page_id": PAGE_ID,

            "link_data": {

                "link": "https://example.com",

                "message": "AI powered smart watch for modern lifestyle.",

                "name": "AI Smart Watch",

                "description": "Track fitness and productivity.",

                "call_to_action": {
                    "type": "LEARN_MORE",
                    "value": {
                        "link": "https://example.com"
                    }
                }
            }
        }
    }

    params = {
        "access_token": ACCESS_TOKEN
    }

    response = requests.post(
        url,
        json=payload,
        params=params
    )

    return response.json()
import json
import logging
import os

import boto3
from dotenv import load_dotenv

# Load env variables
load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")

logger = logging.getLogger(__name__)

# Bedrock configuration
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
BEDROCK_REGION = os.environ.get("BEDROCK_REGION", "us-east-1")


def generate_ad(business, location, goal):

    try:
        from google import genai  # lazy import — only needed at runtime

        gemini_client = genai.Client(api_key=API_KEY)

        prompt = f"""
        Create a professional advertisement.

        Business: {business}
        Location: {location}
        Goal: {goal}

        Generate:
        - Catchy headline
        - Ad copy
        - Call to action
        """

        response = gemini_client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
        )

        print("GEMINI RESPONSE:", response.text)

        return response.text

    except Exception as e:
        print("ERROR:", e)
        return f"Error generating advertisement: {str(e)}"


def generate_ad_copy_from_recommendation(rec) -> str:
    """
    Call AWS Bedrock (Claude) to generate human-readable ad copy from a Recommendation.

    Parameters
    ----------
    rec : Recommendation
        The recommendation containing campaign context.

    Returns
    -------
    str
        Generated ad copy string, or a fallback string if Bedrock is unavailable.
    """
    prompt = (
        f"You are an expert digital marketing copywriter. "
        f"Generate a concise, compelling ad copy suggestion based on the following campaign recommendation:\n\n"
        f"Campaign ID: {rec.campaign_id}\n"
        f"Optimization Goal: {rec.goal.value}\n"
        f"Recommended Action: {rec.action}\n"
        f"Current Value: {rec.current_value:.4f}\n"
        f"Suggested Value: {rec.suggested_value:.4f}\n"
        f"Reasoning: {rec.reasoning}\n\n"
        f"Write a short, actionable ad copy (2-3 sentences) that reflects this optimization strategy."
    )

    try:
        bedrock = boto3.client("bedrock-runtime", region_name=BEDROCK_REGION)

        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 256,
            "messages": [
                {"role": "user", "content": prompt}
            ],
        })

        response = bedrock.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            contentType="application/json",
            accept="application/json",
            body=body,
        )

        result = json.loads(response["body"].read())
        ad_copy = result["content"][0]["text"].strip()
        logger.info("Bedrock ad copy generated for campaign %s", rec.campaign_id)
        return ad_copy

    except Exception as exc:
        logger.warning(
            "Bedrock ad copy generation failed for campaign %s: %s — using fallback.",
            rec.campaign_id,
            exc,
        )
        return f"Optimize your {rec.goal.value} campaign: {rec.action} to improve performance."

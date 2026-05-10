from openai import OpenAI
import os

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def generate_strategy(business, location, goal):

    prompt = f"""
    You are a senior digital marketing strategist.

    Create a marketing strategy for:

    Business: {business}
    Location: {location}
    Goal: {goal}

    Return:
    1. Target audience
    2. Marketing tone
    3. Best campaign objective
    4. Ad angle
    5. Suggested platforms
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content
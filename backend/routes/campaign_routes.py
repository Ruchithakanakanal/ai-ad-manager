from fastapi import APIRouter
from pydantic import BaseModel
from backend.services.ai_engine import generate_ad

router = APIRouter()


# -------- Request Schema (VERY IMPORTANT) --------
class AdRequest(BaseModel):
    business: str
    location: str
    goal: str


# -------- API Endpoint --------
@router.post("/generate-ad")
def create_ad(data: AdRequest):

    # Debug print (see request in terminal)
    print("REQUEST RECEIVED:", data)

    ad = generate_ad(
        data.business,
        data.location,
        data.goal
    )

    return {"ad": ad}
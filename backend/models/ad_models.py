from pydantic import BaseModel
from typing import Optional
from enum import Enum
from sqlalchemy import Column, Integer, String, Float
from backend.database import Base

class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(Integer, primary_key=True, index=True)

    product = Column(String)
    audience = Column(String)
    platform = Column(String)
    budget = Column(String)
    strategy = Column(String)

    performance_score = Column(Float)

    headline = Column(String)
    primary_text = Column(String)
    call_to_action = Column(String)

class OptimizationGoal(str, Enum):
    CTR = "CTR"
    CPC = "CPC"
    CONVERSION = "CONVERSION"
    ROAS = "ROAS"


class CampaignMetrics(BaseModel):
    campaign_id: str
    campaign_name: str
    date: str                   # ISO 8601 YYYY-MM-DD
    impressions: int
    clicks: int
    spend: float                # USD
    conversions: int
    ctr: float                  # clicks / impressions
    cpc: float                  # spend / clicks
    roas: float                 # revenue / spend
    reach: int
    frequency: float


class Recommendation(BaseModel):
    recommendation_id: str
    campaign_id: str
    generated_at: str           # ISO 8601 timestamp
    goal: OptimizationGoal
    action: str                 # e.g. "increase_bid", "narrow_audience"
    current_value: float
    suggested_value: float
    confidence_score: float     # 0.0 - 1.0
    reasoning: str
    applied: bool = False


class AlertConfig(BaseModel):
    user_id: str
    campaign_id: str
    metric: str                 # e.g. "ctr", "spend"
    threshold: float
    direction: str              # "below" | "above"
    sns_topic_arn: str


class AdRequest(BaseModel):
    business: str
    location: str
    goal: str
    campaign_id: Optional[str] = None
    optimization_goal: Optional[OptimizationGoal] = None

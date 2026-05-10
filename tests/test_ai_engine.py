"""
Unit tests for generate_ad_copy_from_recommendation in backend/services/ai_engine.py
Requirements: 5.9
"""
import io
import json
from unittest.mock import MagicMock, patch

import pytest

from backend.models.ad_models import OptimizationGoal, Recommendation
from backend.services.ai_engine import generate_ad_copy_from_recommendation

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_rec() -> Recommendation:
    return Recommendation(
        recommendation_id="rec-001",
        campaign_id="camp-123",
        generated_at="2024-01-15T10:00:00Z",
        goal=OptimizationGoal.CTR,
        action="increase_bid",
        current_value=0.05,
        suggested_value=0.07,
        confidence_score=0.85,
        reasoning="Low CTR detected; increasing bid may improve ad placement.",
        applied=False,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_generate_ad_copy_success(sample_rec):
    """Bedrock returns a valid response — the ad copy text is returned."""
    mock_bedrock = MagicMock()
    mock_response = {
        "body": io.BytesIO(
            json.dumps({"content": [{"text": "Buy now!"}]}).encode()
        )
    }
    mock_bedrock.invoke_model.return_value = mock_response

    with patch("backend.services.ai_engine.boto3.client", return_value=mock_bedrock):
        result = generate_ad_copy_from_recommendation(sample_rec)

    assert result == "Buy now!"
    mock_bedrock.invoke_model.assert_called_once()


def test_generate_ad_copy_bedrock_unavailable(sample_rec):
    """When boto3.client raises, the function returns a fallback string."""
    with patch(
        "backend.services.ai_engine.boto3.client",
        side_effect=Exception("Bedrock unavailable"),
    ):
        result = generate_ad_copy_from_recommendation(sample_rec)

    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_ad_copy_fallback_contains_goal_and_action(sample_rec):
    """Fallback string must contain the goal value and the action."""
    with patch(
        "backend.services.ai_engine.boto3.client",
        side_effect=Exception("Bedrock unavailable"),
    ):
        result = generate_ad_copy_from_recommendation(sample_rec)

    assert sample_rec.goal.value in result
    assert sample_rec.action in result

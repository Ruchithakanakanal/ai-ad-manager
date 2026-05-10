"""
Property-based tests for the optimizer recommendation generation service.

Property 2: Output recommendation count always equals input metrics count
            Validates: Requirements 5.1

Property 3: Confidence score is always in [0, 1] for any prediction input
            Validates: Requirements 5.3

Property 4: suggested_value never deviates more than 50% from current_value
            Validates: Requirements 5.2
"""

from unittest.mock import patch

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.models.ad_models import CampaignMetrics, OptimizationGoal
from backend.services.optimizer import generate_recommendations


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

@st.composite
def campaign_metrics_strategy(draw):
    """Generate valid CampaignMetrics objects with non-negative numeric fields."""
    campaign_id = draw(
        st.text(
            min_size=1,
            max_size=20,
            alphabet=st.characters(whitelist_categories=("Lu", "Ll", "Nd")),
        )
    )
    impressions = draw(st.integers(min_value=0, max_value=1_000_000))
    clicks = draw(st.integers(min_value=0, max_value=impressions)) if impressions > 0 else 0
    spend = draw(
        st.floats(min_value=0.0, max_value=100_000.0, allow_nan=False, allow_infinity=False)
    )
    ctr = clicks / impressions if impressions > 0 else 0.0
    cpc = spend / clicks if clicks > 0 else 0.0
    return CampaignMetrics(
        campaign_id=campaign_id,
        campaign_name="Test",
        date="2024-01-15",
        impressions=impressions,
        clicks=clicks,
        spend=spend,
        conversions=draw(st.integers(min_value=0, max_value=1000)),
        ctr=ctr,
        cpc=cpc,
        roas=draw(
            st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
        ),
        reach=draw(st.integers(min_value=0, max_value=1_000_000)),
        frequency=draw(
            st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)
        ),
    )


# ---------------------------------------------------------------------------
# Property 2: Recommendation count equals input metrics count
# Validates: Requirements 5.1
# ---------------------------------------------------------------------------

@given(metrics_list=st.lists(campaign_metrics_strategy(), min_size=1, max_size=10))
@settings(max_examples=200, deadline=None)
def test_recommendation_count_equals_metrics_count(metrics_list):
    """
    **Validates: Requirements 5.1**

    generate_recommendations() must produce exactly one Recommendation per
    campaign in the input metrics list, regardless of list length.
    """
    with patch("backend.services.optimizer._write_to_dynamodb"), \
         patch("backend.services.optimizer.generate_ad_copy_from_recommendation", return_value="ad copy"):
        # Empty predictions dict forces rule-based fallback for all campaigns
        recs = generate_recommendations(metrics_list, {}, OptimizationGoal.CTR)

    assert len(recs) == len(metrics_list), (
        f"Expected {len(metrics_list)} recommendations, got {len(recs)}"
    )


# ---------------------------------------------------------------------------
# Property 3: Confidence score is always in [0, 1]
# Validates: Requirements 5.3
# ---------------------------------------------------------------------------

@given(
    metrics_list=st.lists(campaign_metrics_strategy(), min_size=1, max_size=5),
    confidence=st.floats(
        min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False
    ),
)
@settings(max_examples=200, deadline=None)
def test_confidence_score_always_in_bounds(metrics_list, confidence):
    """
    **Validates: Requirements 5.3**

    confidence_score on every Recommendation must be in [0.0, 1.0], even when
    the raw prediction supplies an out-of-range confidence value.
    """
    # Build predictions with the arbitrary (possibly out-of-range) confidence
    predictions = {
        m.campaign_id: {
            "predicted_ctr": m.ctr,
            "predicted_cpc": m.cpc,
            "predicted_roas": m.roas,
            "confidence_score": confidence,
        }
        for m in metrics_list
    }

    with patch("backend.services.optimizer._write_to_dynamodb"), \
         patch("backend.services.optimizer.generate_ad_copy_from_recommendation", return_value="ad copy"):
        recs = generate_recommendations(metrics_list, predictions, OptimizationGoal.CTR)

    for rec in recs:
        assert 0.0 <= rec.confidence_score <= 1.0, (
            f"confidence_score {rec.confidence_score} is out of [0, 1] "
            f"(raw confidence supplied: {confidence})"
        )


# ---------------------------------------------------------------------------
# Property 4: suggested_value never deviates more than 50% from current_value
# Validates: Requirements 5.2
# ---------------------------------------------------------------------------

@given(
    current_value=st.floats(
        min_value=0.01, max_value=1_000_000.0, allow_nan=False, allow_infinity=False
    ),
    goal=st.sampled_from(list(OptimizationGoal)),
)
@settings(max_examples=200, deadline=None)
def test_suggested_value_guardrail(current_value, goal):
    """
    **Validates: Requirements 5.2**

    suggested_value must never deviate more than 50% from current_value,
    regardless of the OptimizationGoal or the magnitude of current_value.
    """
    # Build a single CampaignMetrics whose relevant field matches current_value
    metrics = CampaignMetrics(
        campaign_id="guardrail_test",
        campaign_name="Guardrail Test",
        date="2024-01-15",
        impressions=1000,
        clicks=50,
        spend=current_value if goal == OptimizationGoal.CPC else 500.0,
        conversions=int(current_value) if goal == OptimizationGoal.CONVERSION else 10,
        ctr=current_value if goal == OptimizationGoal.CTR else 0.05,
        cpc=current_value if goal == OptimizationGoal.CPC else 10.0,
        roas=current_value if goal == OptimizationGoal.ROAS else 2.0,
        reach=10000,
        frequency=1.5,
    )

    with patch("backend.services.optimizer._write_to_dynamodb"), \
         patch("backend.services.optimizer.generate_ad_copy_from_recommendation", return_value="ad copy"):
        recs = generate_recommendations([metrics], {}, goal)

    assert len(recs) == 1
    rec = recs[0]

    # The guardrail: |suggested - current| / current <= 0.5
    # Use max(..., 1e-9) to avoid division by zero when current_value rounds to 0
    # (e.g. CONVERSION goal with a fractional current_value < 1 → conversions=0)
    safe_current = max(rec.current_value, 1e-9)
    deviation = abs(rec.suggested_value - rec.current_value) / safe_current
    assert deviation <= 0.5, (
        f"suggested_value {rec.suggested_value} deviates {deviation:.2%} from "
        f"current_value {rec.current_value} (goal={goal}, limit=50%)"
    )

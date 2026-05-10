"""
Property-based tests for data_processor normalization.

Property 1: CTR is always in [0, 1] for any non-negative impressions and clicks
            where clicks <= impressions (realistic constraint).

Validates: Requirements 3.4
"""

from hypothesis import given, settings
from hypothesis import strategies as st

from backend.services.data_processor import normalize_metrics


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

@st.composite
def valid_record_strategy(draw):
    """
    Generate a raw record with realistic constraints:
    - impressions >= 0
    - 0 <= clicks <= impressions  (clicks cannot exceed impressions)
    - spend >= 0
    """
    impressions = draw(st.integers(min_value=0, max_value=10_000_000))
    clicks = draw(st.integers(min_value=0, max_value=impressions)) if impressions > 0 else 0
    spend = draw(
        st.floats(
            min_value=0.0,
            max_value=1_000_000.0,
            allow_nan=False,
            allow_infinity=False,
        )
    )
    return {
        "campaign_id": "camp_001",
        "impressions": impressions,
        "clicks": clicks,
        "spend": spend,
    }


# ---------------------------------------------------------------------------
# Property 1: CTR is always in [0, 1]
# Validates: Requirements 3.4
# ---------------------------------------------------------------------------

@given(record=valid_record_strategy())
@settings(max_examples=500)
def test_ctr_always_in_bounds(record: dict) -> None:
    """
    **Validates: Requirements 3.4**

    For any non-negative impressions and clicks (with clicks <= impressions),
    the computed CTR must always be in the range [0.0, 1.0].
    """
    results = normalize_metrics([record])

    # Records with all required fields should always produce a result
    assert len(results) == 1, (
        f"Expected 1 result for valid record, got {len(results)}"
    )

    ctr = results[0].ctr
    assert 0.0 <= ctr <= 1.0, (
        f"CTR {ctr} is out of bounds [0, 1] for "
        f"impressions={record['impressions']}, clicks={record['clicks']}"
    )


# ---------------------------------------------------------------------------
# Property 6: normalize_metrics is idempotent
# Validates: Requirements 3.3, 3.4, 3.5
# ---------------------------------------------------------------------------

@st.composite
def valid_record_list_strategy(draw):
    """Generate a list of 1–10 valid raw records."""
    n = draw(st.integers(min_value=1, max_value=10))
    return [draw(valid_record_strategy()) for _ in range(n)]


@given(records=valid_record_list_strategy())
@settings(max_examples=300)
def test_normalize_metrics_idempotent(records: list) -> None:
    """
    **Validates: Requirements 3.3, 3.4, 3.5**

    normalize_metrics is idempotent: applying it twice to valid input yields
    the same result as applying it once.
    """
    first_pass = normalize_metrics(records)

    # Convert CampaignMetrics objects back to dicts for the second call
    dicts_from_first_pass = [m.model_dump() for m in first_pass]

    second_pass = normalize_metrics(dicts_from_first_pass)

    assert first_pass == second_pass, (
        f"normalize_metrics is not idempotent.\n"
        f"first_pass:  {first_pass}\n"
        f"second_pass: {second_pass}"
    )

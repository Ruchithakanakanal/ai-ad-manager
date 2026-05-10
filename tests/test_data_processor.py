"""
Unit tests for backend/services/data_processor.py

Covers: normalize_metrics and build_feature_vector
Requirements: 3.4, 3.5, 3.6
"""

import pytest
from backend.services.data_processor import normalize_metrics, build_feature_vector
from backend.models.ad_models import CampaignMetrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_record(**overrides) -> dict:
    """Return a minimal valid raw record, with optional field overrides."""
    base = {
        "campaign_id": "camp_001",
        "campaign_name": "Test Campaign",
        "date": "2024-01-15",
        "impressions": 1000,
        "clicks": 50,
        "spend": 100.0,
        "conversions": 5,
        "roas": 2.5,
        "reach": 900,
        "frequency": 1.1,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# test_normalize_valid_full_record
# Requirements: 3.4, 3.5
# ---------------------------------------------------------------------------

def test_normalize_valid_full_record():
    """Valid record with all fields — CTR and CPC are computed correctly."""
    record = make_record(impressions=1000, clicks=50, spend=100.0)
    results = normalize_metrics([record])

    assert len(results) == 1
    m = results[0]
    assert m.campaign_id == "camp_001"
    assert m.impressions == 1000
    assert m.clicks == 50
    assert m.spend == 100.0
    assert m.ctr == pytest.approx(0.05)   # 50 / 1000
    assert m.cpc == pytest.approx(2.0)    # 100.0 / 50


# ---------------------------------------------------------------------------
# test_normalize_zero_impressions
# Requirements: 3.4
# ---------------------------------------------------------------------------

def test_normalize_zero_impressions():
    """impressions=0 must yield ctr=0.0 (no ZeroDivisionError)."""
    record = make_record(impressions=0, clicks=0, spend=0.0)
    results = normalize_metrics([record])

    assert len(results) == 1
    assert results[0].ctr == 0.0


# ---------------------------------------------------------------------------
# test_normalize_zero_clicks
# Requirements: 3.5
# ---------------------------------------------------------------------------

def test_normalize_zero_clicks():
    """clicks=0 must yield cpc=0.0 (no ZeroDivisionError)."""
    record = make_record(impressions=500, clicks=0, spend=50.0)
    results = normalize_metrics([record])

    assert len(results) == 1
    assert results[0].cpc == 0.0


# ---------------------------------------------------------------------------
# Missing required field tests
# Requirements: 3.6
# ---------------------------------------------------------------------------

def test_normalize_missing_campaign_id():
    """Record missing campaign_id must be excluded from output."""
    record = make_record()
    del record["campaign_id"]
    results = normalize_metrics([record])

    assert len(results) == 0


def test_normalize_missing_impressions():
    """Record missing impressions must be excluded from output."""
    record = make_record()
    del record["impressions"]
    results = normalize_metrics([record])

    assert len(results) == 0


def test_normalize_missing_clicks():
    """Record missing clicks must be excluded from output."""
    record = make_record()
    del record["clicks"]
    results = normalize_metrics([record])

    assert len(results) == 0


def test_normalize_missing_spend():
    """Record missing spend must be excluded from output."""
    record = make_record()
    del record["spend"]
    results = normalize_metrics([record])

    assert len(results) == 0


# ---------------------------------------------------------------------------
# test_normalize_mixed_valid_invalid
# Requirements: 3.6
# ---------------------------------------------------------------------------

def test_normalize_mixed_valid_invalid():
    """2 valid records + 1 invalid (missing spend) → output length == 2."""
    valid1 = make_record(campaign_id="camp_001")
    valid2 = make_record(campaign_id="camp_002")
    invalid = make_record(campaign_id="camp_003")
    del invalid["spend"]

    results = normalize_metrics([valid1, valid2, invalid])

    assert len(results) == 2
    ids = {m.campaign_id for m in results}
    assert ids == {"camp_001", "camp_002"}


# ---------------------------------------------------------------------------
# test_normalize_string_numeric_fields
# Requirements: 3.4, 3.5
# ---------------------------------------------------------------------------

def test_normalize_string_numeric_fields():
    """Facebook API may return numeric fields as strings — they must be parsed correctly."""
    record = {
        "campaign_id": "camp_str",
        "impressions": "1000",   # string
        "clicks": "40",          # string
        "spend": "80.0",         # string
    }
    results = normalize_metrics([record])

    assert len(results) == 1
    m = results[0]
    assert m.impressions == 1000
    assert m.clicks == 40
    assert m.spend == pytest.approx(80.0)
    assert m.ctr == pytest.approx(0.04)   # 40 / 1000
    assert m.cpc == pytest.approx(2.0)    # 80.0 / 40


# ---------------------------------------------------------------------------
# test_build_feature_vector
# Requirements: 4.1 (via design spec)
# ---------------------------------------------------------------------------

def test_build_feature_vector():
    """build_feature_vector returns a list of 9 floats in the correct order."""
    metrics = CampaignMetrics(
        campaign_id="camp_001",
        campaign_name="Test",
        date="2024-01-15",
        impressions=2000,
        clicks=100,
        spend=200.0,
        conversions=10,
        ctr=0.05,
        cpc=2.0,
        roas=3.0,
        reach=1800,
        frequency=1.1,
    )
    vector = build_feature_vector(metrics)

    assert isinstance(vector, list)
    assert len(vector) == 9
    assert all(isinstance(v, float) for v in vector)

    # Verify order: impressions, clicks, spend, conversions, ctr, cpc, roas, reach, frequency
    expected = [2000.0, 100.0, 200.0, 10.0, 0.05, 2.0, 3.0, 1800.0, 1.1]
    assert vector == pytest.approx(expected)

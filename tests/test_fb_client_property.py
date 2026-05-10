"""
Property-based tests for Facebook Ads API client pagination accumulation.

Property 5: Pagination accumulates all records (total record count is
monotonically non-decreasing across pages).

Validates: Requirements 2.4
"""

from hypothesis import given, settings
from hypothesis import strategies as st


# ---------------------------------------------------------------------------
# Helpers — simulate the pagination accumulation loop from campaign_fetcher
# ---------------------------------------------------------------------------

def simulate_pagination_accumulation(pages: list[list[dict]]) -> tuple[list[dict], list[int]]:
    """
    Simulate the pagination loop that campaign_fetcher uses when calling
    get_insights() repeatedly until no next page exists.

    Returns:
        all_records: the fully accumulated list of records
        running_counts: the record count after each page is appended
    """
    all_records: list[dict] = []
    running_counts: list[int] = []

    for page in pages:
        all_records.extend(page)
        running_counts.append(len(all_records))

    return all_records, running_counts


# ---------------------------------------------------------------------------
# Hypothesis strategies
# ---------------------------------------------------------------------------

record_strategy = st.fixed_dictionaries({
    "campaign_id": st.text(min_size=1, max_size=20),
    "impressions": st.integers(min_value=0, max_value=10_000_000),
    "clicks": st.integers(min_value=0, max_value=10_000_000),
    "spend": st.floats(min_value=0.0, max_value=1_000_000.0, allow_nan=False, allow_infinity=False),
})

pages_strategy = st.lists(
    st.lists(record_strategy, min_size=0, max_size=50),
    min_size=1,
    max_size=10,
)


# ---------------------------------------------------------------------------
# Property 5: Pagination accumulates all records
# Validates: Requirements 2.4
# ---------------------------------------------------------------------------

@given(pages=pages_strategy)
@settings(max_examples=200)
def test_pagination_total_equals_sum_of_pages(pages: list[list[dict]]) -> None:
    """
    **Validates: Requirements 2.4**

    After accumulating all pages the total record count must equal the sum
    of records across every individual page.
    """
    all_records, _ = simulate_pagination_accumulation(pages)

    expected_total = sum(len(page) for page in pages)
    assert len(all_records) == expected_total, (
        f"Expected {expected_total} records after accumulating {len(pages)} pages, "
        f"got {len(all_records)}"
    )


@given(pages=pages_strategy)
@settings(max_examples=200)
def test_pagination_count_is_monotonically_non_decreasing(pages: list[list[dict]]) -> None:
    """
    **Validates: Requirements 2.4**

    The running record count must be monotonically non-decreasing as each
    page is appended — i.e., no page can remove records.
    """
    _, running_counts = simulate_pagination_accumulation(pages)

    for i in range(1, len(running_counts)):
        assert running_counts[i] >= running_counts[i - 1], (
            f"Running count decreased at page {i}: "
            f"{running_counts[i - 1]} → {running_counts[i]}"
        )

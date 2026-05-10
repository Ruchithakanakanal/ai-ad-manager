# Implementation Plan: AI-Powered Facebook Campaign Optimization

## Overview

Extend the existing FastAPI/Lambda backend with a full campaign analytics and optimization pipeline. Implementation proceeds in layers: data models → integrations → services → API routes → frontend → infrastructure.

## Tasks

- [x] 1. Extend data models in `backend/models/ad_models.py`
  - Add `OptimizationGoal` enum (CTR, CPC, CONVERSION, ROAS)
  - Add `CampaignMetrics` Pydantic model with all fields (campaign_id, date, impressions, clicks, spend, conversions, ctr, cpc, roas, reach, frequency)
  - Add `Recommendation` Pydantic model (recommendation_id, campaign_id, generated_at, goal, action, current_value, suggested_value, confidence_score, reasoning, applied)
  - Add `AlertConfig` Pydantic model (user_id, campaign_id, metric, threshold, direction, sns_topic_arn)
  - Extend existing `AdRequest` with optional `campaign_id` and `optimization_goal` fields
  - _Requirements: 3.3, 5.1, 5.3, 7.1_

- [x] 2. Implement Facebook Ads API client in `backend/integrations/fb_client.py`
  - [x] 2.1 Implement `get_insights(account_id, date_range, access_token, fields, after=None) -> dict`
    - Call Facebook Ads Insights API with pagination support (`after` cursor)
    - Raise `FacebookAPIError` on non-2xx responses, including status code and message
    - Retrieve access token from Secrets Manager (never from env vars or code)
    - _Requirements: 2.1, 2.7, 2.8, 8.5_

  - [x] 2.2 Write property test for pagination accumulation
    - **Property 5: Pagination accumulates all records (total record count is monotonically non-decreasing across pages)**
    - **Validates: Requirements 2.4**
    - Use `hypothesis` to generate multi-page response fixtures and assert accumulated count

  - [x] 2.3 Implement `apply_recommendation(campaign_id, update_payload, access_token) -> bool`
    - Call Facebook Ads API to apply bid/budget/audience update
    - Return `True` on success, raise `FacebookAPIError` on failure
    - _Requirements: 5.8_

  - [x] 2.4 Write unit tests for `fb_client.py`
    - Mock Facebook API responses: success, 429 rate limit, 401 expired token, network error
    - Test `apply_recommendation` success and failure paths
    - _Requirements: 2.5, 2.6, 2.7_

- [x] 3. Implement campaign fetcher service in `backend/services/campaign_fetcher.py`
  - [x] 3.1 Implement `fetch_and_store(account_id: str, date_range: dict) -> str`
    - Retrieve access token from Secrets Manager
    - Call `get_insights()` following all pagination cursors until no next page
    - Write raw JSON to `s3://raw-bucket/raw/{date}/{account_id}.json` with SSE-S3
    - Return the S3 key of the written object
    - Implement exponential backoff retry (up to 5 times) on HTTP 429
    - On token expiry (401), publish SNS alert to admin topic and halt
    - Route to DLQ after 5 failed retries
    - _Requirements: 2.3, 2.4, 2.5, 2.6_

  - [x] 3.2 Write unit tests for `fetch_and_store`
    - Mock S3 writes with moto, mock Facebook API with responses fixture
    - Test retry logic, DLQ routing, token expiry alert path
    - _Requirements: 2.5, 2.6_

- [x] 4. Implement data processor service in `backend/services/data_processor.py`
  - [x] 4.1 Implement `normalize_metrics(raw_records: list[dict]) -> list[CampaignMetrics]`
    - Compute `ctr = clicks / impressions` (0.0 if impressions == 0)
    - Compute `cpc = spend / clicks` (0.0 if clicks == 0)
    - Log warning and exclude records missing required fields (campaign_id, impressions, clicks, spend)
    - _Requirements: 3.3, 3.4, 3.5, 3.6_

  - [x] 4.2 Write property test for CTR bounds
    - **Property 1: CTR is always in [0, 1] for any non-negative impressions and clicks**
    - **Validates: Requirements 3.4**
    - Use `hypothesis` strategies to generate arbitrary non-negative impressions/clicks values

  - [x] 4.3 Write property test for normalize_metrics idempotency
    - **Property 6: normalize_metrics is idempotent — applying it twice to valid input yields the same result**
    - **Validates: Requirements 3.3, 3.4, 3.5**
    - Use `hypothesis` to generate valid raw record lists and assert `normalize(normalize(x)) == normalize(x)`

  - [x] 4.4 Implement `build_feature_vector(metrics: CampaignMetrics) -> list[float]`
    - Extract numeric fields (impressions, clicks, spend, conversions, ctr, cpc, roas, reach, frequency) into a float list
    - _Requirements: 4.1_

  - [x] 4.5 Write unit tests for `data_processor.py`
    - Test zero impressions, zero clicks, missing fields, valid full record
    - _Requirements: 3.4, 3.5, 3.6_

- [x] 5. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement optimizer service in `backend/services/optimizer.py`
  - [x] 6.1 Implement `generate_recommendations(metrics, predictions, goal) -> list[Recommendation]`
    - Produce exactly one `Recommendation` per campaign in `metrics`
    - Enforce 50% guardrail: `suggested_value` must not deviate more than 50% from `current_value`
    - Set `confidence_score` in [0.0, 1.0]; flag low-confidence (< 0.6) in `reasoning`
    - Fall back to rule-based logic if SageMaker endpoint times out; log fallback to CloudWatch
    - Write each recommendation to DynamoDB `Recommendations` table with up to 3 retries (exponential backoff)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 4.4_

  - [x] 6.2 Write property test for recommendation count
    - **Property 2: Output recommendation count always equals input metrics count**
    - **Validates: Requirements 5.1**
    - Use `hypothesis` to generate arbitrary-length metrics lists and assert `len(recs) == len(metrics)`

  - [x] 6.3 Write property test for confidence score bounds
    - **Property 3: Confidence score is always in [0, 1] for any prediction input**
    - **Validates: Requirements 5.3**
    - Use `hypothesis` strategies to generate arbitrary float predictions

  - [x] 6.4 Write property test for suggested value guardrail
    - **Property 4: suggested_value never deviates more than 50% from current_value**
    - **Validates: Requirements 5.2**
    - Use `hypothesis` strategies to generate arbitrary current_value inputs

  - [x] 6.5 Implement `check_and_alert(rec: Recommendation, configs: list[AlertConfig]) -> None`
    - Evaluate each `AlertConfig` for the campaign
    - Publish SNS message when `direction="below"` and metric < threshold, or `direction="above"` and metric > threshold
    - Only evaluate configs when `confidence_score >= 0.6`
    - _Requirements: 7.3, 7.4, 7.5, 7.6_

  - [x] 6.6 Write unit tests for `optimizer.py`
    - Test guardrail enforcement, low-confidence flagging, DynamoDB retry, rule-based fallback
    - Test `check_and_alert` for both directions and no-match case
    - _Requirements: 5.2, 5.4, 5.6, 7.3, 7.4, 7.5_

- [x] 7. Extend `backend/services/ai_engine.py` with Bedrock ad copy generation
  - [x] 7.1 Implement `generate_ad_copy_from_recommendation(rec: Recommendation) -> str`
    - Call AWS Bedrock (Claude) with recommendation context to produce human-readable ad copy
    - Integrate call into `generate_recommendations()` in optimizer (when Bedrock is available)
    - _Requirements: 5.9_

  - [x] 7.2 Write unit tests for `generate_ad_copy_from_recommendation`
    - Mock Bedrock client; test successful response and fallback on Bedrock unavailability
    - _Requirements: 5.9_

- [x] 8. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement API route handlers in `backend/routes/`
  - [x] 9.1 Create `backend/routes/auth.py` — `POST /auth/login`
    - Exchange credentials with Cognito and return JWT tokens
    - Return HTTP 401 on invalid credentials
    - _Requirements: 1.1, 1.2_

  - [x] 9.2 Create `backend/routes/campaigns.py` — campaign and metrics endpoints
    - `GET /campaigns` — list all campaigns with latest metrics (requires valid JWT)
    - `GET /campaigns/{id}/metrics` — time-series metrics from DynamoDB
    - `GET /campaigns/{id}/recommendations` — latest recommendations (Analyst/Admin only)
    - `POST /campaigns/{id}/apply` — apply recommendation to Facebook API, set `applied=True` in DynamoDB (Analyst/Admin only)
    - `POST /campaigns/fetch` — trigger on-demand `fetch_and_store` (Analyst/Admin only)
    - Enforce role-based access: Viewer read-only, Analyst/Admin read-write
    - Return HTTP 401 for missing/invalid JWT; HTTP 403 for insufficient role
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7, 2.2, 5.7, 5.8, 6.6_

  - [x] 9.3 Create `backend/routes/dashboard.py` — `GET /dashboard/summary`
    - Aggregate KPIs across all campaigns from DynamoDB
    - Respond within 2 seconds under normal load
    - _Requirements: 6.5, 6.7_

  - [x] 9.4 Create `backend/routes/alerts.py` — alert config endpoints
    - `GET /alerts` — return all AlertConfigs for authenticated user
    - `POST /alerts` — create or update AlertConfig in DynamoDB (Analyst/Admin only)
    - _Requirements: 7.1, 7.2_

  - [x] 9.5 Register all new routers in `backend/app.py` and add Cognito JWT authorizer middleware
    - Validate JWT on every request; extract role claim and attach to request context
    - Return HTTP 401 on expired or missing token; redirect hint for Dashboard
    - _Requirements: 1.3, 1.4, 1.8_

  - [x] 9.6 Write unit tests for route handlers
    - Test auth flow, role enforcement (Viewer/Analyst/Admin), 401/403 responses
    - Mock DynamoDB with moto; mock Facebook API for apply endpoint
    - _Requirements: 1.1–1.8, 5.7, 5.8, 6.5, 7.1, 7.2_

- [x] 10. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Build React dashboard in `frontend/`
  - [x] 11.1 Scaffold React app with login page and Cognito auth flow
    - Implement login form calling `POST /auth/login`
    - Store JWT in memory (not localStorage); redirect to dashboard on success
    - Redirect to login on 401 response from any API call
    - _Requirements: 1.1, 1.8, 6.1_

  - [x] 11.2 Implement campaign overview page
    - Fetch `GET /campaigns` and display all campaigns with latest metrics in a table/card layout
    - _Requirements: 6.2_

  - [x] 11.3 Implement campaign detail page with time-series graphs
    - Fetch `GET /campaigns/{id}/metrics` and render line charts for impressions, clicks, spend, CTR, CPC, ROAS
    - _Requirements: 6.3_

  - [x] 11.4 Implement recommendations panel
    - Fetch `GET /campaigns/{id}/recommendations` and display as actionable cards
    - Show "Apply" button only for Analyst/Admin roles; hide for Viewer
    - Call `POST /campaigns/{id}/apply` on button click
    - _Requirements: 6.4, 6.8, 5.7, 5.8_

  - [x] 11.5 Implement KPI summary and alert configuration UI
    - Fetch `GET /dashboard/summary` and display aggregated KPI widgets
    - Implement alert config form calling `POST /alerts` (Analyst/Admin only)
    - _Requirements: 6.5, 7.1_

- [x] 12. Create AWS infrastructure stacks in `infrastructure/` (optional CDK)
  - [x] 12.1 Define CDK stacks for Lambda functions, DynamoDB tables, S3 buckets, EventBridge rule, Step Functions state machine, SNS topics, and API Gateway
    - Assign separate least-privilege IAM role per Lambda function
    - Enable SSE-S3 on all S3 buckets with public access blocked
    - Enable DynamoDB encryption at rest and on-demand capacity mode
    - Configure EventBridge cron rule (every 6 hours) targeting fb_fetcher Lambda
    - Configure SQS dead-letter queue for fb_fetcher
    - Configure provisioned concurrency on optimizer Lambda
    - _Requirements: 8.1–8.9, 2.1, 2.5_

  - [x] 12.2 Define CDK stack for CloudFront distribution serving the React frontend from S3
    - Enforce HTTPS; configure global edge caching
    - _Requirements: 6.1, 8.1_

- [x] 13. Write integration tests in `tests/`
  - [x] 13.1 Write integration test for full pipeline: S3 upload → Step Functions → DynamoDB write
    - Use moto to mock S3, DynamoDB, SNS; mock SageMaker and Glue responses
    - Assert recommendations written to DynamoDB after pipeline completes
    - _Requirements: 3.2, 3.7, 4.1, 5.5_

  - [x] 13.2 Write integration test for API Gateway → Lambda → DynamoDB round-trip
    - Use FastAPI TestClient; mock DynamoDB with moto
    - Test authenticated and unauthenticated requests across all role levels
    - _Requirements: 1.3, 1.4, 1.5, 1.6, 1.7_

- [x] 14. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at logical boundaries
- Property tests (Properties 1–6) are implemented using `hypothesis` and validate universal correctness invariants
- Unit tests validate specific examples, edge cases, and error conditions
- Infrastructure tasks (task 12) are optional if deploying manually or using existing IaC

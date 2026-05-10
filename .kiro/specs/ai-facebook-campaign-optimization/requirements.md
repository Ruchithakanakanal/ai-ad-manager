# Requirements Document

## Introduction

This document defines the requirements for the AI-Powered Facebook Campaign Optimization platform — a serverless, cloud-native system that automatically fetches Facebook Ads performance data, runs ML models to detect optimization opportunities, and delivers actionable recommendations through a React dashboard. The system extends an existing FastAPI/Lambda backend with a full campaign analytics and optimization pipeline built on AWS serverless services.

## Glossary

- **System**: The AI-Powered Facebook Campaign Optimization platform as a whole
- **Dashboard**: The React frontend hosted on S3 and served via CloudFront
- **API**: Amazon API Gateway REST interface
- **Cognito**: Amazon Cognito user pool and identity service
- **fb_fetcher**: AWS Lambda function responsible for fetching data from the Facebook Ads API
- **data_processor**: AWS Lambda function responsible for validating and normalizing raw campaign data
- **optimizer**: AWS Lambda function responsible for generating AI-driven recommendations
- **notifier**: AWS Lambda function responsible for sending SNS alerts
- **dashboard_api**: AWS Lambda function responsible for serving analytics data to the Dashboard
- **Facebook_API**: The external Facebook Ads Insights API
- **S3**: Amazon S3 object storage (raw bucket and model bucket)
- **DynamoDB**: Amazon DynamoDB NoSQL database
- **SageMaker**: AWS SageMaker ML training and inference service
- **Glue**: AWS Glue ETL service
- **Athena**: Amazon Athena SQL query service
- **Step_Functions**: AWS Step Functions ML pipeline state machine
- **EventBridge**: Amazon EventBridge scheduler for cron-based triggers
- **SNS**: Amazon Simple Notification Service for alerts
- **Bedrock**: AWS Bedrock (Claude) for ad copy generation
- **Secrets_Manager**: AWS Secrets Manager for storing Facebook API tokens
- **CampaignMetrics**: Pydantic model holding normalized campaign performance data (CTR, CPC, ROAS, etc.)
- **Recommendation**: Pydantic model holding an AI-generated optimization suggestion for a campaign
- **AlertConfig**: Pydantic model holding a user-defined threshold rule for SNS notifications
- **OptimizationGoal**: Enum of optimization targets: CTR, CPC, CONVERSION, ROAS
- **Admin**: User role with full read/write access including user management
- **Analyst**: User role with read/write access to campaigns and recommendations
- **Viewer**: User role with read-only access to the Dashboard

---

## Requirements

### Requirement 1: User Authentication and Role-Based Access

**User Story:** As a marketing team member, I want to log in securely and access only the features appropriate to my role, so that sensitive campaign data and optimization controls are protected.

#### Acceptance Criteria

1. WHEN a user submits valid credentials, THE Cognito SHALL authenticate the user and return a JWT containing the user's role claim.
2. WHEN a user submits invalid credentials, THE Cognito SHALL reject the request and THE API SHALL return an HTTP 401 response.
3. WHEN a request arrives at the API without a valid JWT, THE API SHALL return an HTTP 401 response and reject the request.
4. WHEN a request arrives at the API with a valid JWT, THE API SHALL extract the role claim and forward it to the invoked Lambda function.
5. WHILE a user holds the Viewer role, THE System SHALL permit read-only access to Dashboard endpoints and deny all write operations.
6. WHILE a user holds the Analyst role, THE System SHALL permit read and write access to campaign metrics, recommendations, and alert configurations.
7. WHILE a user holds the Admin role, THE System SHALL permit full access to all endpoints including user management.
8. IF a JWT has expired, THEN THE API SHALL return an HTTP 401 response and THE Dashboard SHALL redirect the user to the login page.
9. THE Secrets_Manager SHALL store all Facebook API access tokens, and THE System SHALL never expose tokens in code, environment variables, or API responses.

---

### Requirement 2: Scheduled and On-Demand Campaign Data Fetching

**User Story:** As a marketing analyst, I want campaign performance data fetched automatically from Facebook on a regular schedule and on demand, so that I always have up-to-date metrics without manual intervention.

#### Acceptance Criteria

1. WHEN the EventBridge cron trigger fires every 6 hours, THE fb_fetcher SHALL invoke the Facebook_API Insights endpoint for all configured ad accounts.
2. WHEN a user with Analyst or Admin role calls `POST /campaigns/fetch`, THE fb_fetcher SHALL immediately fetch the latest campaign data from the Facebook_API.
3. WHEN the Facebook_API returns a successful response, THE fb_fetcher SHALL write the raw JSON payload to `s3://raw-bucket/raw/{date}/{account_id}.json`.
4. WHEN the Facebook_API returns a paginated response, THE fb_fetcher SHALL follow all pagination cursors until no next page exists, accumulating all records.
5. IF the Facebook_API returns HTTP 429 (rate limit), THEN THE fb_fetcher SHALL retry with exponential backoff up to 5 times before routing the event to a dead-letter queue.
6. IF the Facebook access token has expired, THEN THE fb_fetcher SHALL halt the pipeline and publish an alert to the Admin via SNS.
7. IF the Facebook_API is unreachable, THEN THE fb_fetcher SHALL raise a `FacebookAPIError` containing the HTTP status code and error message.
8. THE fb_fetcher SHALL fetch at minimum the following fields per campaign: `campaign_id`, `impressions`, `clicks`, `spend`, `date_start`, `date_stop`.

---

### Requirement 3: Data Storage and ETL Processing

**User Story:** As a data engineer, I want raw Facebook data stored durably and processed into a queryable format, so that the ML pipeline and analytics queries have clean, structured input.

#### Acceptance Criteria

1. WHEN raw data is written to S3, THE S3 SHALL store it with server-side encryption (SSE-S3) and no public access.
2. WHEN a new raw data object is written to S3, THE Step_Functions SHALL be triggered via an S3 event to start the ML pipeline.
3. WHEN the Step_Functions pipeline starts, THE data_processor SHALL validate each raw record and normalize it into a `CampaignMetrics` object.
4. WHEN normalizing a record, THE data_processor SHALL compute `ctr = clicks / impressions`, setting `ctr = 0.0` if `impressions == 0`.
5. WHEN normalizing a record, THE data_processor SHALL compute `cpc = spend / clicks`, setting `cpc = 0.0` if `clicks == 0`.
6. IF a raw record is missing any required field (`campaign_id`, `impressions`, `clicks`, `spend`), THEN THE data_processor SHALL log a warning and exclude that record from the output without raising an exception.
7. WHEN normalization completes, THE data_processor SHALL trigger a Glue ETL job to clean, aggregate, and partition the metrics into Parquet format on S3.
8. IF the Glue ETL job fails, THEN THE Step_Functions SHALL retry the job once and, on a second failure, publish an alert via SNS.
9. THE DynamoDB CampaignMetrics table SHALL store processed metrics with `campaign_id` as the partition key and `date` as the sort key.
10. THE DynamoDB SHALL have encryption at rest enabled on all tables.
11. WHERE ad-hoc trend analysis is required, THE Athena SHALL be able to query processed Parquet data stored in S3.

---

### Requirement 4: AI Optimization Engine

**User Story:** As a marketing analyst, I want the system to automatically analyze campaign trends and predict future performance using ML models, so that I receive data-driven optimization guidance without manual analysis.

#### Acceptance Criteria

1. WHEN the Step_Functions pipeline reaches the inference step, THE SageMaker SHALL invoke the trained prediction endpoint with a feature vector built from the campaign's `CampaignMetrics`.
2. WHEN SageMaker returns predictions, THE SageMaker SHALL provide at minimum: `predicted_ctr`, `predicted_cpc`, and `predicted_roas` for each campaign.
3. WHEN the optimizer receives predictions, THE optimizer SHALL call `generate_recommendations()` with the metrics, predictions, and the campaign's `OptimizationGoal`.
4. IF the SageMaker endpoint times out, THEN THE optimizer SHALL fall back to rule-based recommendations and log the fallback event to CloudWatch.
5. THE SageMaker endpoint SHALL support auto-scaling based on invocation count to handle variable pipeline load.
6. THE optimizer Lambda SHALL use provisioned concurrency to minimize cold-start latency during inference.
7. WHEN the Glue ETL job succeeds, THE S3 model bucket SHALL contain the processed Parquet dataset available for SageMaker training jobs.

---

### Requirement 5: Recommendation Generation

**User Story:** As a marketing analyst, I want to receive specific, actionable recommendations for bid adjustments, audience refinement, and budget reallocation, so that I can improve campaign performance efficiently.

#### Acceptance Criteria

1. WHEN `generate_recommendations()` is called, THE optimizer SHALL produce exactly one `Recommendation` per campaign in the input `metrics` list.
2. WHEN generating a recommendation, THE optimizer SHALL set `suggested_value` such that it deviates from `current_value` by no more than 50%.
3. WHEN generating a recommendation, THE optimizer SHALL set `confidence_score` to a value in the range [0.0, 1.0].
4. WHEN a recommendation has `confidence_score < 0.6`, THE optimizer SHALL include a low-confidence flag in the `reasoning` field.
5. WHEN recommendations are generated, THE optimizer SHALL write each `Recommendation` to the DynamoDB Recommendations table.
6. IF a DynamoDB write fails, THEN THE optimizer SHALL retry up to 3 times with exponential backoff before logging the failure to CloudWatch.
7. WHEN a user with Analyst or Admin role calls `GET /campaigns/{id}/recommendations`, THE dashboard_api SHALL return the latest recommendations for that campaign from DynamoDB.
8. WHEN a user with Analyst or Admin role calls `POST /campaigns/{id}/apply`, THE System SHALL apply the selected recommendation to the Facebook_API and mark the `Recommendation.applied` field as `true` in DynamoDB.
9. WHERE Bedrock is available, THE optimizer SHALL call Bedrock to generate a human-readable ad copy suggestion associated with each recommendation.

---

### Requirement 6: Dashboard Visualization

**User Story:** As a marketing team member, I want a web dashboard that displays campaign KPIs, performance graphs, and AI recommendations, so that I can monitor and act on campaign performance from a single interface.

#### Acceptance Criteria

1. THE Dashboard SHALL be served via CloudFront with HTTPS enforced and global edge caching enabled.
2. WHEN a user navigates to the Dashboard, THE Dashboard SHALL display an overview of all campaigns with their latest metrics.
3. WHEN a user selects a campaign, THE Dashboard SHALL display time-series graphs for impressions, clicks, spend, CTR, CPC, and ROAS.
4. WHEN a user selects a campaign, THE Dashboard SHALL display the latest AI-generated recommendations as actionable cards.
5. WHEN a user calls `GET /dashboard/summary`, THE dashboard_api SHALL return aggregated KPIs across all campaigns within 2 seconds.
6. WHEN a user calls `GET /campaigns/{id}/metrics`, THE dashboard_api SHALL return the full time-series metrics for that campaign from DynamoDB.
7. THE API SHALL respond to all dashboard read requests within 2 seconds under normal load.
8. WHILE a user holds the Viewer role, THE Dashboard SHALL display all metrics and recommendations but hide all apply and configuration controls.

---

### Requirement 7: Automated Notifications and Alerts

**User Story:** As a marketing manager, I want to receive automated alerts when campaign performance drops or budget thresholds are breached, so that I can respond quickly to issues without constantly monitoring the dashboard.

#### Acceptance Criteria

1. WHEN a user with Analyst or Admin role calls `POST /alerts`, THE System SHALL create or update an `AlertConfig` in DynamoDB for the specified campaign, metric, threshold, and direction.
2. WHEN a user calls `GET /alerts`, THE dashboard_api SHALL return all `AlertConfig` records belonging to the authenticated user.
3. WHEN the optimizer generates a recommendation with `confidence_score >= 0.6`, THE notifier SHALL evaluate all `AlertConfig` records for that campaign.
4. WHEN an `AlertConfig` has `direction = "below"` and the current metric value is below the configured threshold, THE notifier SHALL publish an alert message to the configured SNS topic.
5. WHEN an `AlertConfig` has `direction = "above"` and the current metric value is above the configured threshold, THE notifier SHALL publish an alert message to the configured SNS topic.
6. WHEN an alert is published, THE SNS SHALL deliver the notification to all subscribed endpoints (email and/or SMS) for that topic.
7. IF the Facebook access token expires, THEN THE notifier SHALL publish an alert to the Admin SNS topic immediately.
8. IF the Glue ETL job fails twice consecutively, THEN THE notifier SHALL publish an alert to the Admin SNS topic.

---

### Requirement 8: Security and Infrastructure

**User Story:** As a system administrator, I want all infrastructure to follow least-privilege security principles and be fully serverless and auto-scaling, so that the platform is secure, cost-efficient, and operationally low-maintenance.

#### Acceptance Criteria

1. THE System SHALL enforce HTTPS on all CloudFront distributions and API Gateway endpoints.
2. THE System SHALL assign a separate least-privilege IAM role to each Lambda function.
3. THE S3 SHALL have server-side encryption (SSE-S3) enabled and block all public access on all buckets.
4. THE DynamoDB SHALL have encryption at rest enabled on all tables.
5. THE Secrets_Manager SHALL be the sole storage location for Facebook API access tokens.
6. THE System SHALL achieve 99.9% uptime by deploying Lambda and DynamoDB across multiple availability zones.
7. THE DynamoDB SHALL operate in on-demand capacity mode to scale automatically with traffic.
8. THE System SHALL use Lambda auto-scaling to handle concurrent pipeline executions without manual provisioning.
9. IF a Lambda function invocation fails due to an unhandled exception, THEN THE System SHALL log the full error and stack trace to CloudWatch.

1️⃣ Add Bedrock Explanation Requirement

Add this under Recommendation or Dashboard:

WHEN a recommendation is generated, THE System SHALL use AWS Bedrock to convert the recommendation into a human-readable explanation suitable for non-technical users.

2️⃣ Add Demo Mode Requirement

Add:

THE System SHALL support a demo mode using preloaded sample campaign data when Facebook API access is unavailable.
# Infrastructure — AWS CDK (Python)

This directory contains the AWS CDK v2 infrastructure-as-code for the
**AI-Powered Facebook Campaign Optimization** platform.

## Stacks

| Stack | Description |
|---|---|
| `CampaignOptimizerMainStack` | Lambda functions, DynamoDB tables, S3 buckets, EventBridge cron rule, SQS DLQ, Step Functions state machine, SNS topics, API Gateway, Cognito User Pool |
| `CampaignOptimizerFrontendStack` | S3 bucket + CloudFront distribution for the React dashboard |

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.12+ |
| Node.js | 18+ (required by CDK CLI) |
| AWS CDK CLI | 2.x (`npm install -g aws-cdk`) |
| AWS CLI | 2.x (configured with credentials) |

## Setup

```bash
# 1. Create and activate a virtual environment
cd infrastructure
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Bootstrap CDK in your target account/region (first time only)
cdk bootstrap aws://<ACCOUNT_ID>/<REGION>
```

## Synthesise CloudFormation templates

```bash
cdk synth
```

Generated templates are written to `cdk.out/`.

## Deploy

```bash
# Deploy both stacks
cdk deploy --all

# Deploy a single stack
cdk deploy CampaignOptimizerMainStack
cdk deploy CampaignOptimizerFrontendStack
```

Pass `--context account=<ACCOUNT_ID> --context region=<REGION>` if you have
not set `CDK_DEFAULT_ACCOUNT` / `CDK_DEFAULT_REGION` environment variables.

## Deploy the React frontend

After `CampaignOptimizerFrontendStack` is deployed:

```bash
# Build the React app
cd ../frontend
npm install
npm run build

# Sync the build output to S3
aws s3 sync dist/ s3://$(aws cloudformation describe-stacks \
  --stack-name CampaignOptimizerFrontendStack \
  --query "Stacks[0].Outputs[?OutputKey=='FrontendBucketName'].OutputValue" \
  --output text)/

# Invalidate the CloudFront cache
aws cloudfront create-invalidation \
  --distribution-id $(aws cloudformation describe-stacks \
    --stack-name CampaignOptimizerFrontendStack \
    --query "Stacks[0].Outputs[?OutputKey=='CloudFrontDistributionId'].OutputValue" \
    --output text) \
  --paths "/*"
```

## Secrets

The Facebook API access token must be stored in AWS Secrets Manager **before**
deploying or running the pipeline:

```bash
aws secretsmanager create-secret \
  --name facebook-api-token \
  --secret-string '{"access_token":"<YOUR_TOKEN>","account_id":"act_<ID>"}'
```

The `fb_fetcher` and `dashboard_api` Lambda functions retrieve this secret at
runtime. The token is **never** stored in environment variables or source code.

## Destroy

```bash
cdk destroy --all
```

> **Note:** DynamoDB tables and S3 buckets have `RemovalPolicy.RETAIN` to
> prevent accidental data loss. Delete them manually after confirming the data
> is no longer needed.

## Architecture overview

```
EventBridge (cron/6h)
        │
        ▼
  fb_fetcher Lambda ──► Facebook Ads API
        │
        ▼
  S3 raw-bucket  ──► EventBridge S3 event
                              │
                              ▼
                    Step Functions pipeline
                      ├─ data_processor Lambda
                      ├─ optimizer Lambda  ──► DynamoDB Recommendations
                      └─ notifier Lambda   ──► SNS (admin-alerts / campaign-alerts)

React Dashboard (S3 + CloudFront)
        │
        ▼
  API Gateway (Cognito JWT authorizer)
        │
        ▼
  dashboard_api Lambda ──► DynamoDB (CampaignMetrics, Recommendations, AlertConfigs, Users)
```

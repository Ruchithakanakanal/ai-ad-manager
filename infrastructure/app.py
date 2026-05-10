#!/usr/bin/env python3
"""
CDK app entry point for the AI-Powered Facebook Campaign Optimization platform.

Usage:
    cd infrastructure
    pip install -r requirements.txt
    cdk synth
    cdk deploy --all

Stacks:
    MainStack    — Lambda, DynamoDB, S3, EventBridge, Step Functions, SNS,
                   API Gateway, Cognito
    FrontendStack — S3 + CloudFront for the React dashboard
"""

import aws_cdk as cdk

from stacks.main_stack import MainStack
from stacks.frontend_stack import FrontendStack

app = cdk.App()

# Resolve target account and region from CDK context or environment variables.
# Set CDK_DEFAULT_ACCOUNT and CDK_DEFAULT_REGION, or pass --context flags.
env = cdk.Environment(
    account=app.node.try_get_context("account") or None,
    region=app.node.try_get_context("region") or "us-east-1",
)

MainStack(
    app,
    "CampaignOptimizerMainStack",
    env=env,
    description=(
        "AI-Powered Facebook Campaign Optimization — backend infrastructure "
        "(Lambda, DynamoDB, S3, EventBridge, Step Functions, SNS, API Gateway, Cognito)"
    ),
)

FrontendStack(
    app,
    "CampaignOptimizerFrontendStack",
    env=env,
    description=(
        "AI-Powered Facebook Campaign Optimization — frontend infrastructure "
        "(S3 + CloudFront for the React dashboard)"
    ),
)

app.synth()

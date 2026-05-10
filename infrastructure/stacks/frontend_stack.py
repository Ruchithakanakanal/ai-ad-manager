"""
Frontend CDK stack for the AI-Powered Facebook Campaign Optimization platform.

Provisions:
- S3 bucket for React static assets (private, SSE-S3)
- CloudFront distribution serving from the S3 bucket
  - HTTPS enforced (HTTP → HTTPS redirect)
  - Global edge caching
  - OAC (Origin Access Control) for S3

Requirements: 6.1, 8.1
"""

from aws_cdk import (
    Stack,
    RemovalPolicy,
    CfnOutput,
    aws_s3 as s3,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_iam as iam,
)
from constructs import Construct


class FrontendStack(Stack):
    """
    CloudFront + S3 stack for the React dashboard.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ------------------------------------------------------------------ #
        # S3 Bucket — private, SSE-S3, no public access                      #
        # ------------------------------------------------------------------ #
        frontend_bucket = s3.Bucket(
            self,
            "FrontendBucket",
            bucket_name=f"campaign-optimizer-frontend-{self.account}-{self.region}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=False,
            removal_policy=RemovalPolicy.RETAIN,
            enforce_ssl=True,
        )

        # ------------------------------------------------------------------ #
        # CloudFront Origin Access Control (OAC)                              #
        # ------------------------------------------------------------------ #
        oac = cloudfront.CfnOriginAccessControl(
            self,
            "FrontendOAC",
            origin_access_control_config=cloudfront.CfnOriginAccessControl.OriginAccessControlConfigProperty(
                name="campaign-optimizer-frontend-oac",
                description="OAC for campaign optimizer React frontend",
                origin_access_control_origin_type="s3",
                signing_behavior="always",
                signing_protocol="sigv4",
            ),
        )

        # ------------------------------------------------------------------ #
        # CloudFront Distribution                                              #
        # ------------------------------------------------------------------ #
        distribution = cloudfront.Distribution(
            self,
            "FrontendDistribution",
            comment="Campaign Optimizer React Dashboard",
            default_root_object="index.html",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(
                    frontend_bucket,
                    origin_access_levels=[
                        cloudfront.AccessLevel.READ,
                    ],
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                compress=True,
            ),
            # SPA fallback: serve index.html for all 403/404 responses
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                ),
            ],
            price_class=cloudfront.PriceClass.PRICE_CLASS_ALL,  # global edge caching
        )

        # Grant CloudFront OAC read access to the S3 bucket via bucket policy
        frontend_bucket.add_to_resource_policy(
            iam.PolicyStatement(
                sid="AllowCloudFrontServicePrincipal",
                effect=iam.Effect.ALLOW,
                principals=[iam.ServicePrincipal("cloudfront.amazonaws.com")],
                actions=["s3:GetObject"],
                resources=[frontend_bucket.arn_for_objects("*")],
                conditions={
                    "StringEquals": {
                        "AWS:SourceArn": self.format_arn(
                            service="cloudfront",
                            region="",
                            resource=f"distribution/{distribution.distribution_id}",
                        )
                    }
                },
            )
        )

        # ------------------------------------------------------------------ #
        # Stack Outputs                                                        #
        # ------------------------------------------------------------------ #
        CfnOutput(
            self,
            "FrontendBucketName",
            value=frontend_bucket.bucket_name,
            description="S3 bucket holding the React build artefacts",
        )
        CfnOutput(
            self,
            "CloudFrontDistributionId",
            value=distribution.distribution_id,
            description="CloudFront distribution ID",
        )
        CfnOutput(
            self,
            "CloudFrontDomainName",
            value=distribution.distribution_domain_name,
            description="CloudFront domain name (use as the dashboard URL)",
        )

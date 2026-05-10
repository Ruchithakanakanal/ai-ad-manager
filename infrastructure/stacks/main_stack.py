"""
Main CDK stack for the AI-Powered Facebook Campaign Optimization platform.

Provisions:
- Lambda functions (fb_fetcher, data_processor, optimizer, notifier, dashboard_api)
  each with a separate least-privilege IAM role
- DynamoDB tables (CampaignMetrics, Recommendations, AlertConfigs, Users)
  with encryption at rest and on-demand billing
- S3 buckets (raw-bucket, model-bucket) with SSE-S3 and public access blocked
- EventBridge cron rule (every 6 hours) targeting fb_fetcher
- SQS dead-letter queue for fb_fetcher
- Step Functions state machine orchestrating data_processor → optimizer
- SNS topics (admin-alerts, campaign-alerts)
- API Gateway REST API with Cognito JWT authorizer
- Cognito User Pool with admin/analyst/viewer groups
- Provisioned concurrency on optimizer Lambda

Requirements: 8.1–8.9, 2.1, 2.5
"""

from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    aws_lambda as _lambda,
    aws_iam as iam,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
    aws_events as events,
    aws_events_targets as targets,
    aws_sqs as sqs,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as sfn_tasks,
    aws_sns as sns,
    aws_apigateway as apigw,
    aws_cognito as cognito,
)
from constructs import Construct


class MainStack(Stack):
    """
    Core backend infrastructure stack.
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ------------------------------------------------------------------ #
        # Cognito User Pool                                                    #
        # ------------------------------------------------------------------ #
        user_pool = cognito.UserPool(
            self,
            "UserPool",
            user_pool_name="campaign-optimizer-user-pool",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=True,
            ),
            removal_policy=RemovalPolicy.RETAIN,
        )

        # Cognito groups: admin, analyst, viewer
        cognito.CfnUserPoolGroup(
            self,
            "AdminGroup",
            user_pool_id=user_pool.user_pool_id,
            group_name="admin",
            description="Full access including user management",
        )
        cognito.CfnUserPoolGroup(
            self,
            "AnalystGroup",
            user_pool_id=user_pool.user_pool_id,
            group_name="analyst",
            description="Read/write access to campaigns, recommendations, and alerts",
        )
        cognito.CfnUserPoolGroup(
            self,
            "ViewerGroup",
            user_pool_id=user_pool.user_pool_id,
            group_name="viewer",
            description="Read-only access to the dashboard",
        )

        # App client for the React frontend
        user_pool_client = user_pool.add_client(
            "WebClient",
            user_pool_client_name="campaign-optimizer-web-client",
            auth_flows=cognito.AuthFlow(user_password=True, user_srp=True),
            generate_secret=False,
        )

        # ------------------------------------------------------------------ #
        # SNS Topics                                                           #
        # ------------------------------------------------------------------ #
        admin_alerts_topic = sns.Topic(
            self,
            "AdminAlertsTopic",
            topic_name="admin-alerts",
            display_name="Campaign Optimizer Admin Alerts",
        )

        campaign_alerts_topic = sns.Topic(
            self,
            "CampaignAlertsTopic",
            topic_name="campaign-alerts",
            display_name="Campaign Optimizer Campaign Alerts",
        )

        # ------------------------------------------------------------------ #
        # SQS Dead-Letter Queue for fb_fetcher                                #
        # ------------------------------------------------------------------ #
        fb_fetcher_dlq = sqs.Queue(
            self,
            "FbFetcherDLQ",
            queue_name="fb-fetcher-dlq",
            retention_period=Duration.days(14),
            encryption=sqs.QueueEncryption.SQS_MANAGED,
        )

        # ------------------------------------------------------------------ #
        # DynamoDB Tables                                                      #
        # ------------------------------------------------------------------ #

        # CampaignMetrics: PK=campaign_id, SK=date
        campaign_metrics_table = dynamodb.Table(
            self,
            "CampaignMetricsTable",
            table_name="CampaignMetrics",
            partition_key=dynamodb.Attribute(
                name="campaign_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="date", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
        )
        # GSI: date-index for date-range queries
        campaign_metrics_table.add_global_secondary_index(
            index_name="date-index",
            partition_key=dynamodb.Attribute(
                name="date", type=dynamodb.AttributeType.STRING
            ),
        )

        # Recommendations: PK=campaign_id, SK=generated_at
        recommendations_table = dynamodb.Table(
            self,
            "RecommendationsTable",
            table_name="Recommendations",
            partition_key=dynamodb.Attribute(
                name="campaign_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="generated_at", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
        )
        # GSI: applied-index
        recommendations_table.add_global_secondary_index(
            index_name="applied-index",
            partition_key=dynamodb.Attribute(
                name="applied", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="generated_at", type=dynamodb.AttributeType.STRING
            ),
        )

        # AlertConfigs: PK=user_id, SK=campaign_id#metric
        alert_configs_table = dynamodb.Table(
            self,
            "AlertConfigsTable",
            table_name="AlertConfigs",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="campaign_id_metric", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # Users: PK=user_id
        users_table = dynamodb.Table(
            self,
            "UsersTable",
            table_name="Users",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            encryption=dynamodb.TableEncryption.AWS_MANAGED,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ------------------------------------------------------------------ #
        # S3 Buckets                                                           #
        # ------------------------------------------------------------------ #
        raw_bucket = s3.Bucket(
            self,
            "RawBucket",
            bucket_name=f"campaign-optimizer-raw-{self.account}-{self.region}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
            enforce_ssl=True,
        )

        model_bucket = s3.Bucket(
            self,
            "ModelBucket",
            bucket_name=f"campaign-optimizer-model-{self.account}-{self.region}",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
            enforce_ssl=True,
        )

        # ------------------------------------------------------------------ #
        # IAM Roles — one per Lambda (least-privilege)                        #
        # ------------------------------------------------------------------ #

        # --- fb_fetcher role ---
        fb_fetcher_role = iam.Role(
            self,
            "FbFetcherRole",
            role_name="campaign-optimizer-fb-fetcher-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        # Allow writing to raw S3 bucket
        raw_bucket.grant_put(fb_fetcher_role)
        # Allow reading Facebook token from Secrets Manager
        fb_fetcher_role.add_to_policy(
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=[
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:facebook-api-token*"
                ],
            )
        )
        # Allow sending to DLQ
        fb_fetcher_dlq.grant_send_messages(fb_fetcher_role)
        # Allow publishing to admin SNS topic (token expiry alert)
        admin_alerts_topic.grant_publish(fb_fetcher_role)

        # --- data_processor role ---
        data_processor_role = iam.Role(
            self,
            "DataProcessorRole",
            role_name="campaign-optimizer-data-processor-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        raw_bucket.grant_read(data_processor_role)
        model_bucket.grant_put(data_processor_role)
        campaign_metrics_table.grant_write_data(data_processor_role)
        # Allow starting Glue jobs
        data_processor_role.add_to_policy(
            iam.PolicyStatement(
                actions=["glue:StartJobRun", "glue:GetJobRun"],
                resources=["*"],
            )
        )

        # --- optimizer role ---
        optimizer_role = iam.Role(
            self,
            "OptimizerRole",
            role_name="campaign-optimizer-optimizer-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        recommendations_table.grant_write_data(optimizer_role)
        campaign_metrics_table.grant_read_data(optimizer_role)
        alert_configs_table.grant_read_data(optimizer_role)
        campaign_alerts_topic.grant_publish(optimizer_role)
        admin_alerts_topic.grant_publish(optimizer_role)
        # Allow invoking SageMaker endpoint
        optimizer_role.add_to_policy(
            iam.PolicyStatement(
                actions=["sagemaker:InvokeEndpoint"],
                resources=[
                    f"arn:aws:sagemaker:{self.region}:{self.account}:endpoint/campaign-optimizer"
                ],
            )
        )
        # Allow invoking Bedrock for ad copy generation
        optimizer_role.add_to_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=["*"],
            )
        )

        # --- notifier role ---
        notifier_role = iam.Role(
            self,
            "NotifierRole",
            role_name="campaign-optimizer-notifier-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        admin_alerts_topic.grant_publish(notifier_role)
        campaign_alerts_topic.grant_publish(notifier_role)
        alert_configs_table.grant_read_data(notifier_role)

        # --- dashboard_api role ---
        dashboard_api_role = iam.Role(
            self,
            "DashboardApiRole",
            role_name="campaign-optimizer-dashboard-api-role",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        campaign_metrics_table.grant_read_data(dashboard_api_role)
        recommendations_table.grant_read_write_data(dashboard_api_role)
        alert_configs_table.grant_read_write_data(dashboard_api_role)
        users_table.grant_read_write_data(dashboard_api_role)
        # Allow applying recommendations via Facebook API (needs token)
        dashboard_api_role.add_to_policy(
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=[
                    f"arn:aws:secretsmanager:{self.region}:{self.account}:secret:facebook-api-token*"
                ],
            )
        )

        # ------------------------------------------------------------------ #
        # Lambda Functions                                                     #
        # ------------------------------------------------------------------ #
        common_env = {
            "CAMPAIGN_METRICS_TABLE": campaign_metrics_table.table_name,
            "RECOMMENDATIONS_TABLE": recommendations_table.table_name,
            "ALERT_CONFIGS_TABLE": alert_configs_table.table_name,
            "USERS_TABLE": users_table.table_name,
            "RAW_BUCKET": raw_bucket.bucket_name,
            "MODEL_BUCKET": model_bucket.bucket_name,
            "ADMIN_ALERTS_TOPIC_ARN": admin_alerts_topic.topic_arn,
            "CAMPAIGN_ALERTS_TOPIC_ARN": campaign_alerts_topic.topic_arn,
            "FB_FETCHER_DLQ_URL": fb_fetcher_dlq.queue_url,
        }

        fb_fetcher_fn = _lambda.Function(
            self,
            "FbFetcherFunction",
            function_name="campaign-optimizer-fb-fetcher",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="services.campaign_fetcher.lambda_handler",
            code=_lambda.Code.from_asset("../backend"),
            role=fb_fetcher_role,
            timeout=Duration.minutes(15),
            memory_size=512,
            environment={
                **common_env,
                "FB_FETCHER_DLQ_URL": fb_fetcher_dlq.queue_url,
            },
            dead_letter_queue=fb_fetcher_dlq,
        )

        data_processor_fn = _lambda.Function(
            self,
            "DataProcessorFunction",
            function_name="campaign-optimizer-data-processor",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="services.data_processor.lambda_handler",
            code=_lambda.Code.from_asset("../backend"),
            role=data_processor_role,
            timeout=Duration.minutes(10),
            memory_size=512,
            environment=common_env,
        )

        optimizer_fn = _lambda.Function(
            self,
            "OptimizerFunction",
            function_name="campaign-optimizer-optimizer",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="services.optimizer.lambda_handler",
            code=_lambda.Code.from_asset("../backend"),
            role=optimizer_role,
            timeout=Duration.minutes(10),
            memory_size=1024,
            environment=common_env,
        )

        # Provisioned concurrency on optimizer to minimise cold-start latency
        optimizer_version = optimizer_fn.current_version
        _lambda.Alias(
            self,
            "OptimizerProvisionedAlias",
            alias_name="provisioned",
            version=optimizer_version,
            provisioned_concurrent_executions=2,
        )

        notifier_fn = _lambda.Function(
            self,
            "NotifierFunction",
            function_name="campaign-optimizer-notifier",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="services.notifier.lambda_handler",
            code=_lambda.Code.from_asset("../backend"),
            role=notifier_role,
            timeout=Duration.minutes(5),
            memory_size=256,
            environment=common_env,
        )

        dashboard_api_fn = _lambda.Function(
            self,
            "DashboardApiFunction",
            function_name="campaign-optimizer-dashboard-api",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="main.handler",
            code=_lambda.Code.from_asset("../backend"),
            role=dashboard_api_role,
            timeout=Duration.seconds(30),
            memory_size=512,
            environment={
                **common_env,
                "USER_POOL_ID": user_pool.user_pool_id,
                "USER_POOL_CLIENT_ID": user_pool_client.user_pool_client_id,
            },
        )

        # ------------------------------------------------------------------ #
        # EventBridge Rule — cron every 6 hours → fb_fetcher                  #
        # ------------------------------------------------------------------ #
        events.Rule(
            self,
            "FbFetcherSchedule",
            rule_name="campaign-optimizer-fb-fetcher-schedule",
            description="Trigger fb_fetcher Lambda every 6 hours",
            schedule=events.Schedule.cron(minute="0", hour="0/6"),
            targets=[targets.LambdaFunction(fb_fetcher_fn)],
        )

        # ------------------------------------------------------------------ #
        # Step Functions State Machine                                         #
        # Orchestrates: data_processor → optimizer                            #
        # ------------------------------------------------------------------ #

        # Task: invoke data_processor Lambda
        process_task = sfn_tasks.LambdaInvoke(
            self,
            "ProcessDataTask",
            lambda_function=data_processor_fn,
            output_path="$.Payload",
            comment="Validate and normalise raw campaign data",
        )

        # Task: invoke optimizer Lambda
        optimize_task = sfn_tasks.LambdaInvoke(
            self,
            "OptimizeTask",
            lambda_function=optimizer_fn,
            output_path="$.Payload",
            comment="Generate AI-driven recommendations",
        )

        # Task: invoke notifier Lambda
        notify_task = sfn_tasks.LambdaInvoke(
            self,
            "NotifyTask",
            lambda_function=notifier_fn,
            output_path="$.Payload",
            comment="Send alerts for threshold breaches",
        )

        # Chain: process → optimize → notify
        pipeline_definition = process_task.next(optimize_task).next(notify_task)

        # IAM role for the state machine
        state_machine_role = iam.Role(
            self,
            "StateMachineRole",
            role_name="campaign-optimizer-state-machine-role",
            assumed_by=iam.ServicePrincipal("states.amazonaws.com"),
        )
        data_processor_fn.grant_invoke(state_machine_role)
        optimizer_fn.grant_invoke(state_machine_role)
        notifier_fn.grant_invoke(state_machine_role)

        state_machine = sfn.StateMachine(
            self,
            "MLPipelineStateMachine",
            state_machine_name="campaign-optimizer-ml-pipeline",
            definition_body=sfn.DefinitionBody.from_chainable(pipeline_definition),
            role=state_machine_role,
            timeout=Duration.hours(2),
        )

        # S3 event → Step Functions: trigger pipeline when raw data is uploaded
        # We use an EventBridge rule that matches S3 PutObject events on raw_bucket
        pipeline_trigger_role = iam.Role(
            self,
            "PipelineTriggerRole",
            role_name="campaign-optimizer-pipeline-trigger-role",
            assumed_by=iam.ServicePrincipal("events.amazonaws.com"),
        )
        state_machine.grant_start_execution(pipeline_trigger_role)

        events.Rule(
            self,
            "S3RawUploadTrigger",
            rule_name="campaign-optimizer-s3-raw-upload-trigger",
            description="Start ML pipeline when raw data is uploaded to S3",
            event_pattern=events.EventPattern(
                source=["aws.s3"],
                detail_type=["Object Created"],
                detail={
                    "bucket": {"name": [raw_bucket.bucket_name]},
                    "object": {"key": [{"prefix": "raw/"}]},
                },
            ),
            targets=[
                targets.SfnStateMachine(
                    state_machine,
                    role=pipeline_trigger_role,
                )
            ],
        )

        # ------------------------------------------------------------------ #
        # API Gateway — REST API with Cognito JWT authorizer                  #
        # ------------------------------------------------------------------ #
        cognito_authorizer = apigw.CognitoUserPoolsAuthorizer(
            self,
            "CognitoAuthorizer",
            cognito_user_pools=[user_pool],
            authorizer_name="campaign-optimizer-cognito-authorizer",
            identity_source="method.request.header.Authorization",
        )

        api = apigw.RestApi(
            self,
            "CampaignOptimizerApi",
            rest_api_name="campaign-optimizer-api",
            description="AI-Powered Facebook Campaign Optimization REST API",
            default_cors_preflight_options=apigw.CorsOptions(
                allow_origins=apigw.Cors.ALL_ORIGINS,
                allow_methods=apigw.Cors.ALL_METHODS,
                allow_headers=["Authorization", "Content-Type"],
            ),
            deploy_options=apigw.StageOptions(
                stage_name="prod",
                throttling_rate_limit=100,
                throttling_burst_limit=200,
            ),
        )

        # Lambda integration for the dashboard_api (handles all routes via FastAPI)
        dashboard_integration = apigw.LambdaIntegration(
            dashboard_api_fn,
            proxy=True,
        )

        # Proxy all requests to the dashboard_api Lambda
        api.root.add_proxy(
            default_integration=dashboard_integration,
            any_method=True,
            default_method_options=apigw.MethodOptions(
                authorizer=cognito_authorizer,
                authorization_type=apigw.AuthorizationType.COGNITO,
            ),
        )

        # /auth/login is public (no authorizer)
        auth_resource = api.root.add_resource("auth")
        login_resource = auth_resource.add_resource("login")
        login_resource.add_method(
            "POST",
            dashboard_integration,
            authorization_type=apigw.AuthorizationType.NONE,
        )

        # ------------------------------------------------------------------ #
        # Expose key ARNs / names as stack outputs                            #
        # ------------------------------------------------------------------ #
        from aws_cdk import CfnOutput

        CfnOutput(self, "UserPoolId", value=user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=user_pool_client.user_pool_client_id)
        CfnOutput(self, "ApiUrl", value=api.url)
        CfnOutput(self, "RawBucketName", value=raw_bucket.bucket_name)
        CfnOutput(self, "ModelBucketName", value=model_bucket.bucket_name)
        CfnOutput(self, "AdminAlertsTopic", value=admin_alerts_topic.topic_arn)
        CfnOutput(self, "CampaignAlertsTopic", value=campaign_alerts_topic.topic_arn)
        CfnOutput(self, "StateMachineArn", value=state_machine.state_machine_arn)
        CfnOutput(self, "FbFetcherDlqUrl", value=fb_fetcher_dlq.queue_url)

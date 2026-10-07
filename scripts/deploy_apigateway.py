"""Create and Configure API Gateway HTTP API v2 for ReliefTrace in ap-south-1."""
from __future__ import annotations

import json
import boto3

REGION = "ap-south-1"
PROFILE = "FAI-TCE-Builder-AI-314240411685"
API_NAME = "fai-tce-team56-api"
FUNCTION_NAME = "fai-tce-team56-backend"
FUNCTION_ARN = "arn:aws:lambda:ap-south-1:314240411685:function:fai-tce-team56-backend"


def setup_api_gateway():
    session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    apigw = session.client("apigatewayv2", region_name=REGION)
    lam = session.client("lambda", region_name=REGION)

    print("1. Checking for existing HTTP APIs...")
    apis = apigw.get_apis().get("Items", [])
    api = next((a for a in apis if a.get("Name") == API_NAME), None)

    cors_config = {
        "AllowOrigins": ["*"],
        "AllowMethods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "AllowHeaders": ["Content-Type", "Authorization", "X-Request-ID"],
    }

    if api:
        api_id = api["ApiId"]
        print(f"API {API_NAME} already exists (ID: {api_id}). Updating CORS...")
        apigw.update_api(
            ApiId=api_id,
            CorsConfiguration=cors_config,
        )
    else:
        print(f"Creating HTTP API {API_NAME}...")
        res = apigw.create_api(
            Name=API_NAME,
            ProtocolType="HTTP",
            CorsConfiguration=cors_config,
            Description="ReliefTrace Backend API Gateway for Team 56",
        )
        api_id = res["ApiId"]
        print(f"Created API {API_NAME} (ID: {api_id})")

    api_endpoint = f"https://{api_id}.execute-api.{REGION}.amazonaws.com"
    print(f"API Endpoint: {api_endpoint}")

    # 2. Check / Create Lambda Integration
    print("2. Configuring Lambda integration...")
    integrations = apigw.get_integrations(ApiId=api_id).get("Items", [])
    integ = next((i for i in integrations if i.get("IntegrationUri") == FUNCTION_ARN), None)

    if integ:
        integ_id = integ["IntegrationId"]
        print(f"Integration already exists (ID: {integ_id})")
    else:
        print("Creating AWS_PROXY integration with payload format 2.0...")
        integ_res = apigw.create_integration(
            ApiId=api_id,
            IntegrationType="AWS_PROXY",
            IntegrationUri=FUNCTION_ARN,
            PayloadFormatVersion="2.0",
            Description="Lambda integration for ReliefTrace backend",
        )
        integ_id = integ_res["IntegrationId"]
        print(f"Created integration (ID: {integ_id})")

    # 3. Grant Lambda Permission for API Gateway
    print("3. Checking Lambda invoke permissions for API Gateway...")
    try:
        lam.add_permission(
            FunctionName=FUNCTION_NAME,
            StatementId=f"apigw-{api_id}-invoke",
            Action="lambda:InvokeFunction",
            Principal="apigateway.amazonaws.com",
            SourceArn=f"arn:aws:execute-api:{REGION}:314240411685:{api_id}/*",
        )
        print("Granted lambda:InvokeFunction permission to API Gateway.")
    except lam.exceptions.ResourceConflictException:
        print("Lambda invoke permission already exists.")

    # 4. Check / Create Routes
    print("4. Configuring routes ANY / and ANY /{proxy+}...")
    routes = apigw.get_routes(ApiId=api_id).get("Items", [])
    target = f"integrations/{integ_id}"

    for route_key in ("ANY /", "ANY /{proxy+}"):
        existing_route = next((r for r in routes if r.get("RouteKey") == route_key), None)
        if existing_route:
            print(f"Route {route_key} already exists.")
            if existing_route.get("Target") != target:
                apigw.update_route(ApiId=api_id, RouteId=existing_route["RouteId"], Target=target)
        else:
            print(f"Creating route {route_key} -> {target}...")
            apigw.create_route(
                ApiId=api_id,
                RouteKey=route_key,
                Target=target,
            )

    # 5. Check / Create $default Stage
    print("5. Configuring $default stage with AutoDeploy...")
    stages = apigw.get_stages(ApiId=api_id).get("Items", [])
    default_stage = next((s for s in stages if s.get("StageName") == "$default"), None)

    if not default_stage:
        apigw.create_stage(
            ApiId=api_id,
            StageName="$default",
            AutoDeploy=True,
            Description="Default auto-deployed stage",
        )
        print("Created $default stage with AutoDeploy=True")
    else:
        if not default_stage.get("AutoDeploy"):
            apigw.update_stage(ApiId=api_id, StageName="$default", AutoDeploy=True)
        print("$default stage is active with AutoDeploy=True")

    return {
        "api_name": API_NAME,
        "api_id": api_id,
        "api_endpoint": api_endpoint,
        "integration_id": integ_id,
        "routes": ["ANY /", "ANY /{proxy+}"],
        "stage": "$default",
    }


if __name__ == "__main__":
    res = setup_api_gateway()
    print("\nAPI Gateway Setup Complete:")
    print(json.dumps(res, indent=2))

"""Package and Deploy ReliefTrace Backend to AWS Lambda in ap-south-1."""
from __future__ import annotations

import os
import shutil
import zipfile
import time
from pathlib import Path
import boto3

ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = ROOT / "tmp_lambda_build"
ZIP_PATH = ROOT / "tmp_debug" / "relieftrace_lambda.zip"
FUNCTION_NAME = "fai-tce-team56-backend"
ROLE_ARN = "arn:aws:iam::314240411685:role/FAI-TCE-LambdaExecutionRole"
REGION = "ap-south-1"
S3_BUCKET = "fai-tce-team56-images"
S3_KEY = "deployments/relieftrace-backend.zip"

ENV_VARS = {
    "STORAGE_BACKEND": "aws",
    "RT_S3_BUCKET": "fai-tce-team56-images",
    "RT_DYNAMODB_TABLE": "fai-tce-team56-claims",
    "RT_GEO_DIR": "/var/task/data/geo",
    "RT_MAX_UPLOAD_MB": "5",
    "RT_CORS_ORIGINS": "*",
    "BEDROCK_VISION_MODEL_ID": "amazon.nova-lite-v1:0",
    "BEDROCK_TEXT_MODEL_ID": "amazon.nova-micro-v1:0",
    "RT_DB_PATH": "/tmp/reliefTrace.db",
    "RT_S3_DATASET_PREFIX": "dataset/",
}


def prepare_package():
    print(f"Preparing package in {BUILD_DIR}...")
    # Copy backend
    dest_backend = BUILD_DIR / "backend"
    if dest_backend.exists():
        shutil.rmtree(dest_backend)
    shutil.copytree(ROOT / "backend", dest_backend, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"))

    # Copy data/geo
    dest_geo = BUILD_DIR / "data" / "geo"
    dest_geo.parent.mkdir(parents=True, exist_ok=True)
    if dest_geo.exists():
        shutil.rmtree(dest_geo)
    if (ROOT / "data" / "geo").exists():
        shutil.copytree(ROOT / "data" / "geo", dest_geo)

    print("Creating ZIP file...")
    ZIP_PATH.parent.mkdir(parents=True, exist_ok=True)
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(BUILD_DIR):
            for file in files:
                full_path = Path(root) / file
                rel_path = full_path.relative_to(BUILD_DIR)
                zf.write(full_path, rel_path)

    zip_size_mb = ZIP_PATH.stat().st_size / (1024 * 1024)
    print(f"ZIP package created: {ZIP_PATH} ({zip_size_mb:.2f} MB)")
    return ZIP_PATH


def deploy_lambda(session: boto3.Session):
    s3 = session.client("s3", region_name=REGION)
    lam = session.client("lambda", region_name=REGION)

    from boto3.s3.transfer import TransferConfig
    t_config = TransferConfig(multipart_threshold=64 * 1024 * 1024, max_concurrency=2)
    print(f"Uploading ZIP package to s3://{S3_BUCKET}/{S3_KEY}...")
    for attempt in range(1, 5):
        try:
            s3.upload_file(str(ZIP_PATH), S3_BUCKET, S3_KEY, Config=t_config)
            print("Upload complete.")
            break
        except Exception as e:
            print(f"Upload attempt {attempt} failed: {e}")
            if attempt == 4:
                raise
            time.sleep(3)

    existing_fn = None
    try:
        existing_fn = lam.get_function(FunctionName=FUNCTION_NAME)
        print(f"Lambda function {FUNCTION_NAME} already exists. Updating...")
    except lam.exceptions.ResourceNotFoundException:
        print(f"Lambda function {FUNCTION_NAME} does not exist. Creating...")

    if existing_fn:
        # Update function code
        print("Updating Lambda function code...")
        resp = lam.update_function_code(
            FunctionName=FUNCTION_NAME,
            S3Bucket=S3_BUCKET,
            S3Key=S3_KEY,
        )
        print(f"Code update initiated: {resp['LastUpdateStatus']}")

        # Wait for code update to finish
        for _ in range(30):
            fn_desc = lam.get_function(FunctionName=FUNCTION_NAME)["Configuration"]
            if fn_desc.get("LastUpdateStatus") in ("Successful", "Failed"):
                break
            time.sleep(2)

        # Update function configuration
        print("Updating Lambda function configuration...")
        resp = lam.update_function_configuration(
            FunctionName=FUNCTION_NAME,
            Runtime="python3.12",
            Role=ROLE_ARN,
            Handler="backend.main.handler",
            Timeout=60,
            MemorySize=512,
            Environment={"Variables": ENV_VARS},
        )
        print("Configuration update initiated.")
    else:
        print("Creating Lambda function...")
        resp = lam.create_function(
            FunctionName=FUNCTION_NAME,
            Runtime="python3.12",
            Role=ROLE_ARN,
            Handler="backend.main.handler",
            Code={
                "S3Bucket": S3_BUCKET,
                "S3Key": S3_KEY,
            },
            Timeout=60,
            MemorySize=512,
            Environment={"Variables": ENV_VARS},
            Publish=True,
        )
        print("Function creation initiated.")

    # Wait for active state
    print("Waiting for Lambda function to become Active...")
    for _ in range(30):
        fn_desc = lam.get_function(FunctionName=FUNCTION_NAME)["Configuration"]
        state = fn_desc.get("State")
        update_status = fn_desc.get("LastUpdateStatus")
        print(f"State: {state}, LastUpdateStatus: {update_status}")
        if state == "Active" and update_status in ("Successful", None):
            print("Lambda function is Active and Successful!")
            return fn_desc
        time.sleep(2)

    return lam.get_function(FunctionName=FUNCTION_NAME)["Configuration"]


if __name__ == "__main__":
    session = boto3.Session(profile_name="FAI-TCE-Builder-AI-314240411685", region_name=REGION)
    prepare_package()
    res = deploy_lambda(session)
    print("Deployment summary:")
    print(f"Function Name: {res['FunctionName']}")
    print(f"Function ARN: {res['FunctionArn']}")
    print(f"Runtime: {res['Runtime']}")
    print(f"Handler: {res['Handler']}")
    print(f"Memory: {res['MemorySize']} MB")
    print(f"Timeout: {res['Timeout']}s")
    print(f"State: {res['State']}")
    print(f"LastUpdateStatus: {res.get('LastUpdateStatus')}")

"""Upload dataset SQLite database and challenge reference images to S3."""
from __future__ import annotations

import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import boto3

ROOT = Path(__file__).resolve().parent.parent

BUCKET = "fai-tce-team56-images"
REGION = "ap-south-1"
PREFIX = "dataset/"


def upload_file_if_needed(s3, local_path: Path, bucket: str, key: str, force: bool = False) -> bool:
    if not local_path.exists():
        print(f"Skipping missing file: {local_path}")
        return False
    size = local_path.stat().st_size
    if not force:
        try:
            head = s3.head_object(Bucket=bucket, Key=key)
            if head.get("ContentLength") == size:
                return False  # Already uploaded
        except Exception:
            pass  # Does not exist, upload
    content_type = "application/x-sqlite3" if local_path.suffix == ".db" else "image/jpeg"
    s3.upload_file(
        str(local_path),
        bucket,
        key,
        ExtraArgs={"ContentType": content_type},
    )
    return True


def main():
    parser = argparse.ArgumentParser(description="Upload ReliefTrace dataset to private S3 bucket")
    parser.add_argument("--profile", default="FAI-TCE-Builder-AI-314240411685")
    parser.add_argument("--bucket", default=BUCKET)
    parser.add_argument("--region", default=REGION)
    parser.add_argument("--prefix", default=PREFIX)
    parser.add_argument("--all-images", action="store_true", help="Upload all images in data/images")
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    s3 = session.client("s3")

    db_path = ROOT / "data" / "processed" / "reliefTrace.db"
    if not db_path.exists():
        print(f"ERROR: Dataset database not found at {db_path}", file=sys.stderr)
        return 1

    prefix = args.prefix.strip("/")
    # 1. Upload SQLite Database
    print(f"Uploading SQLite database {db_path} ({db_path.stat().st_size / (1024*1024):.2f} MB)...")
    db_keys = [
        f"{prefix}/metadata/reliefTrace.db",
        f"{prefix}/reliefTrace.db",
    ]
    for k in db_keys:
        print(f"  -> s3://{args.bucket}/{k}")
        upload_file_if_needed(s3, db_path, args.bucket, k, force=True)
    print("Database upload complete.")

    # 2. Upload Key Demo Images
    demo_image_names = [
        "642627_371___2fec8fab4a7055ce-43514-14060200521558-5596_318379_2024_11_12_15_37_44.jpg",
        "01098ba2-7e27-4c75-8f93-39c2c9c9f51b642626_293_58_.jpg",
        "01198bd8-1ddd-48b0-8dd0-a238df563ecd933536_696_58_.jpg",
        "00b38c78-9ef3-4568-b254-eb895b6b629f933533_266_58_.jpg",
    ]

    images_dir = ROOT / "data" / "images"
    uploaded_count = 0

    print("Uploading demo reference images...")
    for name in demo_image_names:
        p = images_dir / name
        if p.exists():
            key = f"{prefix}/images/{name}"
            if upload_file_if_needed(s3, p, args.bucket, key, force=True):
                print(f"  Uploaded: s3://{args.bucket}/{key}")
                uploaded_count += 1
            # Also upload by image ID alias for 2fec8fab4a7055ce-43514-14060200521558
            if "2fec8fab4a7055ce-43514-14060200521558" in name:
                id_alias_key = f"{prefix}/images/2fec8fab4a7055ce-43514-14060200521558.jpg"
                upload_file_if_needed(s3, p, args.bucket, id_alias_key, force=True)
                print(f"  Uploaded alias: s3://{args.bucket}/{id_alias_key}")

    # 3. Upload all images if requested or by default in parallel
    if args.all_images or True:
        all_imgs = list(images_dir.glob("*.jpg")) + list(images_dir.glob("*.png")) + list(images_dir.glob("*.jpeg"))
        print(f"Syncing remaining reference images ({len(all_imgs)} files) with 20 threads...")
        def _upload(p: Path):
            k = f"{prefix}/images/{p.name}"
            try:
                upload_file_if_needed(s3, p, args.bucket, k)
                return True
            except Exception as e:
                return False

        with ThreadPoolExecutor(max_workers=20) as pool:
            futures = [pool.submit(_upload, p) for p in all_imgs]
            done = 0
            for f in as_completed(futures):
                done += 1
                if done % 500 == 0 or done == len(all_imgs):
                    print(f"  Processed {done}/{len(all_imgs)} images...")

    print("S3 Dataset upload finished successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

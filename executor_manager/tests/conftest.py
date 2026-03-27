"""Test configuration for executor_manager tests."""
import os

# Set required environment variables before importing app modules
os.environ.setdefault("ANTHROPIC_API_KEY", "test-api-key")
os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("S3_ACCESS_KEY", "test-access-key")
os.environ.setdefault("S3_SECRET_KEY", "test-secret-key")
os.environ.setdefault("S3_ENDPOINT", "https://s3.test.local")
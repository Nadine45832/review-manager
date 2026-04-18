import os

import boto3
from dotenv import load_dotenv


load_dotenv()


def _aws_config(region_name: str | None = None) -> dict:
    config = {
        "region_name": region_name or os.environ.get("AWS_REGION", "us-east-1"),
    }

    access_key = os.environ.get("AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY")
    session_token = os.environ.get("AWS_SESSION_TOKEN")

    if access_key and secret_key:
        config["aws_access_key_id"] = access_key
        config["aws_secret_access_key"] = secret_key
        if session_token:
            config["aws_session_token"] = session_token

    return config


def aws_client(service_name: str, region_name: str | None = None):
    return boto3.client(service_name, **_aws_config(region_name))


def aws_resource(service_name: str, region_name: str | None = None):
    return boto3.resource(service_name, **_aws_config(region_name))

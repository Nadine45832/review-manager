import logging

from botocore.exceptions import ClientError
from chalicelib.aws_client_factory import aws_client

logger = logging.getLogger(__name__)


class StorageService:

    def __init__(self, storage_location):
        self.client = aws_client("s3", region_name="us-east-1")
        self.bucket_name = storage_location

    def get_storage_location(self):
        return self.bucket_name

    def upload_file(
        self,
        file_bytes,
        file_name,
        content_type=None,
        is_public=False
    ):
        """
        Upload raw bytes to S3 and return a URL to access the file.

        Args:
            file_bytes: File content as bytes.
            file_name: S3 key (path within the bucket).
            content_type: Optional MIME type string.
            is_public: If True, return a permanent public URL.
            If False, return a pre-signed URL (1 hour).

        Returns:
            dict: { "fileId": <s3_key>, "fileUrl": <url> }
        """
        put_params = {
            "Bucket": self.bucket_name,
            "Key": file_name,
            "Body": file_bytes,
        }
        if is_public:
            put_params["ACL"] = "public-read"
        if content_type:
            put_params["ContentType"] = content_type

        try:
            self.client.put_object(**put_params)
            logger.info(f"Uploaded '{file_name}' to s3://{self.bucket_name}/")

            if is_public:
                file_url = (
                    f"https://{self.bucket_name}.s3.amazonaws.com/{file_name}"
                )
            else:
                file_url = self.client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket_name, "Key": file_name},
                    ExpiresIn=3600,
                )

            return {"fileId": file_name, "fileUrl": file_url}

        except ClientError as e:
            logger.error(f"Failed to upload '{file_name}': {e}")
            raise

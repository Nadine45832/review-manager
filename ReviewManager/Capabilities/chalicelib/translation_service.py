import logging

from botocore.exceptions import ClientError
from chalicelib.aws_client_factory import aws_client

logger = logging.getLogger(__name__)


class TranslationService:

    def __init__(self):
        self.client = aws_client("translate", region_name="us-east-1")

    def translate_text(
        self,
        text,
        source_language="auto",
        target_language="en"
    ):
        """
        Translate text from source_language to target_language.

        Args:
            text: The text to translate.
            source_language: BCP-47 code of the source language, or 'auto' for
                              automatic detection by AWS Translate.
            target_language: BCP-47 code of the desired output language.

        Returns:
            dict with keys:
                translated_text
                source_language_code
        """
        if not text or not text.strip():
            return {
                "translated_text": "",
                "source_language_code": source_language
            }

        # AWS Translate uses 'auto' the same way we do
        try:
            response = self.client.translate_text(
                Text=text,
                SourceLanguageCode=source_language,
                TargetLanguageCode=target_language,
            )
            return {
                "translated_text": response["TranslatedText"],
                "source_language_code": response["SourceLanguageCode"],
            }
        except ClientError as e:
            logger.error(f"Translation error: {e}")
            raise

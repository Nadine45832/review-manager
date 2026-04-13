import json
import logging
import time
import uuid

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = {
    "en": "en-US",
    "fr": "fr-FR",
    "es": "es-ES",
    "de": "de-DE",
    "it": "it-IT",
    "pt": "pt-BR",
    "ja": "ja-JP",
    "zh": "zh-CN",
    "ko": "ko-KR",
    "ar": "ar-SA",
    "hi": "hi-IN",
    "ru": "ru-RU",
}

DEFAULT_LANGUAGE = "en-US"


class SpeechRecognitionService:

    def __init__(self, storage_location):
        self.client = boto3.client("transcribe", "us-east-1")
        self.s3_client = boto3.client("s3", "us-east-1")
        self.bucket_name = storage_location

    def _get_language_code(self, language_hint):
        """Map short language code (e.g. 'fr')
        to BCP-47 tag AWS Transcribe needs."""
        if not language_hint or language_hint == "auto":
            return None  # Triggers automatic identification
        # Accept both 'fr' and 'fr-FR' style codes
        base = language_hint.split("-")[0].lower()
        return SUPPORTED_LANGUAGES.get(base, DEFAULT_LANGUAGE)

    def transcribe_audio(self, file_name, language_hint="auto", timeout=120):
        """
        Start an AWS Transcribe job for the given S3
        object and wait for it to finish.

        Args:
            file_name: S3 key of the uploaded audio file.
            language_hint: Short language code or 'auto'
            for automatic detection.
            timeout: Max seconds to wait for the job (default 120).

        Returns:
            dict with keys:
                transcript
                detected_language
                confidence – average word confidence (0–1), or None
        """
        job_name = f"review-transcribe-{uuid.uuid4().hex}"
        audio_uri = f"s3://{self.bucket_name}/{file_name}"

        start_params = {
            "TranscriptionJobName": job_name,
            "Media": {"MediaFileUri": audio_uri},
            "OutputBucketName": self.bucket_name,
            "OutputKey": f"transcripts/{job_name}.json",
        }

        language_code = self._get_language_code(language_hint)
        if language_code:
            start_params["LanguageCode"] = language_code
        else:
            # Let Transcribe auto-detect among common languages
            start_params["IdentifyLanguage"] = True
            start_params["LanguageOptions"] = list(
                SUPPORTED_LANGUAGES.values())

        try:
            self.client.start_transcription_job(**start_params)
            logger.info(
                f"Transcription job '{job_name}' started for '{file_name}'.")
        except ClientError as e:
            logger.error(f"Failed to start transcription job: {e}")
            raise

        # Poll until completed or failed
        elapsed = 0
        poll_interval = 5
        while elapsed < timeout:
            time.sleep(poll_interval)
            elapsed += poll_interval

            try:
                response = self.client.get_transcription_job(
                    TranscriptionJobName=job_name
                )
                status = response["TranscriptionJob"]["TranscriptionJobStatus"]
            except ClientError as e:
                logger.error(f"Error polling transcription job: {e}")
                raise

            if status == "COMPLETED":
                return self._parse_transcript(
                    response["TranscriptionJob"], job_name)
            elif status == "FAILED":
                reason = response["TranscriptionJob"].get(
                    "FailureReason", "Unknown")
                raise RuntimeError(f"Transcription job failed: {reason}")

        raise TimeoutError(
            f"Transcription job '{job_name}' "
            f"did not complete within {timeout}s."
        )

    def _parse_transcript(self, job, job_name):
        """Download and parse the Transcribe JSON output from S3."""
        output_key = f"transcripts/{job_name}.json"
        try:
            obj = self.s3_client.get_object(
                Bucket=self.bucket_name, Key=output_key)

            result = json.loads(
                obj["Body"].read()
            )
        except ClientError as e:
            logger.error(f"Could not retrieve transcript JSON: {e}")
            raise

        transcripts = result.get("results", {}).get("transcripts", [])
        transcript_text = transcripts[0].get(
            "transcript", "") if transcripts else ""

        # Compute average word confidence
        items = result.get("results", {}).get("items", [])
        confidences = [
            float(i["alternatives"][0]["confidence"])
            for i in items
            if i.get("type") == "pronunciation"
            and i.get("alternatives")
            and "confidence" in i["alternatives"][0]
        ]
        avg_confidence = (
            sum(confidences) / len(confidences)) if confidences else None

        # Detected language
        detected_language = job.get("LanguageCode", "en-US")

        logger.info(
            f"Transcript ready. Language: {detected_language}, "
            f"Confidence: {avg_confidence:.3f}"
            if avg_confidence
            else "N/A"
        )

        return {
            "transcript": transcript_text,
            "detected_language": detected_language,
            "confidence": avg_confidence,
        }

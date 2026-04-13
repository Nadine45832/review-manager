import base64

import logging
import os
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from chalice import Chalice, Response
from chalicelib.storage_service import StorageService
from chalicelib.translation_service import TranslationService
from dotenv import load_dotenv
from utils.helpers import (
    extract_reviews_from_csv, error_response,
    POLLY_VOICES, build_audio_summary_text,
    normalize_lang_code, analyze_text,
    prepare_review_record
)

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Chalice(app_name="review_manager")
app.debug = True

BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "review-manager-bucket")
DEFAULT_TARGET_LANG = os.environ.get("DEFAULT_TARGET_LANG", "en")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

storage_service = StorageService(BUCKET_NAME)
translation_service = TranslationService()
polly_client = boto3.client("polly", region_name=AWS_REGION)

# Simple in-memory store for the current runtime.
# Good for local/dev use. For production, move this to DynamoDB or another DB.
BATCHES: Dict[str, Dict[str, Any]] = {}


@app.route("/ui", methods=["GET"])
def serve_ui():
    with open("Website/index.html", "r", encoding="utf-8") as f:
        html = f.read()
    return Response(
        body=html,
        status_code=200,
        headers={"Content-Type": "text/html; charset=utf-8"},
    )


@app.route("/scripts.js", methods=["GET"])
def serve_scripts():
    with open("Website/scripts.js", "r", encoding="utf-8") as f:
        js = f.read()
    return Response(
        body=js,
        status_code=200,
        headers={"Content-Type": "application/javascript; charset=utf-8"},
    )


@app.route("/")
def index():
    return {
        "status": "Review Manager is running.",
        "features": [
            "csv_upload",
            "translation",
            "sentiment_analysis",
            "audio_summary",
        ],
    }


@app.route(
    "/reviews/upload", methods=["POST"], content_types=["application/json"]
)
def upload_reviews():
    payload = app.current_request.json_body or {}

    target_lang = normalize_lang_code(payload.get(
        "target_lang") or DEFAULT_TARGET_LANG)
    reviews: List[str] = []
    original_filename = payload.get("filename", "reviews.csv")

    # Preferred flow: upload the CSV file and let the service read it.
    if payload.get("filebytes"):
        try:
            csv_bytes = base64.b64decode(payload["filebytes"])
        except Exception as exc:
            return error_response(f"Invalid base64 file payload: {exc}", 400)
        reviews = extract_reviews_from_csv(csv_bytes)

    elif isinstance(payload.get("reviews"), list):
        reviews = [
            str(item).strip()
            for item in payload["reviews"]
            if str(item).strip()
        ]
    else:
        return error_response(
            "Provide either filebytes for a CSV file or a reviews array.", 400
        )

    if not reviews:
        return error_response(
            "No reviews were found in the uploaded CSV file.", 400)

    translated_reviews = [
        prepare_review_record(text, target_lang) for text in reviews]
    batch_id = f"batch-{uuid.uuid4().hex}"

    BATCHES[batch_id] = {
        "id": batch_id,
        "filename": original_filename,
        "target_lang": target_lang,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "translated_reviews": translated_reviews,
    }

    logger.info(
        "Created batch %s with %s reviews", batch_id, len(translated_reviews))
    return {
        "batch_id": batch_id,
        "review_count": len(translated_reviews),
        "translated_reviews": translated_reviews,
    }


@app.route(
    "/reviews/{batch_id}/analyze",
    methods=["POST"],
    content_types=["application/json"]
)
def analyze_reviews(batch_id: str):
    batch = BATCHES.get(batch_id)
    if not batch:
        return error_response("Batch not found.", 404)

    translated_reviews = batch["translated_reviews"]
    results = []
    phrase_counter: Counter[str] = Counter()
    summary_counter: Counter[str] = Counter()

    for item in translated_reviews:
        text_for_analysis = item["translated"] or item["original"]
        analysis = analyze_text(text_for_analysis, batch["target_lang"])
        sentiment = analysis["sentiment"]
        key_phrases = analysis["key_phrases"]

        summary_counter[sentiment] += 1
        phrase_counter.update(key_phrases)

        results.append(
            {
                "text": text_for_analysis,
                "sentiment": sentiment,
                "sentiment_scores": analysis["sentiment_scores"],
                "key_phrases": key_phrases,
            }
        )

    response = {
        "batch_id": batch_id,
        "summary": {
            "total": len(results),
            "positive": summary_counter.get("POSITIVE", 0),
            "negative": summary_counter.get("NEGATIVE", 0),
            "neutral": summary_counter.get("NEUTRAL", 0),
            "mixed": summary_counter.get("MIXED", 0),
        },
        "results": results,
        "key_phrases": [
            phrase for phrase, _ in phrase_counter.most_common(20)
        ],
    }

    batch["analysis"] = response
    return response


@app.route(
    "/reviews/{batch_id}/audio-summary",
    methods=["POST"],
    content_types=["application/json"],
)
def create_audio_summary(batch_id: str):
    batch = BATCHES.get(batch_id)
    if not batch:
        return error_response("Batch not found.", 404)

    analysis = batch.get("analysis")
    if not analysis:
        return error_response(
            "Run analysis before generating the audio summary.", 400)

    payload = app.current_request.json_body or {}
    language_code = normalize_lang_code(
        payload.get("language_code") or batch.get("target_lang") or "en"
    )
    summary_text = build_audio_summary_text(analysis, language_code)

    try:
        voice_id = POLLY_VOICES.get(language_code, POLLY_VOICES["en"])
        polly_response = polly_client.synthesize_speech(
            Text=summary_text,
            OutputFormat="mp3",
            VoiceId=voice_id,
            Engine="neural",
        )
        audio_bytes = polly_response["AudioStream"].read()
    except (ClientError, BotoCoreError, KeyError) as exc:
        logger.exception("Failed to generate audio summary for %s", batch_id)
        return error_response(f"Failed to generate audio summary: {exc}", 500)

    audio_key = f"audio-summaries/{batch_id}-{language_code}.mp3"
    upload_info = storage_service.upload_file(
        audio_bytes,
        audio_key,
        content_type="audio/mpeg",
        is_public=False,
    )

    response = {
        "batch_id": batch_id,
        "audio_url": upload_info["fileUrl"],
        "audio_file_id": upload_info["fileId"],
        "summary_text": summary_text,
    }
    batch["audio_summary"] = response
    return response


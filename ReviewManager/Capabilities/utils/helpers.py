import csv
import io
import json
import logging
import os

from typing import Any, Dict, List

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from chalicelib.translation_service import TranslationService
from chalice import Response


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BUCKET_NAME = os.environ.get("S3_BUCKET_NAME", "review-manager-bucket")
DEFAULT_TARGET_LANG = os.environ.get("DEFAULT_TARGET_LANG", "en")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

translation_service = TranslationService()
comprehend_client = boto3.client("comprehend", region_name=AWS_REGION)


SUPPORTED_REVIEW_COLUMNS = [
    "review_text",
    "review",
    "text",
    "comment",
    "feedback",
    "body",
    "content",
    "message",
]

POLLY_VOICES = {
    "en": "Joanna",
    "fr": "Lea",
    "es": "Lucia",
    "de": "Vicki",
    "it": "Bianca",
    "pt": "Camila",
}


def error_response(
    message: str, status_code: int
) -> Response:
    return Response(
        body=json.dumps({"error": message}),
        status_code=status_code,
        headers={"Content-Type": "application/json"},
    )


def normalize_lang_code(language_code: str) -> str:
    value = (language_code or "en").strip().lower()
    return value.split("-")[0] if value else "en"


def extract_reviews_from_csv(csv_bytes: bytes) -> List[str]:
    text = csv_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise ValueError("CSV file is empty or missing a header row.")

    normalized_map = {
        field.strip().lower(): field for field in reader.fieldnames if field
    }
    review_column = next(
        (
            normalized_map[col]
            for col in SUPPORTED_REVIEW_COLUMNS
            if col in normalized_map
        ),
        None,
    )

    if not review_column:
        raise ValueError(
            "No review column found. Expected one of: "
            + ", ".join(SUPPORTED_REVIEW_COLUMNS)
        )

    reviews: List[str] = []
    for row in reader:
        value = (row.get(review_column) or "").strip()
        if value:
            reviews.append(value)
    return reviews


def prepare_review_record(
    review_text: str,
    target_lang: str
) -> Dict[str, Any]:
    detected_language = detect_language(review_text)
    source_language = normalize_lang_code(detected_language)
    should_translate = source_language != target_lang

    translated_text = review_text
    if should_translate:
        try:
            translation = translation_service.translate_text(
                text=review_text,
                source_language=source_language,
                target_language=target_lang,
            )
            translated_text = translation.get("translated_text", review_text)
            source_language = normalize_lang_code(
                translation.get("source_language_code", source_language)
            )
        except Exception:
            logger.exception("Translation failed, using original text.")
            translated_text = review_text
            should_translate = False

    return {
        "original": review_text,
        "translated": translated_text,
        "source_language": source_language,
        "target_language": target_lang,
        "was_translated": should_translate,
    }


def detect_language(text: str) -> str:
    try:
        response = comprehend_client.detect_dominant_language(Text=text[:5000])
        languages = response.get("Languages", [])
        if languages:
            return languages[0].get("LanguageCode", "en")
    except (ClientError, BotoCoreError):
        logger.exception("Language detection failed; defaulting to English.")
    return "en"


def analyze_text(text: str, language_code: str) -> Dict[str, Any]:
    safe_text = text[:5000]
    lang = normalize_lang_code(language_code)
    sentiment = "NEUTRAL"
    sentiment_scores: Dict[str, float] = {}
    key_phrases: List[str] = []

    try:
        sentiment_response = comprehend_client.detect_sentiment(
            Text=safe_text, LanguageCode=lang
        )
        sentiment = sentiment_response.get("Sentiment", "NEUTRAL")
        sentiment_scores = sentiment_response.get("SentimentScore", {})
    except (ClientError, BotoCoreError):
        logger.exception(
            "Sentiment analysis failed for text: %s", safe_text[:100])

    try:
        phrases_response = comprehend_client.detect_key_phrases(
            Text=safe_text, LanguageCode=lang
        )
        key_phrases = [
            phrase.get("Text", "")
            for phrase in phrases_response.get("KeyPhrases", [])
            if phrase.get("Text")
        ]
    except (ClientError, BotoCoreError):
        logger.exception(
            "Key phrase extraction failed for text: %s", safe_text[:100])

    return {
        "sentiment": sentiment,
        "sentiment_scores": sentiment_scores,
        "key_phrases": key_phrases,
    }


def build_audio_summary_text(
    analysis: Dict[str, Any], language_code: str
) -> str:
    summary = analysis["summary"]
    key_phrases = analysis.get("key_phrases", [])[:5]
    phrase_text = (
        ", ".join(key_phrases)
        if key_phrases
        else "no dominant repeated phrases"
    )

    if normalize_lang_code(language_code) == "fr":
        return (
            f"Analyse terminée. {summary['total']} avis au total. "
            f"{summary['positive']} positifs, {summary['negative']} négatifs, "
            f"{summary['neutral']} neutres et {summary['mixed']} mitigés. "
            f"Principaux sujets: {phrase_text}."
        )
    if normalize_lang_code(language_code) == "es":
        return (
            f"Análisis completado. {summary['total']} reseñas en total."
            f"{summary['positive']} "
            f"positivas, {summary['negative']} negativas,"
            f"{summary['neutral']} neutrales y {summary['mixed']} mixtas. "
            f"Temas principales: {phrase_text}."
        )

    return (
        f"Analysis complete. {summary['total']} reviews processed. "
        f"{summary['positive']} positive, {summary['negative']} negative, "
        f"{summary['neutral']} neutral, and {summary['mixed']} mixed. "
        f"Top themes: {phrase_text}."
    )

# Review Manager

Review Manager is a Chalice-based web app for hotel review processing.

## What it does

The user uploads a CSV file with reviews. The service then:
1. reads the CSV on the backend,
2. detects the language of each review,
3. translates non-target-language reviews,
4. runs sentiment and key phrase analysis,
5. generates an audio summary.

Supported CSV header names include:
- `review_text`
- `review`
- `text`
- `comment`
- `feedback`
- `body`
- `content`
- `message`

## AWS services used

- Amazon Translate
- Amazon Comprehend
- Amazon Polly
- Amazon S3
- Amazon DynamoDB (optional persistence for review batches)

## How to run locally

### 1. Go to the Chalice app folder

```bash
cd ReviewManager/Capabilities
```

### 2. Create and activate a virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Create a `.env` file

Example:

```env
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_SESSION_TOKEN=optional_if_needed
S3_BUCKET_NAME=your-s3-bucket-name
DEFAULT_TARGET_LANG=en
DDB_TABLE_NAME=hotel-review
```

Your S3 bucket must already exist, and your AWS user/role must have permission to use:
- S3
- Translate
- Comprehend
- Polly
- DynamoDB if you want batch persistence after restarts

### 5. Optional DynamoDB setup

If you want uploaded batches to persist after the local server restarts, create a DynamoDB table with:

- Table name: `hotel-review` (or any name you prefer)
- Partition key: `id`
- Partition key type: `String`
- Region: the same AWS region you use in `AWS_REGION`

Then set the same table name in your `.env`:

```env
DDB_TABLE_NAME=hotel-review (or the name you used)
```

When DynamoDB is configured, the app stores:

- batch metadata
- original and translated review text
- sentiment/key phrase analysis results
- audio summary metadata

If `DDB_TABLE_NAME` is not set, the app still works and falls back to in-memory batch storage.

### 6. Run the app

```bash
chalice local
```

By default, Chalice starts a local server at:

```text
http://127.0.0.1:8000
```

Open the UI here:

```text
http://127.0.0.1:8000/ui
```

## Main API endpoints

- `POST /reviews/upload`
  - accepts a base64 CSV file and target language
- `POST /reviews/{batch_id}/analyze`
  - runs sentiment analysis and key phrase extraction
- `POST /reviews/{batch_id}/audio-summary`
  - creates an MP3 summary and stores it in S3

## Expected request for CSV upload

```json
{
  "filename": "reviews.csv",
  "filebytes": "<base64-csv-content>",
  "target_lang": "en"
}
```

## Notes

- Batch data is stored in memory by default.
- If DynamoDB is configured, the app also stores batches there so they survive server restarts.
- The frontend now sends the CSV file to the backend, and the backend reads and parses it.

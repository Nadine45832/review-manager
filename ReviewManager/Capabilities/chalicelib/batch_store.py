import logging

from botocore.exceptions import BotoCoreError, ClientError
from chalicelib.aws_client_factory import aws_resource


logger = logging.getLogger(__name__)


class BatchStore:
    def __init__(self, table_name: str, region_name: str = "us-east-1"):
        self.table_name = table_name
        self.dynamodb = aws_resource("dynamodb", region_name=region_name)
        self.table = self.dynamodb.Table(table_name)

    def save_batch(self, batch: dict) -> None:
        self.table.put_item(Item=batch)

    def get_batch(self, batch_id: str) -> dict | None:
        response = self.table.get_item(Key={"id": batch_id})
        return response.get("Item")

    def update_analysis(self, batch_id: str, analysis: dict) -> None:
        self.table.update_item(
            Key={"id": batch_id},
            UpdateExpression="SET #analysis = :analysis",
            ExpressionAttributeNames={"#analysis": "analysis"},
            ExpressionAttributeValues={":analysis": analysis},
        )

    def update_audio_summary(self, batch_id: str, audio_summary: dict) -> None:
        self.table.update_item(
            Key={"id": batch_id},
            UpdateExpression="SET audio_summary = :audio_summary",
            ExpressionAttributeValues={":audio_summary": audio_summary},
        )

    def is_available(self) -> bool:
        try:
            self.table.load()
            return True
        except (ClientError, BotoCoreError):
            logger.exception(
                "DynamoDB table '%s' is not available.", self.table_name
            )
            return False

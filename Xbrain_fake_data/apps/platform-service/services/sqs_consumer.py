import asyncio
import json
import logging
from typing import Awaitable, Callable
import boto3
from config import config

logger = logging.getLogger(__name__)

MessageHandler = Callable[[dict], Awaitable[None]]


class SQSConsumer:
    """
    SRP: Chỉ chịu trách nhiệm poll message từ SQS và xóa message sau khi xử lý.
         Không biết gì về business logic của incident.

    DIP: Nhận message_handler là một async callable từ bên ngoài,
         không tự gọi IncidentService trực tiếp.

    OCP: Thay đổi cách xử lý message chỉ cần truyền handler khác vào —
         không cần sửa class này.
    """

    def __init__(self, message_handler: MessageHandler) -> None:
        self._handler = message_handler
        self._sqs = boto3.client("sqs", region_name=config.AWS_REGION)

    async def poll(self) -> None:
        """Vòng lặp vô hạn poll message từ SQS."""
        while True:
            try:
                response = await asyncio.to_thread(
                    self._sqs.receive_message,
                    QueueUrl=config.SQS_QUEUE_URL,
                    MaxNumberOfMessages=1,
                    WaitTimeSeconds=10,  # Long-polling
                )
                if "Messages" in response:
                    for msg in response["Messages"]:
                        body = json.loads(msg["Body"])
                        await self._handler(body)
                        await asyncio.to_thread(
                            self._sqs.delete_message,
                            QueueUrl=config.SQS_QUEUE_URL,
                            ReceiptHandle=msg["ReceiptHandle"],
                        )
            except Exception as e:
                logger.error(f"SQS polling error: {e}")
            await asyncio.sleep(1)
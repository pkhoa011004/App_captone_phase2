"""
tests/test_sqs_consumer.py

Tests cho SQSConsumer — dùng moto để mock AWS SQS thật.
"""
import asyncio
import json
import pytest
from moto import mock_aws
from unittest.mock import AsyncMock, patch
from services.sqs_consumer import SQSConsumer


pytestmark = pytest.mark.anyio


class TestSQSConsumer:

    async def test_handler_called_with_message_body(self, mock_sqs_queue, mock_incident_payload):
        """Consumer phải parse body JSON và gọi handler với dict đúng."""
        sqs, queue_url = mock_sqs_queue
        handler = AsyncMock()
        consumer = SQSConsumer(message_handler=handler)

        with mock_aws():
            sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(mock_incident_payload))
            response = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=0)
            if "Messages" in response:
                for msg in response["Messages"]:
                    body = json.loads(msg["Body"])
                    await consumer._handler(body)

        handler.assert_called_once_with(mock_incident_payload)

    async def test_poll_deletes_message_after_handling(self, mock_sqs_queue, mock_incident_payload):
        """Sau khi xử lý, message phải bị xóa khỏi queue."""
        sqs, queue_url = mock_sqs_queue
        handler = AsyncMock()
        consumer = SQSConsumer(message_handler=handler)

        with mock_aws():
            sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(mock_incident_payload))
            response = sqs.receive_message(
                QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=0
            )
            if "Messages" in response:
                for msg in response["Messages"]:
                    body = json.loads(msg["Body"])
                    await consumer._handler(body)
                    sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=msg["ReceiptHandle"])

            leftover = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=0)
            assert "Messages" not in leftover
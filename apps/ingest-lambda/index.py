import json
import os
import boto3
import uuid

# Khởi tạo client SQS
sqs = boto3.client('sqs')
QUEUE_URL = os.environ.get('SQS_QUEUE_URL')

def handler(event, context):
    print("Received Webhook from Alertmanager:", json.dumps(event))
    
    try:
        # Lấy phần thân của HTTP Request
        body = event.get('body', '{}')
        
        if not QUEUE_URL:
            print("SQS_QUEUE_URL is not set. Mock mode.")
            return {"statusCode": 200, "body": json.dumps({"message": "Mock ingested"})}
            
        # Ném ngay vào SQS FIFO
        response = sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=body,
            MessageGroupId="alertmanager-webhook-group", # Cần thiết cho queue FIFO
            MessageDeduplicationId=str(uuid.uuid4()) # Tránh trùng lặp tin nhắn
        )
        
        print("Successfully sent to SQS. MessageId:", response.get('MessageId'))
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Alert queued successfully!", "messageId": response.get('MessageId')})
        }
        
    except Exception as e:
        print("Error sending to SQS:", str(e))
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }

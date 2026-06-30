import json
import uuid
import boto3
import argparse
from datetime import datetime, timezone

def main():
    parser = argparse.ArgumentParser(description="Inject a simulated alert directly into the Sandbox SQS Queue.")
    parser.add_argument("--queue-url", default="https://sqs.ap-southeast-1.amazonaws.com/458580846647/xbrain-cdo5-sandbox-incident-queue.fifo", help="SQS Queue URL")
    parser.add_argument("--region", default="ap-southeast-1", help="AWS Region")
    parser.add_argument("--incident-id", default=f"INC-{uuid.uuid4().hex[:8].upper()}", help="Incident ID")
    args = parser.parse_args()

    # Tạo một TriageRequest mẫu theo đúng schema
    now_utc = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    payload = {
        "correlation_id": uuid.uuid4().hex,
        "tenant_id": "xbrain-cdo5",
        "incident_id": args.incident_id,
        "environment": "sandbox",
        "received_at": now_utc,
        "alert": {
            "alert_id": f"ALT-{uuid.uuid4().hex[:6].upper()}",
            "source": "prometheus",
            "service": "payment-gateway",
            "severity": "critical",
            "title": "High Latency Detected in Payment Gateway",
            "description": "The 99th percentile latency of the payment-gateway service has exceeded 2000ms for the last 5 minutes. This might indicate a degradation in downstream processing or database connection saturation.",
            "started_at": now_utc,
            "labels": {
                "team": "core-payments",
                "region": "ap-southeast-1"
            }
        },
        "metrics": [
            {
                "metric_name": "payment_latency_p99",
                "service": "payment-gateway",
                "unit": "ms",
                "points": [
                    {
                        "ts": now_utc,
                        "value": 2540.5
                    }
                ]
            }
        ],
        "logs": [
            {
                "service": "payment-gateway",
                "ts": now_utc,
                "level": "error",
                "message": "Connection pool exhausted",
                "trace_id": uuid.uuid4().hex[:8]
            }
        ],
        "traces": [],
        "recent_deploys": [
            {
                "service": "payment-gateway",
                "version": "v1.4.2",
                "deployed_at": "2026-06-29T10:00:00Z"
            }
        ]
    }

    print(f"Preparing to send simulated TriageRequest to SQS: {args.queue_url}")
    print(f"Incident ID: {args.incident_id}")
    
    sqs = boto3.client('sqs', region_name=args.region)
    
    message_group_id = args.incident_id
    message_deduplication_id = uuid.uuid4().hex

    try:
        response = sqs.send_message(
            QueueUrl=args.queue_url,
            MessageBody=json.dumps(payload),
            MessageGroupId=message_group_id,
            MessageDeduplicationId=message_deduplication_id
        )
        print(f"✅ Message successfully sent to SQS.")
        print(f"Message ID: {response.get('MessageId')}")
        print("\n⏳ Now check the logs of tf1-platform-service and tf1-ai-engine on your Kubernetes cluster.")
    except Exception as e:
        print(f"❌ Failed to send message to SQS: {e}")

if __name__ == "__main__":
    main()

import json
import time
import httpx
import asyncio
from datetime import datetime

METRICS_FILE = r"apps/simulator/fake-data/evidence/metrics/scenario-4-disk-saturation.json"
LOGS_FILE = r"apps/simulator/fake-data/evidence/logs/scenario-4-disk-saturation.json"

TARGET_URL = "http://localhost:8080/dumbproxy/inject-batch"

async def main():
    print("=== SCENARIO 4: DISK SPACE SATURATION TEST ===")
    
    # Load files
    with open(METRICS_FILE, "r") as f:
        metrics_data = json.load(f)
    with open(LOGS_FILE, "r") as f:
        logs_data = json.load(f)

    # Standard context labels
    default_labels = {
        "tenant_id": "tenant-a",
        "environment": "prod",
        "region": "ap-southeast-1",
        "cluster": "eks-prod",
        "namespace": "bookhub-prod"
    }

    # Group metrics by timestamp
    timeline_points = {}
    for metric in metrics_data:
        m_name = metric["metric_name"]
        m_service = metric["service"]
        m_labels = metric.get("labels", {})
        
        for pt in metric["points"]:
            ts = pt["ts"]
            val = pt["value"]
            if ts not in timeline_points:
                timeline_points[ts] = {"metrics": [], "logs": []}
            
            # Construct metric payload
            labels = default_labels.copy()
            labels.update(m_labels)
            labels["service"] = m_service
            
            timeline_points[ts]["metrics"].append({
                "name": m_name,
                "type": "gauge",
                "value": val,
                "labels": labels
            })

    # Group logs by timestamp
    for log in logs_data:
        ts = log["ts"]
        if ts not in timeline_points:
            timeline_points[ts] = {"metrics": [], "logs": []}
            
        labels = default_labels.copy()
        labels["service"] = log["service"]
        
        timeline_points[ts]["logs"].append({
            "tenant_id": default_labels["tenant_id"],
            "service": log["service"],
            "environment": default_labels["environment"],
            "level": log["level"],
            "message": log["message"],
            "trace_id": log.get("trace_id"),
            "timestamp": ts,
            "labels": labels
        })

    # Sort timeline by timestamp
    sorted_timestamps = sorted(list(timeline_points.keys()))
    
    async with httpx.AsyncClient() as client:
        for idx, ts in enumerate(sorted_timestamps):
            batch = timeline_points[ts]
            # Skip empty batches
            if not batch["metrics"] and not batch["logs"]:
                continue
                
            print(f"\n[{idx+1}/{len(sorted_timestamps)}] Injecting batch for timestamp: {ts}")
            print(f"  - Metrics count: {len(batch['metrics'])}")
            print(f"  - Logs count: {len(batch['logs'])}")
            
            # Print metric details
            for m in batch["metrics"]:
                print(f"    Metric: {m['name']} = {m['value']}")
            # Print log details
            for l in batch["logs"]:
                print(f"    Log [{l['level'].upper()}]: {l['message']}")

            payload = {
                "metrics": batch["metrics"],
                "logs": batch["logs"],
                "traces": []
            }

            try:
                response = await client.post(TARGET_URL, json=payload, timeout=5.0)
                print(f"  -> Response Status: {response.status_code}")
                print(f"  -> Response Body: {response.json()}")
            except Exception as e:
                print(f"  -> ❌ Failed to send request: {e}")
                
            # Sleep to simulate degradation timeline
            print("Waiting 1 second before next injection...")
            await asyncio.sleep(1.0)
            
    print("\n[OK] Scenario 4 Telemetry Injection Completed Successfully!")

if __name__ == "__main__":
    asyncio.run(main())

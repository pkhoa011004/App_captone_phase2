import httpx
import asyncio
import time
import uuid

async def run_test():
    async with httpx.AsyncClient() as client:
        # Create a gauge metric that exceeds the alert threshold (2000)
        metrics = [
            {
                "name": "http_latency_p95_ms",
                "type": "gauge",
                "value": 2800.0,
                "labels": {
                    "tenant_id": "tenant-a",
                    "service": "payment-api",
                    "environment": "sandbox",
                    "scenario": "latency-degradation"
                }
            }
        ]
            
        payload = {
            "metrics": metrics,
            "logs": [],
            "traces": []
        }
        
        start = time.time()
        # Ensure kubectl port-forward svc/tf1-simulator 8080:80 is running
        print("Sending payload to http://localhost:8080/dumbproxy/inject-batch...")
        try:
            response = await client.post("http://localhost:8080/dumbproxy/inject-batch", json=payload)
            end = time.time()
            
            print(f"Status: {response.status_code}")
            print(f"Response: {response.json()}")
            print(f"Time taken: {(end - start) * 1000:.2f} ms")
            print("\n✅ Metric injected! Wait 1 minute for Prometheus to scrape and Alertmanager to trigger.")
        except Exception as e:
            print(f"❌ Failed to send request: {e}")
            print("Did you forget to run 'kubectl port-forward svc/tf1-simulator 8080:80 -n xbrain-cdo5-sandbox' ?")

if __name__ == "__main__":
    asyncio.run(run_test())

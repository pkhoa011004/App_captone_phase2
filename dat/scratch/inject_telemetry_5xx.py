import httpx
import asyncio
import time

async def run_test():
    async with httpx.AsyncClient() as client:
        # In Scenario 3, HTTP 5xx rate is spiking (> 5% of total request rate)
        # Note: the PrometheusRule for High5xxRate evaluates rate of http_requests_total{status="5.."}
        # Since it uses rate over 5m, we inject a high counter difference.
        metrics = [
            {
                "name": "http_requests_total",
                "type": "counter",
                "value": 500.0,
                "labels": {
                    "tenant_id": "tenant-a",
                    "environment": "prod",
                    "cluster": "eks-prod",
                    "namespace": "bookhub-prod",
                    "service": "book-service",
                    "pod": "book-service-7d9f6c8d9f-abcd1",
                    "container": "book-service",
                    "status": "500",
                    "method": "POST"
                }
            },
            {
                "name": "healthcheck_failures",
                "type": "gauge",
                "value": 1.0,
                "labels": {
                    "tenant_id": "tenant-a",
                    "environment": "prod",
                    "cluster": "eks-prod",
                    "namespace": "bookhub-prod",
                    "service": "book-service",
                    "pod": "book-service-7d9f6c8d9f-abcd1",
                    "container": "book-service"
                }
            }
        ]
            
        payload = {
            "metrics": metrics,
            "logs": [],
            "traces": []
        }
        
        start = time.time()
        print("Sending Scenario 3 telemetry to http://localhost:8080/dumbproxy/inject-batch...")
        try:
            response = await client.post("http://localhost:8080/dumbproxy/inject-batch", json=payload)
            end = time.time()
            print(f"Status: {response.status_code}")
            print(f"Response: {response.json()}")
            print(f"Time taken: {(end - start) * 1000:.2f} ms")
            print("\n[OK] Scenario 3 (HTTP 5xx Spike) metrics injected! Wait 1-2 minutes for Prometheus to trigger alerts.")
        except Exception as e:
            print(f"[ERROR] Failed to send request: {e}")
            print("Is 'kubectl port-forward svc/tf1-simulator 8080:80 -n xbrain-cdo5-sandbox' running?")

if __name__ == "__main__":
    asyncio.run(run_test())

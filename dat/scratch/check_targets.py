import urllib.request
import json

try:
    response = urllib.request.urlopen('http://localhost:9090/api/v1/targets')
    data = json.loads(response.read().decode('utf-8'))
    active_targets = data.get("data", {}).get("activeTargets", [])
    
    print("=== Prometheus Active Targets ===")
    found = False
    for t in active_targets:
        scrape_url = t.get("scrapeUrl", "")
        if "simulator" in scrape_url or "tf1" in scrape_url:
            found = True
            print(f"Target: {scrape_url}")
            print(f"  Health: {t.get('health')}")
            print(f"  Last Scrape: {t.get('lastScrape')}")
            print(f"  Last Error: {t.get('lastError') or 'None'}")
            print("-" * 40)
            
    if not found:
        print("No simulator targets found in Prometheus active targets list!")
except Exception as e:
    print(f"Error querying Prometheus API: {e}")

import urllib.request
import json
import yaml

try:
    response = urllib.request.urlopen('http://localhost:9090/api/v1/status/config')
    data = json.loads(response.read().decode('utf-8'))
    config_yaml = data.get("data", {}).get("yaml", "")
    
    # Print any line in config_yaml that contains 'job_name'
    print("=== Active Prometheus Scrape Job Names ===")
    lines = config_yaml.split("\n")
    for line in lines:
        if "job_name:" in line or "simulator" in line or "tf1" in line:
            print(line.strip())
except Exception as e:
    print(f"Error checking Prometheus config: {e}")

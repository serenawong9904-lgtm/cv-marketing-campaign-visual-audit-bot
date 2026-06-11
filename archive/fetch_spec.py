import urllib.request
import json

url = "https://agentskills.io/specification"
try:
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    response = urllib.request.urlopen(req)
    html = response.read().decode('utf-8')
    # Mintlify websites usually have an llms.txt available! 
    # Or I can just fetch https://agentskills.io/llms.txt
except Exception as e:
    print(f"Error: {e}")

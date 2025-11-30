import requests 

for i in range(10):
    requests.request(
        method="GET",
        url="http://localhost:8081/api/ping1",
        headers={
            "X-User-Id": "hittero" if i % 2 == 0 else "roro" 
        }
    )

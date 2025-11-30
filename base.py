import argparse
from collections import defaultdict, deque
import time 
from enum import Enum
import json
from flask import Flask, request, Response 
import requests 

class AlgorithmType(Enum):
    BUCKET_TOKEN = "bucket-token"
    SLIDING_WINDOW = "sliding-window"

parser = argparse.ArgumentParser(description="Simple ratelimiter for an API")
parser.add_argument(
    '--alg', 
    type=AlgorithmType,
    default=AlgorithmType.BUCKET_TOKEN,
    choices=list(AlgorithmType),
    help="Type of ratelimiting algorithm"
)

app = Flask(__name__) 

TRUE_URL = "http://127.0.0.1:8080/api/"
HTTP_METHODS = ["GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"]

token_counts = defaultdict(dict)
req_counts = defaultdict(deque)

rules = None

@app.route("/health", methods=["GET"])
def health():
    return Response(
        response=json.dumps({
            "message": "Ratelimiter is healthy."
        }),
        status=200,
        content_type="application/json"
    )

def proxy_request(user_id: str, path: str):
    downstream_url = f"{TRUE_URL}{path}"

    downstream_response = requests.request(
        method=request.method,
        url=downstream_url,
        headers=request.headers,
        params=request.args,
        data=request.get_data(),
        allow_redirects=False
    )

    ret_headers = downstream_response.headers 
    ret_headers["X-RateLimit-Limit"] = rules[user_id]["capacity"]
    if args.alg == AlgorithmType.BUCKET_TOKEN:
        ret_headers["X-RateLimit-Remaining"] = int(token_counts[user_id]["tokens"])
    else:
        ret_headers["X-RateLimit-Remaining"] = rules[user_id]["capacity"] - len(req_counts[user_id])

    return Response(
        response=downstream_response.content,
        status=downstream_response.status_code,
        headers=ret_headers
    )

def bucket_token(user_id: str, path: str):
    if user_id not in rules:
        user_id = "default"

    CAPACITY = rules[user_id]["capacity"]
    REFILL_RATE = rules[user_id]["refill_rate"]

    if user_id not in token_counts:
        token_counts[user_id] = {
            "tokens": CAPACITY,
            "last_refill": time.monotonic()
        }
    
    tokens = token_counts[user_id]["tokens"]
    last_refill = token_counts[user_id]["last_refill"]

    cur_time = time.monotonic()
    duration = cur_time - last_refill 

    tokens = min(CAPACITY, tokens + duration / 60 * REFILL_RATE)
    if tokens >= 1:
        token_counts[user_id]["tokens"] = tokens - 1
        token_counts[user_id]["last_refill"] = cur_time
        return proxy_request(user_id, path)
    else:
        token_counts[user_id]["tokens"] = tokens
        retry_after = (1 - tokens) / (REFILL_RATE / 60)
        return Response(
            response=json.dumps({
                "error": "rate_limit_exceeded",
                "message": "You're doing that too often! Try again later."
            }),
            status=429,
            content_type="application/json",
            headers={
                "X-RateLimit-Limit": CAPACITY,
                "X-RateLimit-Remaining": 0,
                "Retry-After": retry_after
            }
        )

def sliding_window(user_id: str, path: str):
    if user_id not in rules:
        user_id = "default"

    CAPACITY = rules[user_id]["capacity"]
    cur_time = time.monotonic()
    user_deque = req_counts[user_id]
    while len(user_deque) > 0 and cur_time - user_deque[0] > 60:
        user_deque.popleft()

    if len(user_deque) >= CAPACITY:
        retry_after = 60 - (cur_time - user_deque[0])
        return Response(
            response=json.dumps({
                "error": "rate_limit_exceeded",
                "message": "You're doing that too often! Try again later."
            }),
            status=429,
            content_type="application/json",
            headers={
                "X-RateLimit-Limit": CAPACITY,
                "X-RateLimit-Remaining": 0,
                "Retry-After": retry_after
            }
        ) 
    else:
        user_deque.append(cur_time)
        return proxy_request(user_id, path)

@app.route("/api/<path:path>", methods=HTTP_METHODS)
def entry(path):
    if path not in ["ping1", "ping2"]:
        return Response(
            response=json.dumps({
                "error": "invalid_request",
                "message": f"/{path} not found"
            }),
            status=404,
            content_type="application/json"
        )
    
    user_id = request.headers["X-User-Id"]
    if args.alg == AlgorithmType.BUCKET_TOKEN:
        return bucket_token(user_id, path)
    else:
        return sliding_window(user_id, path)

if __name__ == "__main__":
    args = parser.parse_args()
    
    with open("rules.json", "r") as f: 
        rules = json.load(f)

    app.run(debug=True, port=8081)
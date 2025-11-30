import json
from flask import Flask, Response 

app = Flask(__name__)

@app.route('/api/ping1', methods=['GET'])
def get_ping_first():
    return Response(
        response=json.dumps({
            "message": "Ping 1 successful!"
        }),
        status=200,
        content_type="application/json"
    )

@app.route('/api/ping2', methods=['GET'])
def get_ping_second():
    return Response(
        response=json.dumps({
            "message": "Ping 2 successful!"
        }),
        status=200,
        content_type="application/json"
    )

if __name__ == "__main__":
    app.run(debug=True, port=8080)
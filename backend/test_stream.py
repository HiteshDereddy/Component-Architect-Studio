import requests
import json

def test_stream():
    url = "http://127.0.0.1:8000/generate"
    data = {
        "prompt": "Create an analytics dashboard.",
        "session_id": "test_session_1"
    }
    
    print("Sending POST request to generate...")
    with requests.post(url, json=data, stream=True) as r:
        for line in r.iter_lines():
            if line:
                decoded = line.decode('utf-8')
                if decoded.startswith("data: "):
                    payload = json.loads(decoded[6:])
                    if payload["type"] == "chunk":
                        print(payload["content"], end="", flush=True)
                    elif payload["type"] == "error":
                        print("\n\n[ERROR RECEIVED]", payload["errors"])
                    elif payload["type"] == "done":
                        print("\n\n[DONE RECEIVED]")

if __name__ == "__main__":
    test_stream()

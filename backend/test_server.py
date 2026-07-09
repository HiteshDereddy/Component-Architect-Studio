import requests

try:
    response = requests.get("http://127.0.0.1:8000/design-system")
    if response.status_code == 200:
        print("Success! Design System JSON:", response.json())
    else:
        print("Failed to get design system. Status code:", response.status_code)
except Exception as e:
    print("Error connecting to server:", e)

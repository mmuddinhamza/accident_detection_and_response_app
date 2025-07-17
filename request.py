import requests

url = 'http://192.168.137.58:5001/accident'
data = {
    "latitude":  17.428624772959356,
    "longitude": 78.44397338553067,
    "intensity": "High"
}

response = requests.post(url, json=data)


# Check if the request was successful
if response.status_code == 200:
    try:
        print(response.json())  # Only attempt to decode JSON if the status code is 200
    except ValueError:
        print("Error: Response is not in JSON format")
else:
    print(f"Request failed with status code {response.status_code}")

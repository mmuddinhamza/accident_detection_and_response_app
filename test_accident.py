import requests
import json
import time

# --- Configuration ---
# URL of your Flask application's /accident endpoint
ACCIDENT_ENDPOINT_URL = "http://127.0.0.1:5001/accident"

# --- Test Data ---
# Example accident locations and intensities
# Adjust these coordinates to be near your registered Hospital/Fire Department
# For Hyderabad: approx. 17.3850 N, 78.4867 E
test_accidents = [
    {
        "latitude": 17.3900,
        "longitude": 78.4900,
        "intensity": "high"
    },
    {
        "latitude": 17.3800,
        "longitude": 78.4800,
        "intensity": "medium"
    },
    {
        "latitude": 17.34345000,
        "longitude": 78.22344000,
        "intensity": "low"
    },
    {
        "latitude": 17.4050, 
        "longitude": 78.5050,
        "intensity": "critical"
    }
]

# --- Function to send an accident alert ---
def send_accident_alert(accident_data):
    """
    Sends a POST request to the /accident endpoint with the given data.
    """
    print(f"\n--- Sending Accident Alert ---")
    print(f"Data: {accident_data}")

    try:
        response = requests.post(
            ACCIDENT_ENDPOINT_URL,
            json=accident_data,
            headers={'Content-Type': 'application/json'}
        )

        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)

        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
        print(f"Response Content: {response.text}")
    except requests.exceptions.ConnectionError as conn_err:
        print(f"Connection error occurred: {conn_err}. Is your Flask app running?")
    except requests.exceptions.Timeout as timeout_err:
        print(f"Timeout error occurred: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        print(f"An unexpected error occurred: {req_err}")
    except json.JSONDecodeError:
        print(f"Failed to decode JSON response. Raw response: {response.text}")

# --- Main execution ---
if __name__ == "__main__":
    print(f"Testing the /accident endpoint at {ACCIDENT_ENDPOINT_URL}")
    print("Ensure your Flask app (app.py) is running before executing this script.")

    for i, accident in enumerate(test_accidents):
        send_accident_alert(accident)
        if i < len(test_accidents) - 1:
            print("\nWaiting for 5 seconds before next alert...")
            time.sleep(5) # Wait a bit between requests
    
    print("\n--- All accident alerts sent. ---")
    print("Check your Flask console and browser dashboards for real-time updates and SMS/WhatsApp alerts.")

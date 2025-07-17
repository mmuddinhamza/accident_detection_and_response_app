import requests
import json
import time

# --- Configuration for Local Testing ---
# Since your Flask app is running on the same machine, use localhost (127.0.0.1)
FLASK_APP_IP = "127.0.0.1"
FLASK_APP_PORT = 5001
ACCIDENT_ENDPOINT_URL = f"http://{FLASK_APP_IP}:{FLASK_APP_PORT}/accident"

# Hardcoded accident location for testing
# Make sure these coordinates are within ~10km of your registered hospital/fire department
# For 'gokuldham' hospital (17.34345, 78.22344), these are good test points.
TEST_LATITUDE = 17.34345
TEST_LONGITUDE = 78.22344

# --- Function to send an accident alert (copied from Raspberry Pi script) ---
def send_accident_alert(latitude, longitude, intensity):
    """
    Sends an HTTP POST request to the Flask backend's /accident endpoint.
    """
    payload = {
        "latitude": latitude,
        "longitude": longitude,
        "intensity": intensity
    }
    
    print(f"\n[TEST] Sending accident data to backend: {json.dumps(payload)}")
    
    try:
        response = requests.post(
            ACCIDENT_ENDPOINT_URL,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=5 # Set a timeout for the request (e.g., 5 seconds)
        )
        
        response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)
        
        print(f"[TEST SUCCESS] Backend response ({response.status_code}): {response.json().get('status', 'No status')}")
        
    except requests.exceptions.ConnectionError as e:
        print(f"[TEST ERROR] Connection to backend failed: {e}. Is Flask app running at {FLASK_APP_IP}:{FLASK_APP_PORT}?")
    except requests.exceptions.Timeout:
        print("[TEST ERROR] Request to backend timed out. Flask app might be slow to respond.")
    except requests.exceptions.HTTPError as e:
        print(f"[TEST ERROR] HTTP error from backend ({response.status_code}): {e}")
        print(f"Backend response body: {response.text}")
    except json.JSONDecodeError:
        print(f"[TEST ERROR] Failed to decode JSON response from backend. Raw response: {response.text}")
    except Exception as e:
        print(f"[TEST ERROR] An unexpected error occurred while sending data: {e}")

# --- Main execution for testing ---
if __name__ == "__main__":
    print("--- Local Test Script for Raspberry Pi Alert Logic ---")
    print("Ensure your Flask app (app.py) is running in a separate terminal.")
    print(f"Attempting to send alert to: {ACCIDENT_ENDPOINT_URL}")

    # Test with a 'high' intensity alert
    send_accident_alert(TEST_LATITUDE, TEST_LONGITUDE, "high")

    time.sleep(2) # Give some time for the Flask app to process

    # Test with a 'medium' intensity alert
    send_accident_alert(TEST_LATITUDE + 0.001, TEST_LONGITUDE - 0.001, "medium")

    print("\n--- Local testing complete. ---")
    print("Check your Flask app's console and any open dashboard in your browser.")

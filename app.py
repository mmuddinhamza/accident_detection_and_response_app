from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS, cross_origin
from geopy.distance import geodesic
from twilio.rest import Client
import mysql.connector
import logging
import requests
from threading import Thread
from flask_socketio import SocketIO, emit
import json
from jinja2 import Template
import os
from werkzeug.security import generate_password_hash, check_password_hash

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

HOSPITAL_TEMPLATE_PATH = "templates/hospital_dashboard.html"


# Database Connection (Use context manager per request)
def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="SecurePass!1", # Make sure this matches your MySQL root password
        database="hospitals_db" # Make sure this matches your database name
    )

# Function to create database tables
def create_tables():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Create users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                phone_number VARCHAR(20),
                emergency_contacts JSON,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        logging.info("Table 'users' ensured to exist.")

        # Create hospitals table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS hospitals (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                contact_number VARCHAR(20),
                password VARCHAR(255) NOT NULL,
                latitude DECIMAL(10, 8) NOT NULL,
                longitude DECIMAL(11, 8) NOT NULL,
                is_alerted BOOLEAN DEFAULT FALSE, # Keep this column, but we won't update it
                dashboard_path VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        logging.info("Table 'hospitals' ensured to exist.")

        # Create fire_departments table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS fire_departments (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                email VARCHAR(255) UNIQUE NOT NULL,
                contact_number VARCHAR(20),
                password VARCHAR(255) NOT NULL,
                latitude DECIMAL(10, 8) NOT NULL,
                longitude DECIMAL(11, 8) NOT NULL,
                dashboard_path VARCHAR(255),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        logging.info("Table 'fire_departments' ensured to exist.")

        # Create accidents table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS accidents (
                id INT AUTO_INCREMENT PRIMARY KEY,
                latitude DECIMAL(10, 8) NOT NULL,
                longitude DECIMAL(11, 8) NOT NULL,
                intensity VARCHAR(50),
                accident_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        logging.info("Table 'accidents' ensured to exist.")

        conn.commit()
        logging.info("All necessary database tables checked/created successfully.")
    except mysql.connector.Error as err:
        logging.error(f"Error creating tables: {err}", exc_info=True)
        raise
    finally:
        if 'cursor' in locals() and cursor:
            cursor.close()
        if 'conn' in locals() and conn.is_connected():
            conn.close()


def create_dashboard(name, user_id, user_type):
    try:
        dashboards_dir = os.path.join("templates", "dashboards")
        
        if user_type == 'hospital':
            template_filename = "hospital_dashboard.html"
        elif user_type == 'fire_department':
            template_filename = "police_dashboard.html"
        else:
            logging.error(f"Unsupported user_type for dashboard creation: {user_type}")
            return None

        template_path = os.path.join("templates", template_filename)
        dashboard_output_filename = f"dashboard_{user_type}_{user_id}.html"
        dashboard_full_path = os.path.join(dashboards_dir, dashboard_output_filename)

        if not os.path.exists(dashboards_dir):
            os.makedirs(dashboards_dir)
            logging.info(f"Created directory: {dashboards_dir}")

        with open(template_path, 'r', encoding='utf-8') as template_file:
            template_content = template_file.read()

        dashboard_content = (
            template_content.replace("{{ hospital_name }}", name)
                            .replace("{{ hospital_id }}", str(user_id))
        )

        with open(dashboard_full_path, 'w', encoding='utf-8') as dashboard_file:
            dashboard_file.write(dashboard_content)

        logging.info(f"Dashboard created for {user_type} {name} (ID: {user_id}) at {dashboard_full_path}")
        return f"dashboards/{dashboard_output_filename}"

    except Exception as e:
        logging.error(f"Error creating dashboard for {user_type} {name}: {e}", exc_info=True)
        return None


app = Flask(__name__, static_folder='templates')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

# Twilio Configuration
TWILIO_SID = ""
TWILIO_AUTH_TOKEN = ""
MESSAGING_SERVICE_SID = ""
client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)

@app.route('/accident', methods=['POST'])
@cross_origin()
def handle_accident():
    try:
        data = request.json
        latitude = data['latitude']
        longitude = data['longitude']
        accident_intensity = data['intensity']

        accident_address = get_location_from_coordinates_osm(latitude, longitude)

        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        insert_accident_query = """
            INSERT INTO accidents (latitude, longitude, intensity)
            VALUES (%s, %s, %s)
        """
        cursor.execute(insert_accident_query, (latitude, longitude, accident_intensity))
        db.commit()

        # --- START MODIFICATION FOR MULTIPLE ALERTS ---
        # Fetch ALL hospitals, regardless of their `is_alerted` status.
        # This ensures they are always considered for new alerts.
        cursor.execute("SELECT * FROM hospitals")
        hospitals = cursor.fetchall()
        # --- END MODIFICATION ---

        nearest_hospitals = []
        accident_location = (latitude, longitude)
        for hospital in hospitals:
            hospital_location = (hospital['latitude'], hospital['longitude'])
            distance = geodesic(accident_location, hospital_location).km
            if distance <= 10: # Still within 10km radius
                nearest_hospitals.append(hospital)

        if not nearest_hospitals:
            return jsonify({'status': 'No nearby hospitals found'})

        hospital_ids_alerted = [] # Keep track of which hospitals are actually alerted in this call

        # Send alerts and emit WebSocket events
        for hospital in nearest_hospitals:
            # Removed the `if hospital['is_alerted'] == 0:` check here
            # because we want to alert them every time if they are nearby.
            alert_message = (
                f"Accident detected at {accident_address} (Lat: {latitude}, Long: {longitude}). "
                f"Intensity: {accident_intensity}."
            )

            # Send SMS asynchronously
            alert_thread = Thread(target=send_sms_alert, args=(hospital, alert_message))
            alert_thread.start()

            # Add hospital ID to the list of alerted hospitals for the WebSocket payload
            hospital_ids_alerted.append(hospital['id'])

            # --- START MODIFICATION ---
            # REMOVED THE LINE THAT SETS is_alerted = 1
            # This ensures the flag is never set to 1 by the alert process,
            # allowing the hospital to be re-alerted.
            # cursor.execute("UPDATE hospitals SET is_alerted = 1 WHERE id = %s", (hospital['id'],))
            # db.commit()
            # --- END MODIFICATION ---
        
        # Emit the alert to WebSocket clients after processing all nearest hospitals
        # This single emit will contain all relevant hospital IDs for client-side filtering
        socketio.emit('accident-alert', {
            'address': accident_address,
            'latitude': latitude,
            'longitude': longitude,
            'intensity': accident_intensity,
            'hospital_ids': hospital_ids_alerted # Use the list of hospitals actually alerted
        })

        return jsonify({
            'status': 'Alert sent to nearby hospitals',
            'alerted_hospitals_count': len(nearest_hospitals),
            'message': f"Alerts sent for accident at {accident_address}"
        })

    except Exception as e:
        logging.error(f"Error occurred: {e}", exc_info=True)
        return jsonify({'error': 'Internal server error', 'details': str(e)}), 500

    finally:
        if 'cursor' in locals():
            cursor.close()
        if 'db' in locals():
            db.close()


@app.route('/register', methods=['POST'])
@cross_origin()
def register():
    data = request.json

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        user_type = data['type']
        name = data['name']
        email = data['email']
        phone_number = data['phone_number']

        cursor.execute("SELECT id FROM users WHERE email = %s UNION SELECT id FROM hospitals WHERE email = %s UNION SELECT id FROM fire_departments WHERE email = %s", (email, email, email))
        if cursor.fetchone():
            return jsonify({"status": "error", "message": "Email already registered."}), 409

        if user_type == 'user':
            emergency_contacts = json.dumps(data.get('emergency_contacts', []))
            insert_user_query = "INSERT INTO users (name, email, phone_number, emergency_contacts) VALUES (%s, %s, %s, %s)"
            cursor.execute(insert_user_query, (name, email, phone_number, emergency_contacts))
            message = "User registered successfully."
            redirect_url = '/login.html'

        elif user_type == 'hospital':
            password = data['password']
            latitude = data['latitude']
            longitude = data['longitude']
            hashed_password = generate_password_hash(password)

            insert_hospital_query = """
                INSERT INTO hospitals (name, email, contact_number, password, latitude, longitude)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_hospital_query, (name, email, phone_number, hashed_password, latitude, longitude))
            hospital_id = cursor.lastrowid
            dashboard_path = create_dashboard(name, hospital_id, user_type='hospital')
            if dashboard_path:
                cursor.execute("UPDATE hospitals SET dashboard_path = %s WHERE id = %s", (dashboard_path, hospital_id))
                message = f"Hospital registered successfully. Dashboard created at: {dashboard_path}"
                redirect_url = '/login.html'
            else:
                message = "Hospital registered, but dashboard creation failed."
                redirect_url = '/registration.html'
                conn.rollback()
                return jsonify({"status": "error", "message": message}), 500


        elif user_type == 'fire_department':
            password = data['password']
            latitude = data['latitude']
            longitude = data['longitude']
            hashed_password = generate_password_hash(password)

            insert_fire_department_query = """
                INSERT INTO fire_departments (name, email, contact_number, password, latitude, longitude)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_fire_department_query, (name, email, phone_number, hashed_password, latitude, longitude))
            fire_department_id = cursor.lastrowid
            dashboard_path = create_dashboard(name, fire_department_id, user_type='fire_department')
            if dashboard_path:
                cursor.execute("UPDATE fire_departments SET dashboard_path = %s WHERE id = %s", (dashboard_path, fire_department_id))
                message = f"Fire Department registered successfully. Dashboard created at: {dashboard_path}"
                redirect_url = '/login.html'
            else:
                message = "Fire Department registered, but dashboard creation failed."
                redirect_url = '/registration.html'
                conn.rollback()
                return jsonify({"status": "error", "message": message}), 500

        else:
            return jsonify({"status": "error", "message": "Invalid user type."}), 400

        conn.commit()
        return jsonify({"status": "success", "message": message, "redirect": redirect_url}), 201

    except KeyError as e:
        conn.rollback()
        logging.error(f"Missing data for registration: {e}", exc_info=True)
        return jsonify({"status": "error", "message": f"Missing required field: {e}. Please provide all necessary information."}), 400
    except mysql.connector.Error as err:
        conn.rollback()
        logging.error(f"Database error during registration: {err}", exc_info=True)
        return jsonify({"status": "error", "message": f"Database error: {err}"}), 500
    except Exception as e:
        conn.rollback()
        logging.error(f"An unexpected error occurred during registration: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "An unexpected error occurred. Please try again."}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/login', methods=['POST'])
@cross_origin()
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')

    if not email or not password:
        return jsonify({"status": "error", "message": "Email and password are required"}), 400

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id, name, password, dashboard_path, 'hospital' as user_type FROM hospitals WHERE email = %s UNION SELECT id, name, password, dashboard_path, 'fire_department' as user_type FROM fire_departments WHERE email = %s", (email, email))
        user = cursor.fetchone()

        if user and check_password_hash(user['password'], password):
            if user['user_type'] in ['hospital', 'fire_department']:
                dashboard_url = user['dashboard_path']
                if dashboard_url:
                    return jsonify({"status": "success", "message": f"Welcome {user['name']}", "dashboard_url": dashboard_url}), 200
                else:
                    logging.warning(f"Dashboard path not found for {user['user_type']} {user['name']} (ID: {user['id']}). Re-creating.")
                    new_dashboard_path = create_dashboard(user['name'], user['id'], user['user_type'])
                    if new_dashboard_path:
                        if user['user_type'] == 'hospital':
                            cursor.execute("UPDATE hospitals SET dashboard_path = %s WHERE id = %s", (new_dashboard_path, user['id']))
                        else:
                            cursor.execute("UPDATE fire_departments SET dashboard_path = %s WHERE id = %s", (new_dashboard_path, user['id']))
                        conn.commit()
                        return jsonify({"status": "success", "message": f"Welcome {user['name']}", "dashboard_url": new_dashboard_path}), 200
                    else:
                        return jsonify({"status": "error", "message": "Dashboard not found and could not be re-created. Please contact support."}), 500
            else:
                return jsonify({"status": "success", "message": f"Welcome {user['name']}. No dashboard for regular users."}), 200
        else:
            return jsonify({"status": "error", "message": "Invalid email or password"}), 401

    except mysql.connector.Error as err:
        logging.error(f"Database error during login: {err}", exc_info=True)
        return jsonify({"status": "error", "message": f"Database error: {err}"}), 500
    except Exception as e:
        logging.error(f"An unexpected error occurred during login: {e}", exc_info=True)
        return jsonify({"status": "error", "message": "An unexpected error occurred. Please try again."}), 500
    finally:
        cursor.close()
        conn.close()


@app.route('/')
def index():
    return app.send_static_file('registration.html')

@app.route('/registration.html')
def serve_registration():
    return app.send_static_file('registration.html')

@app.route('/login.html')
def serve_login():
    return app.send_static_file('login.html')

@app.route('/dashboards/<path:filename>')
def serve_dashboard(filename):
    return send_from_directory(os.path.join(app.root_path, 'templates', 'dashboards'), filename)


def get_location_from_coordinates_osm(latitude, longitude):
    try:
        url = "https://nominatim.openstreetmap.org/reverse"
        params = {
            'lat': latitude,
            'lon': longitude,
            'format': 'json',
            'addressdetails': 1
        }
        headers = {
            'User-Agent': 'Accident-Alert-System/1.0 (contact@example.com)'
        }
        response = requests.get(url, params=params, headers=headers)
        response_data = response.json()
        logging.debug(f"Nominatim API Response: {response_data}")
        return response_data.get('display_name', 'Unknown Location')
    except Exception as e:
        logging.error(f"Exception in get_location_from_coordinates_osm: {e}", exc_info=True)
        return "Error retrieving location"
    

def format_phone_number(phone_number):
    """
    Formats the phone number to E.164 standard.
    Assumes numbers without '+' are Indian numbers.
    """
    if not phone_number.startswith("+"):
        phone_number = "+91" + phone_number
    return phone_number


def send_sms_alert(hospital, alert_message):
    """
    Sends an SMS and WhatsApp alert to the given hospital using a Messaging Service.
    """
    try:
        # Format the phone number to include the country code if missing
        contact_number = format_phone_number(hospital['contact_number'])

        # Send SMS alert using MessagingServiceSid
        sms_response = client.messages.create(
            body=alert_message,
            # Use messaging_service_sid instead of from_
            messaging_service_sid=MESSAGING_SERVICE_SID,
            to=contact_number
        )
        logging.info(f"SMS sent successfully to {contact_number} via Messaging Service: {sms_response.sid}")

        # Send WhatsApp alert (this still needs the specific Twilio WhatsApp number if not part of Messaging Service)
        # If your Messaging Service is configured for WhatsApp, you might also use messaging_service_sid here.
        # Otherwise, keep the specific WhatsApp 'from_' number.
        whatsapp_response = client.messages.create(
            body=alert_message,
            from_="whatsapp: {your twillio whatsapp no.}",  # Your Twilio WhatsApp number (default sandbox number)
            to=f"whatsapp:{contact_number}"
        )
        logging.info(f"WhatsApp alert sent successfully to {contact_number}: {whatsapp_response.sid}")

    except Exception as e:
        logging.error(f"Error in send_sms_alert: {e}", exc_info=True)


if __name__ == '__main__':
    create_tables()
    socketio.run(app,debug=True, host='0.0.0.0', port=5001)

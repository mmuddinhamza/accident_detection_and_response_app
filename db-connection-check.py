import mysql.connector

try:
    db = mysql.connector.connect(
        host="localhost",
        user="root",
        password="SecurePass!1",
        database="hospitals_db"
    )
    print("MySQL connection successful")
except mysql.connector.Error as err:
    print(f"Error: {err}")

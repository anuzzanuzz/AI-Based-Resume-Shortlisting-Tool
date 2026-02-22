from flask import current_app
import os
import mysql.connector

def save_file(file, upload_folder):
    """Save the uploaded file to the specified folder."""
    if not os.path.exists(upload_folder):
        os.makedirs(upload_folder)
    file_path = os.path.join(upload_folder, file.filename)
    file.save(file_path)
    return file_path

def get_db_connection():
    """Establish a connection to the database."""
    try:
        db = mysql.connector.connect(
            host=current_app.config['DB_HOST'],
            user=current_app.config['DB_USER'],
            password=current_app.config['DB_PASSWORD'],
            database=current_app.config['DB_NAME']
        )
        return db
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return None

def close_db_connection(db):
    """Close the database connection."""
    if db:
        db.close()
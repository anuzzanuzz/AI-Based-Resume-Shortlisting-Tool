from mysql.connector import connect, Error
import sys
import os

def create_database_if_not_exists():
    """Create the database if it doesn't exist."""
    try:
        connection = connect(
            host="localhost",
            user="root",
            password=""
        )
        cursor = connection.cursor()
        cursor.execute("CREATE DATABASE IF NOT EXISTS ai_resume_db")
        connection.commit()
        print("✓ Database 'ai_resume_db' created or already exists.")
        return True
    except Error as e:
        print(f"❌ Error creating database: {e}")
        return False
    finally:
        if connection:
            cursor.close()
            connection.close()

def init_db():
    """Initialize database tables."""
    try:
        connection = connect(
            host="localhost",
            user="root",
            password="",
            database="ai_resume_db"
        )

        cursor = connection.cursor()

        # Create tables with proper structure
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS resumes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            filename VARCHAR(255) NOT NULL,
            match_percent FLOAT NOT NULL,
            uploaded_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS candidates (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            email VARCHAR(255) NOT NULL UNIQUE,
            match_percent FLOAT NOT NULL,
            test_score FLOAT DEFAULT 0,
            status VARCHAR(50) DEFAULT 'pending',
            created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        cursor.execute("""
        CREATE TABLE IF NOT EXISTS test_results (
            id INT AUTO_INCREMENT PRIMARY KEY,
            candidate_name VARCHAR(255) NOT NULL,
            candidate_email VARCHAR(255) NOT NULL,
            job_description LONGTEXT,
            score FLOAT NOT NULL,
            total_questions INT NOT NULL,
            status VARCHAR(50) NOT NULL,
            created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        connection.commit()
        print("✓ Database tables initialized successfully.")

    except Error as e:
        print(f"❌ Error initializing database tables: {e}")
        return False

    finally:
        if connection:
            cursor.close()
            connection.close()
    return True

def migrate_db():
    """Run database migrations."""
    print("Running database migrations...")

    # Create database if needed
    if not create_database_if_not_exists():
        return False

    # Initialize tables
    if not init_db():
        return False

    print("✓ All migrations completed successfully.")
    return True

def check_mysql_connection():
    """Check if MySQL is running."""
    try:
        connection = connect(
            host="localhost",
            user="root",
            password=""
        )
        connection.close()
        return True
    except Error as e:
        print(f"❌ MySQL connection failed: {e}")
        print("Please ensure XAMPP MySQL is running.")
        return False

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        if check_mysql_connection():
            migrate_db()
        else:
            sys.exit(1)
    else:
        if check_mysql_connection():
            create_database_if_not_exists()
            init_db()
        else:
            sys.exit(1)

# Flask Configuration
SECRET_KEY=airesume_secret_key_2024
DEBUG=True
UPLOAD_FOLDER=uploads
FLASK_ENV=development

# Database Configuration
DB_TYPE=mysql
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=
DB_NAME=ai_resume_db
DB_PORT=3306

# MongoDB Configuration (alternative)
MONGO_URI=mongodb://localhost:27017/ai_resume_db

# Email Configuration (Gmail)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=resumeproject25@gmail.com
MAIL_PASSWORD=cgkc ihsd vzth kptj
MAIL_DEFAULT_SENDER=resumeproject25@gmail.com
MAIL_USE_TLS=True
MAIL_USE_SSL=False

# Gemini AI Configuration
GEMINI_API_KEY=AIzaSyC-NEZZTXL3Nu6Lj0M1Y3aQf8xAq2XJxQU
GEMINI_MODEL=gemini-2.5-flash

# Login Configuration
ADMIN_USERNAME=resume.project25
ADMIN_PASSWORD=project25resume

# Test Configuration
TOTAL_TEST_QUESTIONS=10
POINTS_PER_QUESTION=10
TOP_CANDIDATES=3
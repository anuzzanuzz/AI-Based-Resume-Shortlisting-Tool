from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
from config import get_config
import os
import PyPDF2
import docx
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import matplotlib.pyplot as plt
import mysql.connector
from pymongo import MongoClient
from datetime import datetime
import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
import re
import google.generativeai as genai
import json
import os

# ---------- Download NLTK data ----------
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')

try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords')

try:
    nltk.data.find('corpora/wordnet')
except LookupError:
    nltk.download('wordnet')

try:
    nltk.data.find('corpora/omw-1.4')
except LookupError:
    nltk.download('omw-1.4')

# ---------- Initialize Flask App ----------
app = Flask(__name__)
config = get_config()
app.config.from_object(config)

# ---------- Gemini AI Configuration ----------
try:
    genai.configure(api_key=app.config['GEMINI_API_KEY'])
    print("✓ Gemini AI configured successfully")
except Exception as e:
    print(f"❌ Error configuring Gemini: {e}")

# ---------- Email Configuration ----------
app.config.update({
    'MAIL_SERVER': app.config.get('MAIL_SERVER', 'smtp.gmail.com'),
    'MAIL_PORT': int(app.config.get('MAIL_PORT', 587)),
    'MAIL_USE_TLS': bool(app.config.get('MAIL_USE_TLS', True)),
    'MAIL_USE_SSL': False,
    'MAIL_USERNAME': app.config.get('MAIL_USERNAME'),
    'MAIL_PASSWORD': app.config.get('MAIL_PASSWORD'),
    'MAIL_DEFAULT_SENDER': app.config.get('MAIL_DEFAULT_SENDER') or app.config.get('MAIL_USERNAME')
})
mail = Mail(app)

def send_test_mail(candidate_email, candidate_id):
    test_link = f"http://localhost:5000/start_test/{candidate_id}"

    msg = Message(
        subject="Online Assessment Test",
        sender=app.config['MAIL_USERNAME'],
        recipients=[candidate_email]
    )

    msg.body = f"""
Dear Candidate,

You have been shortlisted for the next round.

Click below to start your test:
{test_link}

Please allow camera permission for identity verification.

All the best!
Team HR
"""
    mail.send(msg)

# ---------- Create Upload Folder ----------
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ---------- Database Connection ----------
def get_db_connection():
    """Get database connection with automatic fallback to MongoDB."""
    if app.config['DB_TYPE'].lower() == 'mongodb':
        try:
            client = MongoClient(app.config['MONGO_URI'])
            return client[app.config['DB_NAME']]
        except Exception as e:
            print(f"❌ MongoDB Error: {e}")
            return None
    else:
        # Try MySQL first
        try:
            db = mysql.connector.connect(
                host=app.config['DB_HOST'],
                user=app.config['DB_USER'],
                password=app.config['DB_PASSWORD'],
                database=app.config['DB_NAME'],
                port=app.config['DB_PORT'],
                charset='latin1',
                autocommit=True
            )
            return db
        except Exception as e:
            print(f"❌ MySQL not available: {e}")
            print("🔄 Falling back to MongoDB...")
            # Fallback to MongoDB
            try:
                client = MongoClient(app.config['MONGO_URI'])
                app.config['DB_TYPE'] = 'mongodb'  # Switch to MongoDB mode
                print("✓ Successfully connected to MongoDB")
                return client[app.config['DB_NAME']]
            except Exception as mongo_e:
                print(f"❌ MongoDB fallback failed: {mongo_e}")
                return None

def init_db():
    """Initialize database with automatic fallback."""
    db = get_db_connection()  # This will handle fallback automatically
    if db is None:
        print("❌ No database connection available")
        return
    
    try:
        if app.config['DB_TYPE'].lower() == 'mongodb':
            # MongoDB initialization
            db.candidates.create_index("email")
            db.candidates.create_index("name")
            db.hr_notifications.create_index("candidate_id")
            db.test_results.create_index("candidate_email")
            db.admin_users.create_index("username", unique=True)
            print("✓ MongoDB initialized successfully")
        else:
            # MySQL initialization
            cursor = db.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS resumes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                filename VARCHAR(255),
                match_percent FLOAT,
                uploaded_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS candidates (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255),
                email VARCHAR(255),
                match_percent FLOAT,
                test_score FLOAT DEFAULT 0,
                second_round_score FLOAT DEFAULT 0,
                status VARCHAR(50) DEFAULT 'pending',
                job_description LONGTEXT,
                filename VARCHAR(255),
                created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS test_results (
                id INT AUTO_INCREMENT PRIMARY KEY,
                candidate_name VARCHAR(255),
                candidate_email VARCHAR(255),
                job_description LONGTEXT,
                score FLOAT,
                total_questions INT,
                status VARCHAR(50),
                created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS hr_notifications (
                id INT AUTO_INCREMENT PRIMARY KEY,
                candidate_id VARCHAR(255),
                candidate_name VARCHAR(255),
                candidate_email VARCHAR(255),
                test_score FLOAT,
                match_percent FLOAT,
                status VARCHAR(50) DEFAULT 'pending',
                seen BOOLEAN DEFAULT FALSE,
                sent_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS second_round_challenges (
                id INT AUTO_INCREMENT PRIMARY KEY,
                candidate_id VARCHAR(255),
                challenges LONGTEXT,
                created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status VARCHAR(50) DEFAULT 'pending'
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS second_round_results (
                id INT AUTO_INCREMENT PRIMARY KEY,
                candidate_id VARCHAR(255),
                reasoning_score INT,
                aptitude_score INT,
                coding_score FLOAT,
                total_score FLOAT,
                percentage FLOAT,
                answers LONGTEXT,
                submitted_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS admin_users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(100) UNIQUE,
                password VARCHAR(255),
                created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """)
            cursor.close()
            db.close()
            print("✓ MySQL initialized successfully")
    except Exception as e:
        print(f"❌ Database initialization error: {e}")

# Initialize database on startup
init_db()

# Create default admin user if not exists
def create_default_admin():
    db = get_db_connection()
    if db is not None:
        try:
            if app.config['DB_TYPE'].lower() == 'mongodb':
                count = db.admin_users.count_documents({})
                if count == 0:
                    db.admin_users.insert_one({
                        'username': app.config['ADMIN_USERNAME'],
                        'password': app.config['ADMIN_PASSWORD'],
                        'created_on': datetime.now()
                    })
                    print("✓ Default admin user created")
            else:
                cursor = db.cursor()
                cursor.execute("SELECT COUNT(*) FROM admin_users")
                count = cursor.fetchone()[0]
                if count == 0:
                    cursor.execute("INSERT INTO admin_users (username, password) VALUES (%s, %s)", 
                                  (app.config['ADMIN_USERNAME'], app.config['ADMIN_PASSWORD']))
                    print("✓ Default admin user created")
                cursor.close()
                db.close()
        except Exception as e:
            print(f"❌ Error creating admin user: {e}")

create_default_admin()

# ---------- Database Helper Functions ----------
def save_results_to_db(results_df):
    """Save resume results to database."""
    db = get_db_connection()
    if db is None:
        return
    try:
        if app.config['DB_TYPE'].lower() == 'mongodb':
            resumes = []
            for i, row in results_df.iterrows():
                resumes.append({
                    'filename': row['Resume'],
                    'match_percent': float(row['Match %']),
                    'uploaded_on': datetime.now()
                })
            if resumes:
                result = db.resumes.insert_many(resumes)
                print(f"✓ Saved {len(result.inserted_ids)} resumes to MongoDB")
        else:
            cursor = db.cursor()
            for i, row in results_df.iterrows():
                sql = "INSERT INTO resumes (filename, match_percent) VALUES (%s, %s)"
                val = (row['Resume'], float(row['Match %']))
                cursor.execute(sql, val)
            cursor.close()
            db.close()
    except Exception as e:
        print(f"❌ Failed to save results: {e}")

def save_candidate_to_db(name, email, match_percent, status='pending', job_description='', filename=''):
    """Save candidate information to database."""
    db = get_db_connection()
    if db is None:
        return None
    try:
        if app.config['DB_TYPE'].lower() == 'mongodb':
            candidate = {
                'name': name,
                'email': email,
                'match_percent': float(match_percent),
                'status': status,
                'job_description': job_description,
                'filename': filename,
                'created_on': datetime.now()
            }
            result = db.candidates.insert_one(candidate)
            return str(result.inserted_id)
        else:
            cursor = db.cursor()
            try:
                cursor.execute("ALTER TABLE candidates ADD COLUMN filename VARCHAR(255)")
            except:
                pass
            sql = "INSERT INTO candidates (name, email, match_percent, status, job_description, filename) VALUES (%s, %s, %s, %s, %s, %s)"
            val = (name, email, float(match_percent), status, job_description, filename)
            cursor.execute(sql, val)
            candidate_id = cursor.lastrowid
            cursor.close()
            db.close()
            return candidate_id
    except Exception as e:
        print(f"❌ Failed to save candidate: {e}")
        return None

def save_test_result(name, email, job_desc, score, total, status):
    """Save test results to database."""
    db = get_db_connection()
    if db is None:
        return
    try:
        if app.config['DB_TYPE'].lower() == 'mongodb':
            test_result = {
                'candidate_name': name,
                'candidate_email': email,
                'job_description': job_desc[:5000],
                'score': float(score),
                'total_questions': int(total),
                'status': status,
                'created_on': datetime.now()
            }
            db.test_results.insert_one(test_result)
        else:
            cursor = db.cursor()
            sql = "INSERT INTO test_results (candidate_name, candidate_email, job_description, score, total_questions, status) VALUES (%s, %s, %s, %s, %s, %s)"
            val = (name, email, job_desc[:5000], float(score), int(total), status)
            cursor.execute(sql, val)
            cursor.close()
            db.close()
    except Exception as e:
        print(f"❌ Failed to save test result: {e}")

def update_candidate_test_score(name, score):
    """Update candidate test score."""
    db = get_db_connection()
    if db is None:
        return None
    try:
        if app.config['DB_TYPE'].lower() == 'mongodb':
            result = db.candidates.update_one(
                {'name': name},
                {'$set': {'test_score': float(score), 'status': 'test_completed'}}
            )
            candidate = db.candidates.find_one({'name': name})
            return str(candidate['_id']) if candidate else None
        else:
            cursor = db.cursor()
            cursor.execute("UPDATE candidates SET test_score = %s, status = %s WHERE name = %s", (float(score), 'test_completed', name))
            cursor.execute("SELECT id FROM candidates WHERE name = %s", (name,))
            result = cursor.fetchone()
            candidate_id = result[0] if result else None
            cursor.close()
            db.close()
            return candidate_id
    except Exception as e:
        print(f"❌ Failed to update test score: {e}")
        return None

def send_result_to_hr(candidate_id, name, email, score):
    """Send test result notification to HR."""
    db = get_db_connection()
    if db is None:
        return
    try:
        if app.config['DB_TYPE'].lower() == 'mongodb':
            from bson import ObjectId
            try:
                candidate = db.candidates.find_one({'_id': ObjectId(candidate_id)})
            except:
                candidate = db.candidates.find_one({'_id': candidate_id})
            
            match_percent = candidate.get('match_percent', 0) if candidate else 0
            
            notification = {
                'candidate_id': candidate_id,
                'candidate_name': name,
                'candidate_email': email,
                'test_score': float(score),
                'match_percent': float(match_percent),
                'status': 'pending',
                'seen': False,
                'sent_on': datetime.now()
            }
            db.hr_notifications.insert_one(notification)
        else:
            cursor = db.cursor()
            cursor.execute("SELECT match_percent FROM candidates WHERE id = %s", (candidate_id,))
            result = cursor.fetchone()
            match_percent = result[0] if result else 0
            
            cursor.execute("INSERT INTO hr_notifications (candidate_id, candidate_name, candidate_email, test_score, match_percent) VALUES (%s, %s, %s, %s, %s)", 
                          (candidate_id, name, email, float(score), float(match_percent)))
            cursor.close()
            db.close()
        print(f"✓ HR notification sent for {name}")
    except Exception as e:
        print(f"❌ Failed to send HR notification: {e}")

# ---------- Global Variables ----------
selected_candidates = []
job_descriptions_store = {}

# ---------- NLP Preprocessing Function ----------
def preprocess_text(text):
    """Perform text preprocessing: lowercase, clean, tokenize, remove stopwords, lemmatize."""
    try:
        text = str(text).lower()
        text = re.sub(r'[^a-zA-Z\s]', '', text)
        tokens = word_tokenize(text)
        stop_words = set(stopwords.words('english'))
        tokens = [token for token in tokens if token not in stop_words and len(token) > 1]
        lemmatizer = WordNetLemmatizer()
        tokens = [lemmatizer.lemmatize(token) for token in tokens]
        return ' '.join(tokens)
    except Exception as e:
        print(f"❌ Preprocessing error: {e}")
        return str(text)

# ---------- Extract Text from Files ----------
def extract_text_from_file(filepath):
    """Extract text from PDF or DOCX files."""
    try:
        if filepath.endswith('.pdf'):
            with open(filepath, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                text = ' '.join([page.extract_text() for page in reader.pages if page.extract_text()])
                return text if text else ''
        elif filepath.endswith('.docx'):
            doc = docx.Document(filepath)
            text = ' '.join([p.text for p in doc.paragraphs])
            return text if text else ''
    except Exception as e:
        print(f"❌ Error extracting text: {e}")
    return ''

# ---------- Generate Test Questions using Gemini ----------
def generate_test_questions(job_description):
    """Generate test questions based on job description using Gemini AI."""
    try:
        print(f"🔍 Generating questions for job description: {job_description[:100]}...")
        if not job_description or len(job_description.strip()) < 10:
            return get_fallback_questions()

        model = genai.GenerativeModel(app.config['GEMINI_MODEL'])
        prompt = f"""
Generate exactly {app.config['TOTAL_TEST_QUESTIONS']} technical interview questions for: {job_description[:500]}

Return ONLY a JSON array:
[
  {{
    "question": "What is Android Activity?",
    "options": ["UI component", "Database", "Network", "Storage"],
    "correct_answer": "UI component",
    "points": {app.config['POINTS_PER_QUESTION']}
  }}
]
"""

        print("🤖 Calling Gemini API...")
        response = model.generate_content(prompt)
        text = response.text.strip()
        
        if text.startswith('```json'):
            text = text[7:]
        if text.endswith('```'):
            text = text[:-3]
        text = text.strip()

        start = text.find('[')
        end = text.rfind(']') + 1
        if start >= 0 and end > start:
            questions = json.loads(text[start:end])
            if isinstance(questions, list) and len(questions) > 0:
                valid_questions = [q for q in questions if 
                    all(k in q for k in ['question', 'options', 'correct_answer']) and
                    isinstance(q['options'], list) and len(q['options']) == 4]
                if len(valid_questions) >= app.config['TOTAL_TEST_QUESTIONS']:
                    return valid_questions[:app.config['TOTAL_TEST_QUESTIONS']]
        return get_fallback_questions()
    except Exception as e:
        print(f"❌ Error generating questions: {e}")
        return get_fallback_questions()

def get_fallback_questions():
    """Return randomized fallback questions when AI fails."""
    import random
    print("📚 Using randomized fallback questions")
    
    all_questions = [
        {
            "question": "What is Python?",
            "options": ["A programming language", "A database", "A web browser", "An operating system"],
            "correct_answer": "A programming language",
            "points": 10
        },
        {
            "question": "Which of the following is a Python web framework?",
            "options": ["Flask", "MySQL", "HTML", "CSS"],
            "correct_answer": "Flask",
            "points": 10
        },
        {
            "question": "What does SQL stand for?",
            "options": ["Structured Query Language", "Simple Query Language", "Standard Query Language", "System Query Language"],
            "correct_answer": "Structured Query Language",
            "points": 10
        },
        {
            "question": "Which HTML tag is used to create a hyperlink?",
            "options": ["&lt;a&gt;", "&lt;p&gt;", "&lt;div&gt;", "&lt;span&gt;"],
            "correct_answer": "&lt;a&gt;",
            "points": 10
        },
        {
            "question": "What is the purpose of CSS?",
            "options": ["To style web pages", "To create databases", "To write server-side code", "To handle user input"],
            "correct_answer": "To style web pages",
            "points": 10
        },
        {
            "question": "Which of these is a JavaScript framework?",
            "options": ["React", "Django", "Laravel", "Spring"],
            "correct_answer": "React",
            "points": 10
        },
        {
            "question": "What does API stand for?",
            "options": ["Application Programming Interface", "Advanced Programming Interface", "Automated Programming Interface", "Application Process Interface"],
            "correct_answer": "Application Programming Interface",
            "points": 10
        },
        {
            "question": "Which HTTP method is used to retrieve data?",
            "options": ["GET", "POST", "PUT", "DELETE"],
            "correct_answer": "GET",
            "points": 10
        },
        {
            "question": "What is Git used for?",
            "options": ["Version control", "Database management", "Web hosting", "File compression"],
            "correct_answer": "Version control",
            "points": 10
        },
        {
            "question": "Which of these is a machine learning library in Python?",
            "options": ["scikit-learn", "pandas", "numpy", "matplotlib"],
            "correct_answer": "scikit-learn",
            "points": 10
        },
        {
            "question": "What is the time complexity of binary search?",
            "options": ["O(log n)", "O(n)", "O(n²)", "O(1)"],
            "correct_answer": "O(log n)",
            "points": 10
        },
        {
            "question": "Which database is NoSQL?",
            "options": ["MongoDB", "MySQL", "PostgreSQL", "SQLite"],
            "correct_answer": "MongoDB",
            "points": 10
        },
        {
            "question": "What does REST stand for?",
            "options": ["Representational State Transfer", "Remote State Transfer", "Relational State Transfer", "Resource State Transfer"],
            "correct_answer": "Representational State Transfer",
            "points": 10
        },
        {
            "question": "Which is a containerization platform?",
            "options": ["Docker", "Apache", "Nginx", "Redis"],
            "correct_answer": "Docker",
            "points": 10
        },
        {
            "question": "What is the default port for HTTPS?",
            "options": ["443", "80", "8080", "3000"],
            "correct_answer": "443",
            "points": 10
        }
    ]
    
    # Randomize and return subset
    random.shuffle(all_questions)
    return all_questions[:app.config['TOTAL_TEST_QUESTIONS']]

# ---------- Evaluate Answer using Gemini ----------
def evaluate_answer(question, user_answer, correct_answer):
    """Evaluate if user answer is correct."""
    try:
        return user_answer.strip().lower() == correct_answer.strip().lower()
    except Exception as e:
        return False

# ---------- Routes ----------

@app.route('/login', methods=['GET', 'POST'])
def login():
    """User login route."""
    if request.method == 'POST':
        user = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        db = get_db_connection()
        if db is not None:
            try:
                if app.config['DB_TYPE'].lower() == 'mongodb':
                    result = db.admin_users.find_one({'username': user, 'password': password})
                    if result:
                        session['user'] = user
                        flash(f'Welcome {user}!', 'success')
                        return redirect(url_for('index'))
                else:
                    cursor = db.cursor()
                    cursor.execute("SELECT username FROM admin_users WHERE username = %s AND password = %s", (user, password))
                    result = cursor.fetchone()
                    cursor.close()
                    db.close()
                    
                    if result:
                        session['user'] = user
                        flash(f'Welcome {user}!', 'success')
                        return redirect(url_for('index'))
            except Exception as e:
                print(f"❌ Login error: {e}")
        
        return render_template('login.html', error="Invalid credentials!")
    return render_template('login.html')

@app.route('/')
@app.route('/home')
@app.route('/index')
def index():
    """Home page."""
    return render_template('index.html')

@app.route('/about')
def about():
    """About page."""
    return render_template('about.html')

@app.route('/upload', methods=['POST'])
def upload():
    """Upload and process resumes."""
    global selected_candidates, job_descriptions_store
    
    if 'user' not in session:
        flash('Please login first')
        return redirect(url_for('login'))
    
    job_description = request.form.get('job_description', '').strip()
    uploaded_files = request.files.getlist('files')

    if not job_description:
        flash('Please enter job description')
        return redirect(url_for('index'))

    resumes, filenames = [], []
    for file in uploaded_files:
        if file.filename:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            text = extract_text_from_file(filepath)
            if text:
                resumes.append(text)
                filenames.append(file.filename)
    if not resumes:
        flash('No valid resumes found')
        return redirect(url_for('index'))

    print("📋 Processing resumes...")
    processed_job_desc = preprocess_text(job_description)
    processed_resumes = [preprocess_text(r) for r in resumes]
    
    corpus = [processed_job_desc] + processed_resumes
    vectorizer = TfidfVectorizer(stop_words='english', max_features=500)
    tfidf_matrix = vectorizer.fit_transform(corpus)
    similarity = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()
    
    results = pd.DataFrame({
        'Resume': filenames,
        'Match %': (similarity * 100).round(2)
    }).sort_values(by='Match %', ascending=False)

    plt.figure(figsize=(10, 6))
    plt.barh(results['Resume'], results['Match %'], color='#38bdf8')
    plt.xlabel('Match %')
    plt.ylabel('Resume')
    plt.title('Resume Matching Results')
    plt.tight_layout()
    plt.savefig('static/result_chart.png', dpi=100)
    plt.close()
    
    save_results_to_db(results)
    job_descriptions_store = {row[0].replace('_', ' '): job_description for row in results.values}
    
    print("✓ Processing complete")
    return render_template('result.html', tables=results.values, chart='result_chart.png')

@app.route('/send-email', methods=['POST'])
def send_email():
    """Send single email."""
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Please login first'}), 401
    
    candidates = request.json.get('candidates', [])
    if not candidates:
        return jsonify({'success': False, 'message': 'No candidates provided'}), 400

    candidate = candidates[0]  # Assuming single email
    name = candidate.get('name', '').strip()
    filename = candidate.get('filename', '').strip()
    email = candidate.get('email', '').strip()
    match = candidate.get('match', 0)

    if not email or '@' not in email:
        return jsonify({'success': False, 'message': 'Invalid email address'}), 400
    
    if not name:
        return jsonify({'success': False, 'message': 'Candidate name is required'}), 400

    try:
        job_desc = job_descriptions_store.get(filename.replace('_', ' '), '')
        candidate_id = save_candidate_to_db(name, email, match, 'test_invited', job_desc, filename)
        
        test_link = f"http://localhost:5000/start_test/{candidate_id}" if candidate_id else f"http://localhost:5000/skill-test/{name.replace(' ', '_')}"
        
        msg = Message(
            subject='🎯 First Round Assessment - Skill Test Invitation',
            recipients=[email],
            html=f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #38bdf8;">🎯 First Round Assessment</h2>
                <p>Dear {name},</p>
                <p>Congratulations! Your resume matched <strong>{match}%</strong> with our job requirements.</p>
                
                <div style="background: #f0f9ff; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="color: #1e40af;">Assessment Overview:</h3>
                    <ul>
                        <li><strong>Technical Questions:</strong> Job-specific skill assessment</li>
                        <li><strong>Duration:</strong> Approximately 15-20 minutes</li>
                        <li><strong>Format:</strong> Multiple choice questions</li>
                    </ul>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{test_link}" style="background: #38bdf8; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold;">Start First Round Test</a>
                </div>
                
                <p style="color: #666; font-size: 14px;">Good luck with your assessment!</p>
            </div>
            """
        )
        msg.body = f"Dear {name},\n\nCongratulations! Your resume matched {match}% with our job requirements.\n\nStart Test: {test_link}\n\nGood luck!\n\nTeam HR"
        mail.send(msg)
        return jsonify({'success': True, 'message': f'Email sent to {email}'})
    except Exception as e:
        print(f"[ERROR] Email error: {e}")
        return jsonify({'success': False, 'message': 'Failed to send email'}), 500


@app.route('/send-skill-test-emails', methods=['POST'])
def send_skill_test_emails():
    """Send test invitation emails."""
    if 'user' not in session:
        return jsonify({'success': False}), 401

    candidates = request.json.get('candidates', [])
    if not candidates:
        return jsonify({'success': False, 'message': 'No candidates provided'})

    for candidate in candidates:
        name = candidate.get('name', '').strip()
        filename = candidate.get('filename', '').strip()
        email = candidate.get('email', '').strip()
        match = candidate.get('match', 0)
        
        if not email or '@' not in email:
            continue
        
        if not name:
            continue
        
        try:
            job_desc = job_descriptions_store.get(filename.replace('_', ' '), '')
            candidate_id = save_candidate_to_db(name, email, match, 'test_invited', job_desc, filename)
            
            test_link = f"http://localhost:5000/start_test/{candidate_id}" if candidate_id else f"http://localhost:5000/skill-test/{name.replace(' ', '_')}"
            
            msg = Message(
                subject='🎯 First Round Assessment - Skill Test Invitation',
                recipients=[email],
                html=f"""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                    <h2 style="color: #38bdf8;">🎯 First Round Assessment</h2>
                    <p>Dear {name},</p>
                    <p>Congratulations! Your resume matched <strong>{match}%</strong> with our job requirements.</p>
                    
                    <div style="background: #f0f9ff; padding: 20px; border-radius: 8px; margin: 20px 0;">
                        <h3 style="color: #1e40af;">Assessment Overview:</h3>
                        <ul>
                            <li><strong>Technical Questions:</strong> Job-specific skill assessment</li>
                            <li><strong>Duration:</strong> Approximately 15-20 minutes</li>
                            <li><strong>Format:</strong> Multiple choice questions</li>
                        </ul>
                    </div>
                    
                    <div style="text-align: center; margin: 30px 0;">
                        <a href="{test_link}" style="background: #38bdf8; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold;">Start First Round Test</a>
                    </div>
                    
                    <p style="color: #666; font-size: 14px;">Good luck with your assessment!</p>
                </div>
                """
            )
            msg.body = f"Dear {name},\n\nCongratulations! Your resume matched {match}% with our job requirements.\n\nStart Test: {test_link}\n\nGood luck!\n\nTeam HR"
            mail.send(msg)
        except Exception as e:
            print(f"❌ Email error: {e}")
    
    return jsonify({'success': True, 'message': f'Invitations sent to {len(candidates)} candidates'})

@app.route('/start_test/<candidate_id>')
def start_test(candidate_id):
    """Start test page for candidate by ID."""
    db = get_db_connection()
    if db is None:
        return "Database not available", 500

    try:
        if app.config['DB_TYPE'].lower() == 'mongodb':
            from bson import ObjectId
            try:
                candidate = db.candidates.find_one({'_id': ObjectId(candidate_id)})
            except:
                candidate = db.candidates.find_one({'_id': candidate_id})
            
            if not candidate:
                return "Candidate not found", 404
            
            candidate_name = candidate.get('name', '')
            candidate_email = candidate.get('email', '')
            job_desc = candidate.get('job_description', '')
        else:
            cursor = db.cursor()
            cursor.execute("SELECT name, email, job_description FROM candidates WHERE id = %s", (candidate_id,))
            result = cursor.fetchone()
            cursor.close()
            db.close()
            
            if not result:
                return "Candidate not found", 404

            candidate_name, candidate_email, job_desc = result
        
        return render_template('skill_test.html', candidate_name=candidate_name, candidate_email=candidate_email, job_description=job_desc)
    except Exception as e:
        print(f"❌ Error fetching candidate: {e}")
        return "Error loading test", 500

@app.route('/skill-test/<candidate_name>')
def skill_test(candidate_name):
    """Skill test page."""
    display_name = candidate_name.replace('_', ' ')
    db = get_db_connection()
    
    job_desc = ''
    if db is not None:
        try:
            cursor = db.cursor()
            cursor.execute("SELECT job_description FROM candidates WHERE name = %s", (candidate_name,))
            result = cursor.fetchone()
            job_desc = result[0] if result else ''
            cursor.close()
            db.close()
        except Exception as e:
            print(f"❌ Error fetching job description: {e}")
    
    # If not found in database, try the global store (for testing purposes)
    if not job_desc:
        job_desc = job_descriptions_store.get(display_name, '')
    
    # If still not found, use a default job description for testing
    if not job_desc:
        job_desc = """We are looking for a skilled Python Developer with experience in web development using Flask, Django, and REST APIs. The ideal candidate should have strong knowledge of Python programming, database management (MySQL, PostgreSQL), and front-end technologies (HTML, CSS, JavaScript). Experience with machine learning libraries like scikit-learn and data visualization tools is a plus. Responsibilities include developing web applications, writing clean and efficient code, collaborating with cross-functional teams, and participating in code reviews."""
        print(f"📝 Using default job description for testing: {job_desc[:100]}...")
    
    return render_template('skill_test.html', candidate_name=display_name, candidate_email='', job_description=job_desc)

@app.route('/api/get-test-questions', methods=['POST'])
def get_test_questions():
    """API to get test questions."""
    job_desc = request.json.get('job_description', '')
    questions = generate_test_questions(job_desc)
    return jsonify({'questions': questions})

@app.route('/api/submit-test-answers', methods=['POST'])
def submit_test_answers():
    """API to submit and evaluate test answers."""
    data = request.json
    name = data.get('candidate_name', '')
    email = data.get('candidate_email', '')
    job_desc = data.get('job_description', '')
    answers = data.get('answers', [])
    
    score = sum(10 for ans in answers if evaluate_answer(ans['question'], ans['answer'], ans['correct']))
    
    save_test_result(name, email, job_desc, score, len(answers), 'completed')
    candidate_id = update_candidate_test_score(name, score)
    
    # Send result to HR
    if candidate_id:
        send_result_to_hr(candidate_id, name, email, score)
    
    return jsonify({'success': True, 'score': score, 'total': len(answers) * 10})

@app.route('/top-3-results')
def top_3_results():
    """Display candidates grouped by interview rounds and job description."""
    if 'user' not in session:
        return redirect(url_for('login'))
    
    db = get_db_connection()
    if db is None:
        return render_template('top_3_results.html', rounds_data={})
    
    try:
        rounds_data = {
            'Test Invited': {},
            'First Round Completed': {},
            'Second Round Invited': {},
            'Second Round Completed': {},
            'HR Round Invited': {}
        }
        
        if app.config['DB_TYPE'].lower() == 'mongodb':
            candidates = list(db.candidates.find({}).sort('test_score', -1))
            
            for candidate in candidates:
                status = candidate.get('status', '')
                round_key = {
                    'test_invited': 'Test Invited',
                    'test_completed': 'First Round Completed',
                    'second_round_invited': 'Second Round Invited',
                    'second_round_completed': 'Second Round Completed',
                    'hr_round_invited': 'HR Round Invited'
                }.get(status, 'Test Invited')
                
                job_desc = candidate.get('job_description', 'General')[:40] + '...'
                if job_desc not in rounds_data[round_key]:
                    rounds_data[round_key][job_desc] = []
                
                rounds_data[round_key][job_desc].append({
                    'id': str(candidate['_id']),
                    'name': candidate.get('name', ''),
                    'email': candidate.get('email', ''),
                    'match_percent': candidate.get('match_percent', 0),
                    'test_score': candidate.get('test_score', 0),
                    'second_round_score': candidate.get('second_round_score', 0)
                })
        else:
            cursor = db.cursor()
            cursor.execute("SELECT id, name, email, match_percent, test_score, job_description, status, COALESCE(second_round_score, 0) FROM candidates ORDER BY test_score DESC")
            results = cursor.fetchall()
            cursor.close()
            db.close()
            
            for row in results:
                status = row[6]
                round_key = {
                    'test_invited': 'Test Invited',
                    'test_completed': 'First Round Completed',
                    'second_round_invited': 'Second Round Invited',
                    'second_round_completed': 'Second Round Completed',
                    'hr_round_invited': 'HR Round Invited'
                }.get(status, 'Test Invited')
                
                job_desc = (row[5][:40] + '...') if row[5] else 'General'
                if job_desc not in rounds_data[round_key]:
                    rounds_data[round_key][job_desc] = []
                
                rounds_data[round_key][job_desc].append({
                    'id': row[0],
                    'name': row[1],
                    'email': row[2],
                    'match_percent': row[3],
                    'test_score': row[4],
                    'second_round_score': row[7] if len(row) > 7 else 0
                })
        
        return render_template('top_3_results.html', rounds_data=rounds_data)
    except Exception as e:
        print(f"❌ Error: {e}")
        return render_template('top_3_results.html', rounds_data={})

def send_hr_round_email(name, email, match, score):
    """Send HR round invitation email."""
    try:
        msg = Message(
            subject='🎉 Selected for HR Round',
            recipients=[email],
            html=f"""<p>Hello {name},</p>
            <p>Congratulations! You are selected for HR Round.</p>
            <p>Resume Match: {match}% | Test Score: {score}/100</p>"""
        )
        msg.body = f"Hello {name},\n\nCongratulations! You are selected for HR Round.\n\nResume Match: {match}% | Test Score: {score}/100"
        mail.send(msg)
    except Exception as e:
        print(f"❌ Email error: {e}")

def generate_second_round_challenges(job_description, candidate_name):
    """Generate reasoning, aptitude, and coding challenges using Gemini AI."""
    import random
    try:
        model = genai.GenerativeModel(app.config['GEMINI_MODEL'])
        
        # Add randomization to get different questions each time
        topics = ['algorithms', 'data structures', 'problem solving', 'system design', 'programming logic']
        random_topic = random.choice(topics)
        random_number = random.randint(1, 1000)
        
        prompt = f"""
Create unique assessment questions #{random_number} focusing on {random_topic} for job: {job_description[:300]}

Return valid JSON:
{{
  "reasoning": [
    {{"question": "unique logic question", "options": ["A", "B", "C", "D"], "correct_answer": "A"}},
    {{"question": "different reasoning question", "options": ["A", "B", "C", "D"], "correct_answer": "B"}},
    {{"question": "another logic problem", "options": ["A", "B", "C", "D"], "correct_answer": "C"}}
  ],
  "aptitude": [
    {{"question": "math problem 1", "options": ["10", "20", "30", "40"], "correct_answer": "20"}},
    {{"question": "calculation question", "options": ["5", "15", "25", "35"], "correct_answer": "15"}},
    {{"question": "numerical reasoning", "options": ["100", "200", "300", "400"], "correct_answer": "200"}}
  ],
  "coding": [
    {{"question": "coding challenge 1", "sample_input": "input1", "expected_output": "output1", "difficulty": "easy"}},
    {{"question": "programming task", "sample_input": "input2", "expected_output": "output2", "difficulty": "medium"}}
  ]
}}

Make questions different from previous assessments.
"""
        
        print("🔄 Calling Gemini API for second round challenges...")
        print(f"📝 Using prompt: {prompt[:150]}...")
        response = model.generate_content(prompt)
        text = response.text.strip()
        print(f"📝 Gemini response: {text[:200]}...")
        
        # Clean response - remove markdown formatting
        text = text.replace('```json', '').replace('```', '').strip()
        
        # Find JSON boundaries
        start = text.find('{')
        end = text.rfind('}') + 1
        
        if start >= 0 and end > start:
            json_text = text[start:end]
            print(f"🔍 Extracted JSON: {json_text[:100]}...")
            
            try:
                challenges = json.loads(json_text)
                print(f"📊 Parsed challenges: {list(challenges.keys()) if isinstance(challenges, dict) else 'Invalid format'}")
                
                # Validate structure
                if (isinstance(challenges, dict) and 
                    all(k in challenges for k in ['reasoning', 'aptitude', 'coding']) and
                    all(isinstance(challenges[k], list) for k in ['reasoning', 'aptitude', 'coding'])):
                    
                    # Validate each section has questions
                    if (len(challenges['reasoning']) >= 1 and 
                        len(challenges['aptitude']) >= 1 and 
                        len(challenges['coding']) >= 1):
                        print("✅ AI-generated challenges validated successfully")
                        return challenges
                    else:
                        print("⚠️ Insufficient questions in AI response")
                else:
                    print("⚠️ Invalid challenge structure from AI")
            except json.JSONDecodeError as je:
                print(f"❌ JSON parsing error: {je}")
                print(f"📝 Raw JSON text: {json_text[:200]}...")
        else:
            print("⚠️ No valid JSON found in AI response")
        
        print("⚠️ AI response validation failed, using fallback challenges")
        return get_fallback_challenges()
    except Exception as e:
        print(f"❌ Error generating challenges: {e}")
        import traceback
        traceback.print_exc()
        print("📚 Using fallback challenges")
        return get_fallback_challenges()

def get_fallback_challenges():
    """Return randomized fallback challenges when AI fails."""
    import random
    
    reasoning_pool = [
        {"question": "If all roses are flowers and some flowers fade quickly, which conclusion is valid?", "options": ["All roses fade quickly", "Some roses may fade quickly", "No roses fade quickly", "All flowers are roses"], "correct_answer": "Some roses may fade quickly"},
        {"question": "In a sequence 2, 6, 18, 54, what comes next?", "options": ["108", "162", "216", "270"], "correct_answer": "162"},
        {"question": "If it takes 5 machines 5 minutes to make 5 widgets, how long for 100 machines to make 100 widgets?", "options": ["5 minutes", "20 minutes", "100 minutes", "500 minutes"], "correct_answer": "5 minutes"},
        {"question": "All programmers drink coffee. John drinks coffee. Is John a programmer?", "options": ["Yes, definitely", "No, definitely not", "Cannot be determined", "Only on weekdays"], "correct_answer": "Cannot be determined"},
        {"question": "If A > B and B > C, then:", "options": ["A = C", "A < C", "A > C", "Cannot determine"], "correct_answer": "A > C"}
    ]
    
    aptitude_pool = [
        {"question": "A train travels 60 km in 40 minutes. What is its speed in km/hr?", "options": ["90 km/hr", "100 km/hr", "120 km/hr", "150 km/hr"], "correct_answer": "90 km/hr"},
        {"question": "If 20% of a number is 50, what is 75% of that number?", "options": ["150", "187.5", "200", "225"], "correct_answer": "187.5"},
        {"question": "A rectangle has length 12cm and width 8cm. What is its area?", "options": ["96 sq cm", "40 sq cm", "20 sq cm", "48 sq cm"], "correct_answer": "96 sq cm"},
        {"question": "If 3x + 5 = 20, what is x?", "options": ["3", "4", "5", "6"], "correct_answer": "5"},
        {"question": "What is 15% of 200?", "options": ["25", "30", "35", "40"], "correct_answer": "30"}
    ]
    
    coding_pool = [
        {"question": "Write a function to find the maximum number in a list", "sample_input": "[3, 7, 2, 9, 1]", "expected_output": "9", "difficulty": "easy"},
        {"question": "Write a function to check if a string is a palindrome", "sample_input": "'racecar'", "expected_output": "True", "difficulty": "medium"},
        {"question": "Write a function to count vowels in a string", "sample_input": "'hello'", "expected_output": "2", "difficulty": "easy"},
        {"question": "Write a function to find factorial of a number", "sample_input": "5", "expected_output": "120", "difficulty": "medium"},
        {"question": "Write a function to remove duplicates from a list", "sample_input": "[1,2,2,3,3,4]", "expected_output": "[1,2,3,4]", "difficulty": "medium"}
    ]
    
    return {
        "reasoning": random.sample(reasoning_pool, 3),
        "aptitude": random.sample(aptitude_pool, 3),
        "coding": random.sample(coding_pool, 2)
    }

def send_second_round_email(candidate_id, name, email, job_description):
    """Send second round email with AI-generated challenges."""
    try:
        print(f"📧 Preparing second round email for {name}")
        challenges = generate_second_round_challenges(job_description, name)
        second_round_link = f"http://localhost:5000/second-round/{candidate_id}"
        
        # Create HTML email with challenges preview
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #38bdf8;">🎯 Second Round Assessment</h2>
            <p>Dear {name},</p>
            <p>Congratulations on passing the first round! You're now invited to the second round assessment.</p>
            
            <div style="background: #f0f9ff; padding: 20px; border-radius: 8px; margin: 20px 0;">
                <h3 style="color: #1e40af;">Assessment Overview:</h3>
                <ul>
                    <li><strong>Reasoning:</strong> {len(challenges['reasoning'])} logical reasoning questions</li>
                    <li><strong>Aptitude:</strong> {len(challenges['aptitude'])} mathematical/analytical questions</li>
                    <li><strong>Coding:</strong> {len(challenges['coding'])} programming challenges</li>
                </ul>
            </div>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="{second_round_link}" style="background: #38bdf8; color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px; font-weight: bold;">Start Second Round</a>
            </div>
            
            <p style="color: #666; font-size: 14px;">Time limit: 30 minutes | Good luck!</p>
        </div>
        """
        
        msg = Message(
            subject='🚀 Second Round Assessment - Technical Challenge',
            recipients=[email],
            html=html_content
        )
        msg.body = f"""Dear {name},

Congratulations! You're invited to the second round assessment.

Assessment includes:
- Reasoning: {len(challenges['reasoning'])} questions
- Aptitude: {len(challenges['aptitude'])} questions  
- Coding: {len(challenges['coding'])} challenges

Start here: {second_round_link}

Time limit: 30 minutes
Good luck!

Team HR"""
        
        mail.send(msg)
        
        # Store challenges in database for the test
        store_second_round_challenges(candidate_id, challenges)
        print(f"✅ Second round email sent successfully to {name}")
        
        return True
    except Exception as e:
        print(f"❌ Error sending second round email: {e}")
        return False

def evaluate_coding_answers(coding_answers):
    """Evaluate coding answers using Gemini AI."""
    if not coding_answers:
        return 0
    
    total_score = 0
    try:
        model = genai.GenerativeModel(app.config['GEMINI_MODEL'])
        
        for answer in coding_answers:
            question = answer.get('question', '')
            code = answer.get('answer', '').strip()
            
            if not code:
                continue
                
            prompt = f"""
Evaluate this coding solution:

Question: {question}
Code: {code}

Rate from 0-1 based on:
- Correctness of logic
- Code quality
- Completeness

Respond with only a number between 0 and 1 (e.g., 0.8)
"""
            
            response = model.generate_content(prompt)
            score_text = response.text.strip()
            
            try:
                score = float(score_text)
                if 0 <= score <= 1:
                    total_score += score
                else:
                    total_score += 0.5  # Default partial credit
            except:
                total_score += 0.5  # Default partial credit if parsing fails
                
    except Exception as e:
        print(f"❌ Error evaluating code: {e}")
        # Fallback: give partial credit for non-empty answers
        total_score = sum(0.5 for ans in coding_answers if ans.get('answer', '').strip())
    
    return total_score

def store_second_round_challenges(candidate_id, challenges):
    """Store second round challenges in database."""
    db = get_db_connection()
    if db is None:
        return
    
    try:
        if app.config['DB_TYPE'].lower() == 'mongodb':
            db.second_round_challenges.insert_one({
                'candidate_id': candidate_id,
                'challenges': challenges,
                'created_on': datetime.now(),
                'status': 'pending'
            })
        else:
            cursor = db.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS second_round_challenges (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    candidate_id VARCHAR(255),
                    challenges LONGTEXT,
                    created_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status VARCHAR(50) DEFAULT 'pending'
                )
            """)
            cursor.execute(
                "INSERT INTO second_round_challenges (candidate_id, challenges) VALUES (%s, %s)",
                (candidate_id, json.dumps(challenges))
            )
            cursor.close()
            db.close()
    except Exception as e:
        print(f"❌ Error storing challenges: {e}")

@app.route('/api/notifications')
def get_notifications():
    """Get HR notifications."""
    if 'user' not in session:
        return jsonify({'notifications': [], 'unseen_count': 0})
    
    db = get_db_connection()
    if db is None:
        return jsonify({'notifications': [], 'unseen_count': 0})
    
    try:
        notifications = []
        unseen_count = 0
        
        if app.config['DB_TYPE'].lower() == 'mongodb':
            docs = db.hr_notifications.find({'candidate_id': {'$ne': None}}).sort('sent_on', -1).limit(20)
            for doc in docs:
                seen_value = doc.get('seen', False)
                notif = {
                    'id': str(doc['_id']),
                    'candidate_name': doc.get('candidate_name', 'Unknown'),
                    'test_score': int(doc.get('test_score', 0)),
                    'combined_score': float(doc.get('combined_score', 0)) if doc.get('combined_score', None) is not None else None,
                    'sent_on': doc.get('sent_on', datetime.now()).strftime('%Y-%m-%d %H:%M'),
                    'candidate_id': str(doc.get('candidate_id', '')),
                    'seen': seen_value
                }
                notifications.append(notif)
                if not seen_value:
                    unseen_count += 1
        else:
            cursor = db.cursor()
            cursor.execute("SELECT id, candidate_name, test_score, COALESCE(combined_score, 0), sent_on, candidate_id, COALESCE(seen, 0) FROM hr_notifications WHERE candidate_id IS NOT NULL ORDER BY sent_on DESC LIMIT 20")
            for row in cursor.fetchall():
                seen_value = bool(row[6]) if row[6] is not None else False
                notif = {
                    'id': row[0],
                    'candidate_name': row[1] or 'Unknown',
                    'test_score': int(row[2]) if row[2] is not None else 0,
                    'combined_score': float(row[3]) if row[3] is not None else None,
                    'sent_on': row[4].strftime('%Y-%m-%d %H:%M') if row[4] else 'Unknown',
                    'candidate_id': row[5],
                    'seen': seen_value
                }
                notifications.append(notif)
                if not seen_value:
                    unseen_count += 1
            cursor.close()
            db.close()
        
        return jsonify({'notifications': notifications, 'unseen_count': unseen_count})
    except Exception as e:
        print(f"❌ Error fetching notifications: {e}")
        return jsonify({'notifications': [], 'unseen_count': 0})

@app.route('/api/notifications/mark-seen', methods=['POST'])
def mark_notification_seen():
    """Mark notification as seen."""
    if 'user' not in session:
        return jsonify({'success': False})
    
    notification_id = request.json.get('id')
    db = get_db_connection()
    if db is None:
        return jsonify({'success': False})
    
    try:
        if app.config['DB_TYPE'].lower() == 'mongodb':
            from bson import ObjectId
            try:
                db.hr_notifications.update_one(
                    {'_id': ObjectId(notification_id)},
                    {'$set': {'seen': True}}
                )
            except:
                db.hr_notifications.update_one(
                    {'_id': notification_id},
                    {'$set': {'seen': True}}
                )
        else:
            cursor = db.cursor()
            cursor.execute("UPDATE hr_notifications SET seen = TRUE WHERE id = %s", (notification_id,))
            cursor.close()
            db.close()
        return jsonify({'success': True})
    except Exception as e:
        print(f"❌ Error marking notification as seen: {e}")
        return jsonify({'success': False})

@app.route('/candidate-details/<candidate_id>')
def candidate_details(candidate_id):
    """Show candidate details page."""
    print(f"Accessing candidate details for ID: {candidate_id}")
    if 'user' not in session:
        return redirect(url_for('login'))
    
    db = get_db_connection()
    if db is None:
        print("Database not available")
        flash('Database not available')
        return redirect(url_for('index'))
    
    try:
        if app.config['DB_TYPE'].lower() == 'mongodb':
            print("Using MongoDB to fetch candidate")
            from bson import ObjectId
            try:
                candidate = db.candidates.find_one({'_id': ObjectId(candidate_id)})
                print(f"Found candidate with ObjectId: {candidate is not None}")
            except Exception as e:
                print(f"ObjectId failed, trying string: {e}")
                candidate = db.candidates.find_one({'_id': candidate_id})
                print(f"Found candidate with string ID: {candidate is not None}")
            
            if not candidate:
                print("Candidate not found in MongoDB")
                flash('Candidate not found')
                return redirect(url_for('index'))
            
            test_result = db.test_results.find_one(
                {'candidate_name': candidate.get('name')},
                sort=[('created_on', -1)]
            )
            
            candidate_data = {
                'id': str(candidate['_id']),
                'name': candidate.get('name', ''),
                'email': candidate.get('email', ''),
                'match_percent': candidate.get('match_percent', 0),
                'test_score': candidate.get('test_score', 0),
                'status': candidate.get('status', 'pending'),
                'created_on': candidate.get('created_on', datetime.now()),
                'filename': candidate.get('filename', candidate.get('name', '')),
                'job_description': candidate.get('job_description', ''),
                'second_round_score': candidate.get('second_round_score', 0),
                'test_details': test_result
            }
            print(f"Candidate data prepared: {candidate_data['name']}")
        else:
            print("Using MySQL to fetch candidate")
            cursor = db.cursor()
            cursor.execute("SELECT name, email, match_percent, test_score, status, created_on, filename, job_description, second_round_score FROM candidates WHERE id = %s", (candidate_id,))
            candidate = cursor.fetchone()
            
            if not candidate:
                flash('Candidate not found')
                return redirect(url_for('index'))
            
            cursor.execute("SELECT score, total_questions, created_on FROM test_results WHERE candidate_name = %s ORDER BY created_on DESC LIMIT 1", (candidate[0],))
            test_result = cursor.fetchone()
            
            cursor.close()
            db.close()
            
            candidate_data = {
                'id': candidate_id,
                'name': candidate[0],
                'email': candidate[1],
                'match_percent': candidate[2],
                'test_score': candidate[3],
                'status': candidate[4],
                'created_on': candidate[5],
                'filename': candidate[6] if len(candidate) > 6 else candidate[0],
                'job_description': candidate[7] if len(candidate) > 7 else '',
                'second_round_score': candidate[8] if len(candidate) > 8 else 0,
                'test_details': test_result
            }
        
        print("Rendering candidate details template")
        return render_template('candidate_details.html', candidate=candidate_data)
    except Exception as e:
        print(f"❌ Error fetching candidate details: {e}")
        import traceback
        traceback.print_exc()
        flash('Error loading candidate details')
        return redirect(url_for('index'))

@app.route('/view-resume/<filename>')
def view_resume(filename):
    """Serve resume PDF files."""
    if 'user' not in session:
        return redirect(url_for('login'))
    
    try:
        from flask import send_from_directory
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    except Exception as e:
        print(f"❌ Error serving resume: {e}")
        flash('Resume file not found')
        return redirect(url_for('index'))

@app.route('/approve-second-round/<candidate_id>', methods=['POST'])
def approve_second_round(candidate_id):
    """Approve candidate for second round and send email."""
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    db = get_db_connection()
    if db is None:
        return jsonify({'success': False, 'message': 'Database not available'}), 500
    
    try:
        if app.config['DB_TYPE'].lower() == 'mongodb':
            from bson import ObjectId
            try:
                candidate = db.candidates.find_one({'_id': ObjectId(candidate_id)})
            except:
                candidate = db.candidates.find_one({'_id': candidate_id})
            
            if not candidate:
                return jsonify({'success': False, 'message': 'Candidate not found'}), 404
            
            # Update status
            db.candidates.update_one(
                {'_id': candidate['_id']},
                {'$set': {'status': 'second_round_invited'}}
            )
            
            name = candidate.get('name', '')
            email = candidate.get('email', '')
            job_desc = candidate.get('job_description', '')
        else:
            cursor = db.cursor()
            cursor.execute("SELECT name, email, job_description FROM candidates WHERE id = %s", (candidate_id,))
            result = cursor.fetchone()
            
            if not result:
                return jsonify({'success': False, 'message': 'Candidate not found'}), 404
            
            name, email, job_desc = result
            
            # Update status
            cursor.execute("UPDATE candidates SET status = 'second_round_invited' WHERE id = %s", (candidate_id,))
            cursor.close()
            db.close()
        
        # Send second round email
        success = send_second_round_email(candidate_id, name, email, job_desc)
        
        if success:
            return jsonify({'success': True, 'message': f'Second round invitation sent to {name}'})
        else:
            return jsonify({'success': False, 'message': 'Failed to send email'}), 500
            
    except Exception as e:
        print(f"❌ Error approving second round: {e}")
        return jsonify({'success': False, 'message': 'Server error'}), 500

@app.route('/approve-hr-round/<candidate_id>', methods=['POST'])
def approve_hr_round(candidate_id):
    """Approve candidate for HR round and send email."""
    if 'user' not in session:
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    db = get_db_connection()
    if db is None:
        return jsonify({'success': False, 'message': 'Database not available'}), 500
    
    try:
        if app.config['DB_TYPE'].lower() == 'mongodb':
            from bson import ObjectId
            try:
                candidate = db.candidates.find_one({'_id': ObjectId(candidate_id)})
            except:
                candidate = db.candidates.find_one({'_id': candidate_id})
            
            if not candidate:
                return jsonify({'success': False, 'message': 'Candidate not found'}), 404
            
            db.candidates.update_one(
                {'_id': candidate['_id']},
                {'$set': {'status': 'hr_round_invited'}}
            )
            
            name = candidate.get('name', '')
            email = candidate.get('email', '')
        else:
            cursor = db.cursor()
            cursor.execute("SELECT name, email FROM candidates WHERE id = %s", (candidate_id,))
            result = cursor.fetchone()
            
            if not result:
                return jsonify({'success': False, 'message': 'Candidate not found'}), 404
            
            name, email = result
            cursor.execute("UPDATE candidates SET status = 'hr_round_invited' WHERE id = %s", (candidate_id,))
            cursor.close()
            db.close()
        
        # Send HR round email
        msg = Message(
            subject='🎉 Selected for HR Round - Final Interview',
            recipients=[email],
            html=f"""
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
                <h2 style="color: #38bdf8;">🎉 Congratulations!</h2>
                <p>Dear {name},</p>
                <p>We are pleased to inform you that you have successfully completed our technical assessments and have been selected for the HR round.</p>
                
                <div style="background: #f0f9ff; padding: 20px; border-radius: 8px; margin: 20px 0; text-align: center;">
                    <h3 style="color: #1e40af; margin: 0;">HR will contact you soon</h3>
                    <p style="margin: 10px 0 0 0; color: #666;">Please keep your phone available for the interview scheduling call</p>
                </div>
                
                <p>Thank you for your patience and we look forward to speaking with you soon.</p>
                <p>Best regards,<br>HR Team</p>
            </div>
            """
        )
        msg.body = f"""Dear {name},

Congratulations! You have been selected for the HR round.

HR will contact you soon for the final interview.

Best regards,
HR Team"""
        
        mail.send(msg)
        return jsonify({'success': True, 'message': f'HR round notification sent to {name}'})
        
    except Exception as e:
        print(f"❌ Error approving HR round: {e}")
        return jsonify({'success': False, 'message': 'Server error'}), 500

@app.route('/second-round/<candidate_id>')
def second_round_test(candidate_id):
    """Second round test page."""
    db = get_db_connection()
    if db is None:
        return "Database not available", 500
    
    try:
        # Get candidate info
        if app.config['DB_TYPE'].lower() == 'mongodb':
            from bson import ObjectId
            try:
                candidate = db.candidates.find_one({'_id': ObjectId(candidate_id)})
            except:
                candidate = db.candidates.find_one({'_id': candidate_id})
            
            if not candidate:
                return "Candidate not found", 404
            
            # Get challenges
            challenges_doc = db.second_round_challenges.find_one({'candidate_id': candidate_id})
            challenges = challenges_doc.get('challenges', get_fallback_challenges()) if challenges_doc else get_fallback_challenges()
            
            candidate_data = {
                'name': candidate.get('name', ''),
                'email': candidate.get('email', '')
            }
        else:
            cursor = db.cursor()
            cursor.execute("SELECT name, email FROM candidates WHERE id = %s", (candidate_id,))
            result = cursor.fetchone()
            
            if not result:
                return "Candidate not found", 404
            
            candidate_data = {'name': result[0], 'email': result[1]}
            
            # Get challenges
            cursor.execute("SELECT challenges FROM second_round_challenges WHERE candidate_id = %s", (candidate_id,))
            challenge_result = cursor.fetchone()
            challenges = json.loads(challenge_result[0]) if challenge_result else get_fallback_challenges()
            
            cursor.close()
            db.close()
        
        return render_template('second_round.html', 
                             candidate=candidate_data, 
                             challenges=challenges,
                             candidate_id=candidate_id)
    except Exception as e:
        print(f"❌ Error loading second round: {e}")
        return "Error loading test", 500

@app.route('/api/submit-second-round', methods=['POST'])
def submit_second_round():
    """Submit second round answers - with validation and logging."""
    data = request.json
    candidate_id = data.get('candidate_id')
    answers = data.get('answers', {})
    
    db = get_db_connection()
    if db is None:
        return jsonify({'success': False, 'message': 'Database error'}), 500
    
    try:
        # Log received answers for debugging
        reasoning_count = len(answers.get('reasoning', []))
        aptitude_count = len(answers.get('aptitude', []))
        coding_count = len(answers.get('coding', []))
        
        print(f"📊 [Second Round Submission] Candidate: {candidate_id}")
        print(f"   Reasoning questions: {reasoning_count}")
        print(f"   Aptitude questions: {aptitude_count}")
        print(f"   Coding questions: {coding_count}")
        
        # Show which questions were answered
        reasoning_answered = sum(1 for ans in answers.get('reasoning', []) if ans.get('answer'))
        aptitude_answered = sum(1 for ans in answers.get('aptitude', []) if ans.get('answer'))
        coding_answered = sum(1 for ans in answers.get('coding', []) if ans.get('answer', '').strip())
        
        print(f"   Answered: Reasoning {reasoning_answered}/{reasoning_count}, Aptitude {aptitude_answered}/{aptitude_count}, Coding {coding_answered}/{coding_count}")
        
        # Calculate scores
        reasoning_score = sum(1 for ans in answers.get('reasoning', []) if ans.get('correct', False))
        aptitude_score = sum(1 for ans in answers.get('aptitude', []) if ans.get('correct', False))
        coding_score = evaluate_coding_answers(answers.get('coding', []))
        
        total_score = reasoning_score + aptitude_score + coding_score
        max_score = 3 + 3 + 2  # 3 reasoning + 3 aptitude + 2 coding
        percentage = (total_score / max_score) * 100
        
        print(f"   Scores: Reasoning {reasoning_score}/{reasoning_count}, Aptitude {aptitude_score}/{aptitude_count}, Coding {coding_score:.1f}/2")
        print(f"   Total: {total_score}/{max_score} ({percentage:.1f}%)\n")
        
        # Store results
        if app.config['DB_TYPE'].lower() == 'mongodb':
            db.second_round_results.insert_one({
                'candidate_id': candidate_id,
                'reasoning_score': reasoning_score,
                'aptitude_score': aptitude_score,
                'coding_score': coding_score,
                'total_score': total_score,
                'percentage': percentage,
                'answers': answers,
                'submitted_on': datetime.now()
            })
            
            # Update candidate status and send HR notification
            from bson import ObjectId
            try:
                candidate = db.candidates.find_one({'_id': ObjectId(candidate_id)})
                db.candidates.update_one(
                    {'_id': ObjectId(candidate_id)},
                    {'$set': {'status': 'second_round_completed', 'second_round_score': percentage}}
                )
            except:
                candidate = db.candidates.find_one({'_id': candidate_id})
                db.candidates.update_one(
                    {'_id': candidate_id},
                    {'$set': {'status': 'second_round_completed', 'second_round_score': percentage}}
                )
            
            # Send second round result to HR
            if candidate:
                db.hr_notifications.insert_one({
                    'candidate_id': candidate_id,
                    'candidate_name': candidate.get('name', ''),
                    'candidate_email': candidate.get('email', ''),
                    'test_score': percentage,
                    'match_percent': candidate.get('match_percent', 0),
                    'combined_score': (candidate.get('test_score', 0) + percentage) / 2.0,
                    'status': 'second_round_completed',
                    'seen': False,
                    'sent_on': datetime.now()
                })
        else:
            cursor = db.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS second_round_results (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    candidate_id VARCHAR(255),
                    reasoning_score INT,
                    aptitude_score INT,
                    coding_score INT,
                    total_score INT,
                    percentage FLOAT,
                    answers LONGTEXT,
                    submitted_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                INSERT INTO second_round_results 
                (candidate_id, reasoning_score, aptitude_score, coding_score, total_score, percentage, answers)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (candidate_id, reasoning_score, aptitude_score, coding_score, total_score, percentage, json.dumps(answers)))
            
            # Add columns if not exist
            try:
                cursor.execute("ALTER TABLE candidates ADD COLUMN second_round_score FLOAT DEFAULT 0")
            except:
                pass
            try:
                cursor.execute("ALTER TABLE hr_notifications MODIFY candidate_id VARCHAR(255)")
            except:
                pass
            
            cursor.execute("UPDATE candidates SET status = 'second_round_completed', second_round_score = %s WHERE id = %s", 
                          (percentage, candidate_id))
            
            # Get candidate info for HR notification (include existing test_score)
            cursor.execute("SELECT name, email, match_percent, COALESCE(test_score, 0) FROM candidates WHERE id = %s", (candidate_id,))
            candidate = cursor.fetchone()
            
            if candidate:
                # Ensure hr_notifications has combined_score column (ignore errors)
                try:
                    cursor.execute("ALTER TABLE hr_notifications ADD COLUMN combined_score FLOAT DEFAULT NULL")
                except Exception:
                    pass

                round1_score = float(candidate[3]) if len(candidate) > 3 and candidate[3] is not None else 0.0
                combined = (round1_score + float(percentage)) / 2.0
                cursor.execute("INSERT INTO hr_notifications (candidate_id, candidate_name, candidate_email, test_score, match_percent, combined_score, status) VALUES (%s, %s, %s, %s, %s, %s, %s)", 
                              (candidate_id, candidate[0], candidate[1], percentage, candidate[2], combined, 'second_round_completed'))
            
            cursor.close()
            db.close()
        
        return jsonify({
            'success': True,
            'reasoning_score': reasoning_score,
            'aptitude_score': aptitude_score,
            'coding_score': coding_score,
            'total_score': total_score,
            'percentage': round(percentage, 1)
        })
        
    except Exception as e:
        print(f"❌ Error submitting second round: {e}")
        return jsonify({'success': False, 'message': 'Submission failed'}), 500

@app.route('/second-round-result/<candidate_id>')
def second_round_result(candidate_id):
    """Show second round results."""
    db = get_db_connection()
    if db is None:
        return render_template('second_round_result.html', candidate={'name': '', 'email': '', 'percentage': 0, 'reasoning_score': 0, 'aptitude_score': 0, 'coding_score': 0, 'total_score': 0, 'test_score': 0})
    
    candidate_data = None
    try:
        if app.config['DB_TYPE'].lower() == 'mongodb':
            from bson import ObjectId
            try:
                candidate = db.candidates.find_one({'_id': ObjectId(candidate_id)})
            except:
                candidate = db.candidates.find_one({'_id': candidate_id})
            
            result = db.second_round_results.find_one({'candidate_id': candidate_id})
            
            if candidate and result:
                candidate_data = {
                    'name': candidate.get('name', ''),
                    'email': candidate.get('email', ''),
                    'reasoning_score': result.get('reasoning_score', 0),
                    'aptitude_score': result.get('aptitude_score', 0),
                    'coding_score': result.get('coding_score', 0),
                    'total_score': result.get('total_score', 0),
                    'percentage': result.get('percentage', 0),
                    'test_score': candidate.get('test_score', 0)
                }
        else:
            cursor = db.cursor()
            cursor.execute("SELECT name, email, test_score FROM candidates WHERE id = %s", (candidate_id,))
            candidate = cursor.fetchone()
            
            cursor.execute("SELECT reasoning_score, aptitude_score, coding_score, total_score, percentage FROM second_round_results WHERE candidate_id = %s", (candidate_id,))
            result = cursor.fetchone()
            
            cursor.close()
            db.close()
            
            if candidate and result:
                candidate_data = {
                    'name': candidate[0],
                    'email': candidate[1],
                    'reasoning_score': result[0],
                    'aptitude_score': result[1],
                    'coding_score': result[2],
                    'total_score': result[3],
                    'percentage': result[4],
                    'test_score': candidate[2] if len(candidate) > 2 else 0
                }
        
        if not candidate_data:
            print(f"⚠️ No candidate data found for ID: {candidate_id}")
            candidate_data = {'name': '', 'email': '', 'percentage': 0, 'reasoning_score': 0, 'aptitude_score': 0, 'coding_score': 0, 'total_score': 0, 'test_score': 0}
        
        return render_template('second_round_result.html', candidate=candidate_data)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        candidate_data = {'name': '', 'email': '', 'percentage': 0, 'reasoning_score': 0, 'aptitude_score': 0, 'coding_score': 0, 'total_score': 0, 'test_score': 0}
        return render_template('second_round_result.html', candidate=candidate_data)

@app.route('/logout')
def logout():
    """Logout route."""
    session.clear()
    return redirect(url_for('login'))

# ---------- Diagnostic: Send test email route ----------
@app.route('/send-test-email')
def send_test_email():
    # Detailed diagnostic endpoint
    user = app.config.get('MAIL_USERNAME')
    pwd = app.config.get('MAIL_PASSWORD')
    if not user or not pwd:
        return "Mail credentials not configured (check .env).", 400
    try:
        # Temporarily use smtplib for verbose error output
        import smtplib, ssl
        from email.message import EmailMessage
        server = app.config.get('MAIL_SERVER', 'smtp.gmail.com')
        port = int(app.config.get('MAIL_PORT', 587))
        msg = EmailMessage()
        msg.set_content('This is a test email from AI Resume app.')
        msg['Subject'] = '[AI Resume] Test Email'
        msg['From'] = user
        msg['To'] = user

        if port == 465:
            ctx = ssl.create_default_context()
            with smtplib.SMTP_SSL(server, port, context=ctx) as s:
                s.set_debuglevel(1)
                s.login(user, pwd)
                s.send_message(msg)
        else:
            s = smtplib.SMTP(server, port, timeout=20)
            s.set_debuglevel(1)
            s.ehlo()
            s.starttls()
            s.ehlo()
            s.login(user, pwd)
            s.send_message(msg)
            s.quit()
        return "Test email sent, check inbox.", 200
    except Exception as e:
        # return detailed exception (safe for dev)
        return f"SMTP error: {repr(e)}", 500

if __name__ == '__main__':
    app.run(debug=app.config['DEBUG'])
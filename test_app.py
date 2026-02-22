<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>AI Resume Shortlisting Tool</title>
  <link href="https://fonts.googleapis.com/css2?family=Poppins:wght@300;500;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
  <link rel="stylesheet" href="{{ url_for('static', filename='css/theme.css') }}">

  <style>
    .notification-wrapper {
      position: relative;
    }

    .notification-icon {
      position: relative;
      cursor: pointer;
      padding: 8px 12px;
      color: #e2e8f0;
      font-size: 1.2rem;
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.05);
      border: 1px solid transparent;
      transition: all 0.3s ease;
    }

    .notification-icon:hover {
      color: #38bdf8;
      background: rgba(56, 189, 248, 0.1);
      border-color: rgba(56, 189, 248, 0.3);
      transform: translateY(-1px);
    }

    .notification-count {
      position: absolute;
      top: -2px;
      right: -2px;
      background: linear-gradient(135deg, #ef4444, #dc2626);
      color: white;
      border-radius: 50%;
      width: 20px;
      height: 20px;
      font-size: 0.7rem;
      font-weight: 600;
      display: none;
      align-items: center;
      justify-content: center;
      box-shadow: 0 2px 4px rgba(239, 68, 68, 0.4);
      animation: pulse 2s infinite;
    }

    .notification-count.show {
      display: flex;
    }

    @keyframes pulse {
      0%, 100% { transform: scale(1); }
      50% { transform: scale(1.1); }
    }

    .notification-dropdown {
      position: absolute;
      top: calc(100% + 10px);
      right: 0;
      background: rgba(255, 255, 255, 0.95);
      backdrop-filter: blur(10px);
      color: #1f2937;
      width: 320px;
      max-height: 400px;
      overflow-y: auto;
      border-radius: 12px;
      box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
      border: 1px solid rgba(56, 189, 248, 0.2);
      display: none;
      z-index: 1000;
    }

    .notification-item {
      padding: 15px;
      border-bottom: 1px solid rgba(0, 0, 0, 0.1);
      cursor: pointer;
      transition: all 0.3s ease;
    }

    .notification-item:hover {
      background: rgba(56, 189, 248, 0.1);
    }

    .notification-item.unseen {
      background: linear-gradient(135deg, rgba(56, 189, 248, 0.1), rgba(14, 165, 233, 0.05));
      border-left: 4px solid #38bdf8;
      font-weight: 600;
    }

    .notification-item:last-child {
      border-bottom: none;
    }

    .hero {
      height: 100vh;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      text-align: center;
      padding: 2rem;
    }

    .hero h2 {
      font-size: 2.8rem;
      font-weight: 700;
      color: #38bdf8;
      animation: fadeInDown 1s ease;
    }

    .hero p {
      font-size: 1.2rem;
      color: #e2e8f0;
      margin-top: 15px;
      animation: fadeInUp 1s ease;
    }

    .btn {
      margin-top: 25px;
      border-radius: 25px;
    }

    .btn:hover {
      transform: scale(1.05);
    }

    .upload-section {
      background: rgba(255, 255, 255, 0.05);
      margin: 4rem auto;
      width: 80%;
      padding: 2rem;
      border-radius: 20px;
      text-align: center;
      box-shadow: 0 0 15px rgba(56, 189, 248, 0.3);
      animation: fadeInUp 1.2s ease;
    }

    .upload-section h3 {
      color: #38bdf8;
      margin-bottom: 1rem;
    }

    input[type="file"],
    textarea {
      width: 80%;
      margin: 0.8rem 0;
      background: rgba(255, 255, 255, 0.1);
      color: var(--text-light);
      border: 2px solid rgba(56, 189, 248, 0.3);
    }

    input[type="file"]:focus,
    textarea:focus {
      border-color: var(--primary-color);
      box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.1);
    }

    textarea {
      height: 120px;
      resize: none;
    }

    footer {
      background: rgba(255, 255, 255, 0.05);
      text-align: center;
      padding: 1rem;
      font-size: 0.9rem;
      color: #cbd5e1;
    }

    footer span {
      color: #38bdf8;
      font-weight: 600;
    }
  </style>
</head>
<body>
  <header>
    <h1><i class="fas fa-robot"></i> AI Resume Shortlisting Tool</h1>
    <nav>
      {% if session.get('user') %}
        <a href="{{ url_for('index') }}">Dashboard</a>
        <a href="{{ url_for('top_3_results') }}">Top Results</a>
        <div class="notification-wrapper">
          <div class="notification-icon" onclick="toggleNotifications()">
            <i class="fas fa-bell"></i>
            <span class="notification-count" id="notificationCount">0</span>
          </div>
          <div class="notification-dropdown" id="notificationDropdown"></div>
        </div>
        <a href="{{ url_for('logout') }}">Logout</a>
      {% else %}
        <a href="{{ url_for('index') }}">Home</a>
        <a href="{{ url_for('login') }}">Login</a>
        <a href="{{ url_for('about') }}">About</a>
      {% endif %}
    </nav>
  </header>

  <section class="hero">
    <h2>Smart Hiring Starts Here 🤖</h2>
    <p>Upload resumes, match job descriptions, and let AI shortlist the best candidates in seconds.</p>
    {% if session.get('user') %}
      <button class="btn" id="getStarted">Get Started</button>
    {% else %}
      <a class="btn" href="{{ url_for('login') }}">Login to Get Started</a>
    {% endif %}
  </section>

  <section id="upload" class="upload-section">
    <h3>Upload Resumes & Job Description</h3>
  {% if session.get('user') %}
    <form action="/upload" method="POST" enctype="multipart/form-data">
      <input type="file" name="files" multiple accept=".pdf,.doc,.docx" required /><br>
      <textarea name="job_description" placeholder="Paste Job Description here..." required></textarea><br>
      <button type="submit" class="btn">Analyze & Shortlist</button>
    </form>
    {% else %}
    <p>Please <a href="{{ url_for('login') }}">login</a> to upload resumes and analyze.</p>
    {% endif %}
  </section>

  <footer>
    © 2025 <span>AI Resume Shortlisting Tool</span> | Designed by MiniProject Team KVGCE💙
  </footer>

  <script>
    function toggleNotifications() {
      const dropdown = document.getElementById('notificationDropdown');
      if (dropdown.style.display === 'block') {
        dropdown.style.display = 'none';
      } else {
        loadNotifications();
        dropdown.style.display = 'block';
      }
    }

    document.addEventListener('click', function(event) {
      const dropdown = document.getElementById('notificationDropdown');
      const icon = document.querySelector('.notification-icon');
      if (dropdown && !dropdown.contains(event.target) && !icon.contains(event.target)) {
        dropdown.style.display = 'none';
      }
    });



    function loadNotifications() {
      fetch('/api/notifications')
        .then(response => response.json())
        .then(data => {
          const dropdown = document.getElementById('notificationDropdown');
          const count = document.getElementById('notificationCount');
          
          count.textContent = data.unseen_count || 0;
          if (data.unseen_count > 0) {
            count.classList.add('show');
          } else {
            count.classList.remove('show');
          }
          
          if (!data.notifications || data.notifications.length === 0) {
            dropdown.innerHTML = '<div class="notification-item" style="text-align: center; color: #666;">📭 No notifications yet</div>';
          } else {
            dropdown.innerHTML = data.notifications.map(n => 
              `<div class="notification-item ${n.seen ? '' : 'unseen'}" data-candidate-id="${n.candidate_id}" data-notification-id="${n.id}">
                <div>
                  <strong>🎯 ${n.candidate_name}</strong> completed test<br>
                  <small>Score: ${n.test_score}/100 points</small><br>
                  <small>${n.sent_on}</small>
                </div>
              </div>`
            ).join('');
            
            // Add click listeners
            dropdown.querySelectorAll('.notification-item').forEach(item => {
              item.addEventListener('click', function() {
                const candidateId = this.getAttribute('data-candidate-id');
                const notificationId = this.getAttribute('data-notification-id');
                
                if (candidateId) {
                  // Mark as seen
                  if (!this.classList.contains('seen')) {
                    fetch('/api/notifications/mark-seen', {
                      method: 'POST',
                      headers: {'Content-Type': 'application/json'},
                      body: JSON.stringify({id: notificationId})
                    });
                    
                    // Update badge count
                    const count = document.getElementById('notificationCount');
                    const currentCount = parseInt(count.textContent) || 0;
                    const newCount = Math.max(0, currentCount - 1);
                    count.textContent = newCount;
                    if (newCount === 0) {
                      count.classList.remove('show');
                    }
                  }
                  
                  // Navigate
                  setTimeout(() => {
                    window.location.href = '/candidate-details/' + candidateId;
                  }, 100);
                }
              });
            });
          }
        })
        .catch(error => console.error('Error:', error));
    }

    {% if session.get('user') %}
      document.addEventListener('DOMContentLoaded', function() {
        loadNotifications();
        setInterval(loadNotifications, 30000);
      });
    {% endif %}
    
    const getStartedBtn = document.getElementById('getStarted');
    if (getStartedBtn) {
      getStartedBtn.addEventListener('click', function() {
      var isLoggedIn = {{ (session.get('user') is not none) | tojson }};
      if (isLoggedIn) {
        document.getElementById('upload').scrollIntoView({ behavior: 'smooth' });
      } else {
        window.location.href = "{{ url_for('login') }}";
      }
      });
    }
  </script>
</body>
</html>
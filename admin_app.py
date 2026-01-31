import os
import sqlite3
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, session, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.secret_key = "95bebc58c77ee810005033378becf1838d9fc2e0fe667259" # बदला: अधिक सुरक्षित की वापरा
DATABASE = 'college_results.db'

# --- १. डेटाबेस फंक्शन्स ---
def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def log_activity(action, desc):
    """अ‍ॅडमिनच्या सर्व कृतींची नोंद ठेवणे"""
    conn = get_db_connection()
    conn.execute("INSERT INTO activity_logs (action_type, description) VALUES (?, ?)", (action, desc))
    conn.commit()
    conn.close()

# --- २. लॉगिन गार्ड (Middleware) ---
def admin_required(f):
    def wrap(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('admin_login_page'))
        return f(*args, **kwargs)
    wrap.__name__ = f.__name__
    return wrap

# --- ३. सुरक्षित अ‍ॅडमिन राउट्स ---

# 🔐 Hidden Login URL
@app.route('/secure-admin-v1-access', methods=['GET', 'POST'])
def admin_login_page():
    if request.method == 'POST':
        user = request.form['username']
        pw = request.form['password']
        
        conn = get_db_connection()
        admin = conn.execute("SELECT * FROM admin_config LIMIT 1").fetchone()
        conn.close()
        
        if admin and user == admin['admin_username'] and check_password_hash(admin['admin_password_hash'], pw):
            session['admin_logged_in'] = True
            log_activity("LOGIN", f"Admin {user} logged in")
            return redirect(url_for('admin_dashboard'))
        
        return "Invalid Credentials", 401
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    try:
        conn = get_db_connection()
        # डेटाबेस टेबल अस्तित्वात असल्याची खात्री करा
        stats = {
            'total_students': conn.execute("SELECT COUNT(*) FROM students").fetchone()[0],
            'total_subjects': conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0],
            'recent_logs': conn.execute("SELECT * FROM activity_logs ORDER BY timestamp DESC LIMIT 5").fetchall()
        }
        conn.close()
        
        # ✨ फिक्स: 'admin/' फोल्डरचा संदर्भ द्या
        return render_template('admin/dashboard.html', stats=stats) 
        
    except Exception as e:
        # एरर अधिक स्पष्टपणे समजण्यासाठी हे वापरा
        return f"Dashboard Error: {str(e)} (Check if admin/dashboard.html exists in templates)"

# ५. डेटा मॅनेजर मॉड्यूल
@app.route('/admin/data-manager')
@admin_required
def data_manager_page():
    try:
        conn = get_db_connection()
        # डेटाबेस मधील सर्व टेबल्सची नावे मिळवणे
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';").fetchall()
        conn.close()
        return render_template('admin/data_manager.html', tables=[t['name'] for t in tables])
    except Exception as e:
        return f"Manager Error: {str(e)}"

@app.route('/admin/data-manager/view', methods=['POST'])
@admin_required
def view_table_data():
    try:
        table_name = request.form.get('table_name')
        conn = get_db_connection()
        
        # निवडलेल्या टेबलचा सर्व डेटा मिळवणे
        data = conn.execute(f"SELECT * FROM {table_name}").fetchall()
        
        # कॉलम्सची नावे डायनॅमिकली मिळवणे
        column_names = [description[0] for description in conn.execute(f"SELECT * FROM {table_name} LIMIT 1").description]
        
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';").fetchall()
        conn.close()
        
        return render_template('admin/data_manager.html', 
                               tables=[t['name'] for t in tables],
                               selected_table=table_name,
                               columns=column_names,
                               rows=data)
    except Exception as e:
        return f"Table Access Error: {str(e)}"


# ⚠️ Danger Zone: Secure Truncate
@app.route('/admin/danger/truncate-students', methods=['POST'])
@admin_required
def truncate_data():
    try:
        sec_pw = request.form['secondary_password']
        
        conn = get_db_connection()
        admin = conn.execute("SELECT secondary_password_hash FROM admin_config").fetchone()
        
        # Secondary Password Confirmation
        if check_password_hash(admin['secondary_password_hash'], sec_pw):
            conn.execute("DELETE FROM students")
            conn.commit()
            log_activity("DANGER", "Truncated all student records")
            conn.close()
            return "Database Cleared Successfully"
        
        conn.close()
        return "Unauthorized: Incorrect Operations Password", 403
    except Exception as e:
        return f"System Error: {str(e)}"

@app.route('/admin/logout')
def admin_logout():
    log_activity("LOGOUT", "Admin logged out")
    session.clear()
    return redirect(url_for('admin_login_page'))

if __name__ == "__main__":
    app.run(debug=True, port=5001)
import os
import json
import sqlite3
import pandas as pd
from flask import Flask, render_template, request, flash, redirect, url_for, flash, session, send_file
import io
# Custom parser imports
import parser
import parser_nep
import parser_sy
import re

# Flask application initialization
app = Flask(__name__)
app.secret_key = "supersecretkey"

# Configuration for file uploads
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ---------------------------------------------------
# GLOBAL DATA STORE
# ---------------------------------------------------

# Stores the state of processed PDF data and analysis statistics
PDF_DATA_STORE = {
    'all_students': [],
    'college_info': {},
    'display_students': [],
    'course_display': '',
    'year_display': '',
    'stats': {},
    'pattern': ''
}

# Maps internal course codes to display names
COURSE_MAP = {
    'bcs': 'B.Sc. (Computer Science)',
    'bca': 'B.C.A. (Science)',
    'other': 'Other Course'
}

# Maps internal year codes to display names
YEAR_MAP = {
    'fy': 'First Year (F.Y.)',
    'sy': 'Second Year (S.Y.)',
    'ty': 'Third Year (T.Y.)'
}

# ---------------------------------------------------
# DATABASE SETUP & UTILITIES
# ---------------------------------------------------

def init_subject_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # १. टेबल तयार करताना 'academic_year' कॉलम समाविष्ट करा
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_code TEXT,
            subject_name TEXT,
            course TEXT,
            semester INTEGER,
            academic_year TEXT,
            UNIQUE(subject_code, course)
        )
    """)

    # २. विद्यमान कॉलम्स तपासणे
    cursor.execute("PRAGMA table_info(subjects)")
    existing_columns = [col[1] for col in cursor.fetchall()]

    # ३. आवश्यक कॉलम्सची यादी (academic_year सह)
    required_columns = {
        "subject_code": "TEXT",
        "subject_name": "TEXT",
        "course": "TEXT",
        "semester": "INTEGER",
        "academic_year": "TEXT" 
    }

    # ४. जर कॉलम नसेल तर तो ॲड करा
    for column, col_type in required_columns.items():
        if column not in existing_columns:
            cursor.execute(f"ALTER TABLE subjects ADD COLUMN {column} {col_type}")

    conn.commit()
    conn.close()


def init_db():
    """
    Initializes the SQLite database with required tables and pre-defined subject data.
    """
    try:
        conn = sqlite3.connect('college_results.db')
        cursor = conn.cursor()

        # Creates table for student records
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prn TEXT,
                seat_no TEXT,
                full_name TEXT,
                mother_name TEXT,
                gender TEXT,
                course TEXT,
                year TEXT,
                college_name TEXT,
                pun_code TEXT,
                result TEXT,
                dashboard_sgpa TEXT,
                pattern TEXT,
                all_data_json TEXT,
                UNIQUE(prn, year)
            )
        ''')

        # Creates table for subject mapping
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subjects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject_code TEXT UNIQUE,
                subject_name TEXT,
                academic_year TEXT,
                course TEXT,
                semester INTEGER,
                UNIQUE(subject_code, course)
            )
        ''')
        required_schema = {
            "students": {
                "college_name": "TEXT",
                "pun_code": "TEXT"
            },
            "subjects": {
                "course": "TEXT"
            }
        }

        for table, columns in required_schema.items():
            # Get existing column names for the table
            cursor.execute(f"PRAGMA table_info({table})")
            existing_cols = [row[1] for row in cursor.fetchall()]

            for col_name, col_type in columns.items():
                if col_name not in existing_cols:
                    print(f"Adding missing column '{col_name}' to table '{table}'...")
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")

        conn.commit()
        print("Database initialized and schema verified successfully.")
    except Exception as e:
        print(f"Database Initialization Error: {str(e)}")
    finally:
        if conn:
            conn.close()

# Execute database initialization
init_db()

def get_db_connection():
    """
    Establishes and returns a connection to the SQLite database.
    """
    try:
        conn = sqlite3.connect('college_results.db')
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"Error connecting to database: {str(e)}")
        return None

# ---------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------

def calculate_stats(student_list):
    """
    Calculates summary statistics (Pass/Fail/ATKT) based on gender and results.
    """
    stats = {
        'total': len(student_list),
        'male_pass': 0, 'male_atkt': 0, 'male_fail': 0,
        'female_pass': 0, 'female_atkt': 0, 'female_fail': 0,
        'pass': 0, 'atkt': 0, 'fail': 0
    }
    for std in student_list:
        res = std.get('result', 'FAIL').upper()
        gender = std.get('gender', 'Male')
        status = 'fail'
        
        if "PASS" in res:
            status = 'pass'
            stats['pass'] += 1
        elif "A.T.K.T" in res or "ATKT" in res:
            status = 'atkt'
            stats['atkt'] += 1
            std['dashboard_sgpa'] = "-"
        else:
            stats['fail'] += 1
            std['dashboard_sgpa'] = "-"
        
        key = f"{gender.lower()}_{status}"
        if key in stats:
            stats[key] += 1
    return stats

def safe_float(val):
    """
    Safely converts a string value to a float, handling non-numeric markers.
    """
    try:
        if val is None or str(val).strip() in ['-', '', 'AB']:
            return 0.0
        cleaned = "".join(c for c in str(val) if c.isdigit() or c == '.')
        return float(cleaned) if cleaned else 0.0
    except Exception:
        return 0.0

def calculate_precise_percentage(cgpa):
    """
    Calculates the percentage based on the official University range-based equations.
    """
    val = safe_float(cgpa)
    if val >= 9.50: return (20 * val) - 100
    elif 8.25 <= val <= 9.49: return (12 * val) - 25
    elif 6.75 <= val <= 8.24: return (10 * val) - 7.5
    elif 5.75 <= val <= 6.74: return (5 * val) + 26.25
    elif 5.25 <= val <= 5.74: return (10 * val) - 2.5
    elif 4.75 <= val <= 5.24: return (10 * val) - 2.5
    elif 4.00 <= val <= 4.74: return (6.6 * val) + 13.6
    return 0.0

def get_unique_subjects():
    """
    Extracts a unique list of subject codes from the current global student data store.
    """
    all_students = PDF_DATA_STORE.get('all_students', [])
    subjects = set()
    for std in all_students:
        for key in ['subjects', 'sem1_subjects', 'sem2_subjects', 'sem3_subjects', 'sem4_subjects']:
            if key in std:
                for sub in std[key]:
                    subjects.add(sub['code'])
    return sorted(list(subjects))

# ---------------------------------------------------
# CORE ROUTES
# ---------------------------------------------------

@app.route('/')
def home():
    """
    Renders the landing page with dynamic dropdown options fetched from the database.
    """
    try:
        conn = sqlite3.connect('college_results.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Dynamically fetch unique Course and Year combinations that exist in the DB
        query = "SELECT DISTINCT course, year FROM students"
        saved_records = cursor.execute(query).fetchall()
        conn.close()
        # Convert row objects to list of dicts for JS processing
        saved_options = [{"course": r["course"], "year": r["year"]} for r in saved_records]
    except Exception as e:
        print(f"Error fetching history options: {e}")
        saved_options = []

    # Passes saved_options to the template for the dynamic dropdown
    return render_template('index.html', saved_options=saved_options)

@app.context_processor
def inject_college_name():
    """
    Makes the college name available to all templates dynamically.
    It checks the global store first, then falls back to the database.
    """
    # Default name if nothing is found
    display_name = "COLLEGE ANALYSIS SYSTEM"
    
    # Check if a PDF has been processed in the current session
    store_college = PDF_DATA_STORE.get('college_info', {}).get('college_name')
    
    if store_college and store_college != 'Unknown':
        display_name = store_college
    else:
        # Fallback: Fetch the most recent college name from the database
        try:
            conn = sqlite3.connect('college_results.db')
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            # Get the college name from the last student entry
            row = cursor.execute('SELECT college_name FROM students WHERE college_name IS NOT NULL AND college_name != "Unknown" ORDER BY id DESC LIMIT 1').fetchone()
            conn.close()
            if row:
                display_name = row['college_name']
        except Exception as e:
            print(f"Error fetching college name for navbar: {e}")

    return dict(dynamic_college_name=display_name)

@app.route('/save_to_db', methods=['POST'])
def save_to_db():
    all_students = PDF_DATA_STORE.get('all_students', [])
    course = PDF_DATA_STORE.get('course_display', '')
    year = PDF_DATA_STORE.get('year_display', '')
    pattern = PDF_DATA_STORE.get('pattern', '')
    # Ensure metadata is a dictionary to prevent 'list' attribute error
    metadata = PDF_DATA_STORE.get('college_info', {}) 
    
    if not all_students:
        return redirect(url_for('dashboard'))
        
    try:
        conn = sqlite3.connect('college_results.db')
        cursor = conn.cursor()
        for std in all_students:
            student_json = json.dumps(std)
            
            # Match the order: prn, seat_no, full_name, mother_name, gender, 
            # course, year, college_name, pun_code, result, dashboard_sgpa, pattern, all_data_json
            cursor.execute('''
                INSERT OR REPLACE INTO students 
                (prn, seat_no, full_name, mother_name, gender, course, year, 
                 college_name, pun_code, result, dashboard_sgpa, pattern, all_data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                std.get('prn'), 
                std.get('seat_no'), 
                std.get('full_name'), 
                std.get('mother_name'),
                std.get('gender', 'Male'),
                metadata.get('course_name', course), # Course from header
                year,
                metadata.get('college_name', '-'),  # College from header
                metadata.get('pun_code', '-'),      # PUN from header
                std.get('result'), 
                std.get('dashboard_sgpa', '-'), 
                pattern, 
                student_json
            ))
        conn.commit()
        conn.close()
        flash(f"Successfully saved {len(all_students)} students!", "success")
    except Exception as e:
        flash(f"Database Error: {str(e)}", "danger")
    return redirect(url_for('dashboard'))


@app.route('/analyze', methods=['POST'])
def analyze():
    """
    Handles PDF upload and triggers parsing logic based on class year.
    Now supports dynamic metadata extraction (College Name, Course, Puncode) from headers.
    """
    if 'ledger_pdf' not in request.files:
        flash('System Error: File part not detected.', 'danger')
        return redirect(url_for('home'))
        
    file = request.files['ledger_pdf']
    if file.filename == '':
        flash('Action Required: Please select a PDF file before analysis.', 'warning')
        return redirect(url_for('home'))

    if not file.filename.lower().endswith('.pdf'):
        flash('Invalid Format: Only University Result Ledger PDFs are supported.', 'danger')
        return redirect(url_for('home'))

    try:
        class_year = request.form.get('class_year')
        # raw_course = request.form.get('course_name')
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)

        # Triggers parser based on academic year
        if class_year == 'fy':
            result = parser_nep.main(file_path)
            PDF_DATA_STORE['pattern'] = 'NEP'
        elif class_year == 'sy':
            result = parser_sy.main(file_path) 
            PDF_DATA_STORE['pattern'] = 'SY_4SEM'
        else:
            result = parser.main(file_path)
            PDF_DATA_STORE['pattern'] = '2019'

        if result['success']:
            extracted_data = result.get('data', result.get('student_data'))
            metadata = result.get('college_info', {})
            
            if not extracted_data or len(extracted_data) == 0:
                flash("❌ Analysis Blocked: The uploaded PDF is not a valid Result Ledger.", "danger")
                return redirect(url_for('home'))

            for s in extracted_data:
                res_upper = s.get('result', '').upper()
                if "PASS" not in res_upper:
                    s['dashboard_sgpa'] = "-"
                else:
                    if class_year == 'ty':
                        s['dashboard_sgpa'] = s.get('cgpa', '-')
                    if 'dashboard_sgpa' not in s:
                        s['dashboard_sgpa'] = s.get('cgpa', '-')

            PDF_DATA_STORE.update({
                # 'course_display': metadata.get('course_name', raw_course),
                'course_display': metadata.get('course_name', 'Unknown Course'),
                'college_info': metadata,
                'year_display': YEAR_MAP.get(class_year, class_year),
                'all_students': extracted_data,
                'display_students': extracted_data,
                'stats': calculate_stats(extracted_data)
            })
            
            flash(f"✅ Success: Processed {len(extracted_data)} students.", "success")
            return redirect(url_for('dashboard'))
        else:
            flash(f"Parser Rejected: {result.get('error')}", "danger")
            return redirect(url_for('home'))

    except Exception as e:
        flash(f"Internal Crash during Analysis: {str(e)}", "danger")
        return redirect(url_for('home'))
    finally:
        # Auto-delete logic: Cleanup the file from the upload folder
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"Cleanup Successful: Deleted {file_path}")
            except Exception as cleanup_error:
                print(f"Warning: Could not delete temporary file: {cleanup_error}")



@app.route('/dashboard')
def dashboard():
    """
    Displays the main dashboard with statistics and student list.
    """
    if not PDF_DATA_STORE['all_students']:
        flash("System Note: Please upload a PDF to begin analysis.", "warning")
        return redirect(url_for('home'))

    course_display = PDF_DATA_STORE['course_display']
    year_display = PDF_DATA_STORE['year_display']
    
    is_already_saved = False
    try:
        conn = get_db_connection()
        cursor = conn.execute(
            'SELECT COUNT(*) FROM students WHERE course = ? AND year = ?', 
            (course_display, year_display)
        )
        count = cursor.fetchone()[0]
        if count > 0:
            is_already_saved = True
        conn.close()
    except Exception as e:
        print(f"Check Save Error: {e}")

    year_display_text = PDF_DATA_STORE['year_display']
    is_fy = True if ("First Year" in year_display_text or "Second Year" in year_display_text) else False
    
    if session.get('show_gender_forcefully'):
        is_fy = False
        session.pop('show_gender_forcefully', None)
        
    return render_template('dashboard.html', 
                           student_data=PDF_DATA_STORE['display_students'],
                           course=course_display,
                           year=year_display,
                           stats=PDF_DATA_STORE['stats'],
                           is_fy=is_fy,
                           is_already_saved=is_already_saved)

@app.route('/generate_class_report')
# 1st and 2nd year
# def generate_class_report():
#     try:
#         conn = get_db_connection()

#         # ---------- SUBJECT MASTER ----------
#         db_subjects = conn.execute(
#             "SELECT subject_code, subject_name FROM subjects"
#         ).fetchall()
#         subject_map = {str(r['subject_code']): r['subject_name'] for r in db_subjects}

#         # ---------- ACTIVE META ----------
#         active_dept = PDF_DATA_STORE.get('course')
#         active_year = PDF_DATA_STORE.get('year_display')

#         if not active_dept or not active_year:
#             print("[WARN] PDF_DATA_STORE missing, fetching from DB...")

#             row = conn.execute(
#                 "SELECT course, year FROM students ORDER BY id DESC LIMIT 1"
#             ).fetchone()

#             if row:
#                 active_dept = active_dept or row['course']
#                 active_year = active_year or row['year']

#                 print("[DEBUG] Fallback DB course:", active_dept)
#                 print("[DEBUG] Fallback DB year  :", active_year)

#         # ❌ तरीही नसेल तर UI error
#         if not active_dept or not active_year:
#             print("[ERROR] Course/Year still missing after fallback")
#             flash("⚠️ Course किंवा Year select केलेले नाही. कृपया पुन्हा select करा.", "danger")
#             return redirect(url_for('dashboard'))
        
#         # ---------- DATA FETCH ----------
#         db_data = conn.execute(
#             "SELECT * FROM students WHERE course = ? AND year = ?",
#             (active_dept, active_year)
#         ).fetchall()

#         source_data = []

#         if db_data:
#             print(f"[DEBUG] DB students found: {len(db_data)}")

#             for row in db_data:
#                 d = dict(row)

#                 # 👉 Year नुसार semester keys ठरव
#                 if "First" in active_year:
#                     sem_keys = ['sgpa', 'sem1_subjects', 'sem2_subjects', 'subjects']
#                 elif "Second" in active_year:
#                     sem_keys = ['sgpa', 'sem3_subjects', 'sem4_subjects', 'subjects']
#                 elif "Third" in active_year:
#                     sem_keys = ['sgpa', 'sem5_subjects', 'sem6_subjects', 'subjects']
#                 else:
#                     sem_keys = ['sgpa', 'subjects']

#                 # 👉 JSON unpack
#                 for key in sem_keys:
#                     if isinstance(d.get(key), str):
#                         import json
#                         try:
#                             d[key] = json.loads(d[key])
#                         except Exception as e:
#                             print(f"[WARN] JSON parse failed for {key}: {e}")
#                             d[key] = []

#                 source_data.append(d)

#             print(f"[DEBUG] Source data prepared: {len(source_data)}")

#         else:
#             source_data = (
#                 PDF_DATA_STORE.get('display_students')
#                 or PDF_DATA_STORE.get('all_students')
#                 or []
#             )
#             print(f"[DEBUG] Using PDF store data: {len(source_data)}")


#         conn.close()

#         # ---------- SEM CONFIG ----------
#         is_sy = "Second" in active_year or "S.Y." in active_year
#         if "Third" in active_year:
#             sem_a, sem_b, pre_a, pre_b = 5, 6, "35", "36"
#         elif is_sy:
#             sem_a, sem_b, pre_a, pre_b = 3, 4, "23", "24"
#         else:
#             sem_a, sem_b, pre_a, pre_b = 1, 2, "10", "15"

#         # ---------- HELPERS ----------
#         def init_stats():
#             return {
#                 'enrolled': {'boys': 0, 'girls': 0, 'total': 0},
#                 'appeared': {'boys': 0, 'girls': 0, 'total': 0},
#                 'pass': {'boys': 0, 'girls': 0, 'total': 0},
#                 # ✅ NEW : 60% AND ABOVE
#                 'perc_60': {'boys': 0, 'girls': 0, 'total': 0},
#             }

#         def calculate_fy_sgpa(subjects):
#             grade_map = {'O':10,'A+':9,'A':8,'B+':7,'B':6,'C':5,'P':4}
#             total = count = 0
#             for sub in subjects:
#                 grd = str(sub.get('grd', sub.get('grade',''))).upper()
#                 if grd in grade_map:
#                     total += grade_map[grd]
#                     count += 1
#             return round(total/count, 2) if count else 0

#         # ---------- INIT ----------
#         stats_a, stats_b = init_stats(), init_stats()
#         subs_a, subs_b = {}, {}
#         tops_a, tops_b = [], []

#         annual_stats = {
#             'pass':0,'atkt':0,'fail':0,
#             'male_pass':0,'male_atkt':0,'male_fail':0,
#             'female_pass':0,'female_atkt':0,'female_fail':0,
#             'dist':0,'first':0,'higher_sec':0,'second':0,'pass_class':0
#         }

#         all_ann, male_ann, fem_ann = [], [], []

#         # ================= MAIN LOOP =================
#         for std in source_data:
#             gender = str(std.get('gender','')).lower()
#             g_key = 'boys' if gender in ['male','m','b'] else 'girls'

#             # ---------- ANNUAL ----------
#             res = str(std.get('result','')).upper()
#             cgpa = safe_float(std.get('dashboard_sgpa') or std.get('cgpa') or 0)

#             status = 'fail'
#             if "PASS" in res:
#                 status = 'pass'
#             elif any(x in res for x in ['ATKT','A.T.K.T','PROMOTED']):
#                 status = 'atkt'

#             annual_stats[status] += 1
#             annual_stats[f"{'male' if g_key=='boys' else 'female'}_{status}"] += 1

#             if status == 'pass':
#                 if cgpa >= 7.75: annual_stats['dist'] += 1
#                 elif cgpa >= 6.75: annual_stats['first'] += 1
#                 elif cgpa >= 6.25: annual_stats['higher_sec'] += 1
#                 elif cgpa >= 5.75: annual_stats['second'] += 1
#                 else: annual_stats['pass_class'] += 1

#             ann_obj = {
#                 'full_name': std.get('full_name'),
#                 'cgpa': cgpa,
#                 'perc': round(calculate_precise_percentage(cgpa), 2)
#             }
#             all_ann.append(ann_obj)
#             (male_ann if g_key=='boys' else fem_ann).append(ann_obj)

#             # ---------- SEM LOOP ----------
#             for s_num, s_obj, t_list, s_map, prefix in [
#                 (sem_a, stats_a, tops_a, subs_a, pre_a),
#                 (sem_b, stats_b, tops_b, subs_b, pre_b)
#             ]:
#                 # ---------- ENROLLED ----------
#                 s_obj['enrolled'][g_key] += 1

#                 # ---------- APPEARED ----------
#                 if res not in ['ABSENT', 'AB', 'A.B.']:
#                     s_obj['appeared'][g_key] += 1

#                 # ---------- SGPA EXTRACTION ----------
#                 sgpa_val = safe_float(
#                     std.get(f'sem{s_num}_sgpa', 0) or
#                     std.get('sgpa', {}).get(str(s_num), 0)
#                 )

#                 sem_subs = std.get(f'sem{s_num}_subjects', [])

#                 # FY fallback
#                 if sgpa_val == 0 and "First" in active_year:
#                     sgpa_val = calculate_fy_sgpa(sem_subs)

#                 # SY regex fallback
#                 if sgpa_val == 0 and is_sy:
#                     summary = str(std.get(f'sem{s_num}_summary', ''))
#                     match = re.search(r"SGPA\s*:\s*([\d\.]+)", summary)
#                     if match:
#                         sgpa_val = safe_float(match.group(1))

#                 # ---------- FAIL CHECK ----------
#                 failed = any(
#                     str(sub.get('grd', sub.get('grade', ''))).upper()
#                     in ['F', 'FAIL', 'FFF', 'AB']
#                     for sub in sem_subs
#                 )

#                 # ---------- PASS + 60% ----------
#                 if sgpa_val > 0 and not failed:
#                     s_obj['pass'][g_key] += 1

#                     perc_val = calculate_precise_percentage(sgpa_val)
#                     if perc_val >= 60:
#                         s_obj['perc_60'][g_key] += 1

#                     t_list.append({
#                         'full_name': std.get('full_name'),
#                         'sgpa': sgpa_val,
#                         'perc': round(perc_val, 2)
#                     })

#                 # ---------- SUBJECT STATS (YEAR AWARE) ----------
#                 for sub in sem_subs + std.get('subjects', []):
#                     code = str(sub.get('code', ''))

#                     if "First" in active_year:
#                         valid = prefix in code
#                     elif "Second" in active_year:
#                         valid = (prefix in code) or ("AECC" in code.upper())
#                     else:  # TY
#                         valid = code.startswith(prefix)

#                     if not valid:
#                         continue

#                     if code not in s_map:
#                         s_map[code] = {
#                             'name': subject_map.get(code, sub.get('name', 'Unknown')),
#                             'app': 0,
#                             'pass': 0
#                         }

#                     s_map[code]['app'] += 1
#                     grd = str(sub.get('grd', sub.get('grade', ''))).upper()
#                     if grd not in ['F', 'FAIL', 'FFF', 'AB']:
#                         s_map[code]['pass'] += 1


#         # ---------- FINAL TOTALS ----------
#         for s in (stats_a, stats_b):
#             for k in ['enrolled','appeared','pass','perc_60']:
#                 s[k]['total'] = s[k]['boys'] + s[k]['girls']

#         # ---------- CONSOLE ----------
#         for s_num, s in [(sem_a, stats_a), (sem_b, stats_b)]:
#             print(f"[SEM {s_num}] 60%+ : {s['perc_60']['total']} "
#                   f"(B:{s['perc_60']['boys']} G:{s['perc_60']['girls']})")

#         return render_template(
#             'class_report.html',
#             year=active_year,
#             sem_a=sem_a,
#             sem_b=sem_b,
#             stats_a=stats_a,
#             stats_b=stats_b,
#             subs_a=subs_a,
#             subs_b=subs_b,
#             tops_a=sorted(tops_a, key=lambda x:x['sgpa'], reverse=True)[:3],
#             tops_b=sorted(tops_b, key=lambda x:x['sgpa'], reverse=True)[:3],
#             annual=annual_stats,
#             top_year=sorted(all_ann, key=lambda x:x['cgpa'], reverse=True)[:3],
#             top_male=sorted(male_ann, key=lambda x:x['cgpa'], reverse=True)[:3],
#             top_female=sorted(fem_ann, key=lambda x:x['cgpa'], reverse=True)[:3]
#         )

#     except Exception as e:
#         print("[ERROR]", e)
#         return f"Error: {e}"

def generate_class_report():
    try:
        conn = get_db_connection()

        # ---------- SUBJECT MASTER ----------
        db_subjects = conn.execute(
            "SELECT subject_code, subject_name FROM subjects"
        ).fetchall()
        subject_map = {str(r['subject_code']): r['subject_name'] for r in db_subjects}

        # ---------- ACTIVE META ----------
        active_dept = PDF_DATA_STORE.get('course')
        active_year = PDF_DATA_STORE.get('year_display')

        if not active_dept or not active_year:
            print("[WARN] PDF_DATA_STORE missing, fetching from DB...")
            row = conn.execute(
                "SELECT course, year FROM students ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if row:
                active_dept = active_dept or row['course']
                active_year = active_year or row['year']

        if not active_dept or not active_year:
            print("[ERROR] Course/Year still missing")
            flash("⚠️ Course किंवा Year select केलेले नाही.", "danger")
            return redirect(url_for('dashboard'))
        
        # ---------- DATA FETCH ----------
        db_data = conn.execute(
            "SELECT * FROM students WHERE course = ? AND year = ?",
            (active_dept, active_year)
        ).fetchall()

        source_data = []

        if db_data:
            print(f"[DEBUG] DB students found: {len(db_data)}")

            for row in db_data:
                d = dict(row)

                # ✅ FIX 1: T.Y. cha data 'all_data_json' madhe asto, to unpack karne
                if 'all_data_json' in d and d['all_data_json']:
                    try:
                        extra_data = json.loads(d['all_data_json'])
                        # JSON madhala data main dict madhe merge kar
                        d.update(extra_data)
                    except Exception as e:
                        print(f"[WARN] Failed to unpack all_data_json for {d.get('full_name')}: {e}")

                # 👉 JSON unpack for specific columns (jar columns astil tr)
                sem_keys = []
                if "First" in active_year:
                    sem_keys = ['sgpa', 'sem1_subjects', 'sem2_subjects', 'subjects']
                elif "Second" in active_year:
                    sem_keys = ['sgpa', 'sem3_subjects', 'sem4_subjects', 'subjects']
                elif "Third" in active_year:
                    sem_keys = ['sgpa', 'sem5_subjects', 'sem6_subjects', 'subjects']

                for key in sem_keys:
                    # Jar data string format madhe asel trch parse kar
                    if key in d and isinstance(d[key], str):
                        try:
                            d[key] = json.loads(d[key])
                        except:
                            d[key] = []

                source_data.append(d)
        else:
            source_data = (
                PDF_DATA_STORE.get('display_students')
                or PDF_DATA_STORE.get('all_students')
                or []
            )
            print(f"[DEBUG] Using PDF store data: {len(source_data)}")

        conn.close()

        # ---------- SEM CONFIG ----------
        is_sy = "Second" in active_year or "S.Y." in active_year
        if "Third" in active_year:
            sem_a, sem_b, pre_a, pre_b = 5, 6, "35", "36"
        elif is_sy:
            sem_a, sem_b, pre_a, pre_b = 3, 4, "23", "24"
        else:
            sem_a, sem_b, pre_a, pre_b = 1, 2, "10", "15"

        # ---------- HELPERS ----------
        def init_stats():
            return {
                'enrolled': {'boys': 0, 'girls': 0, 'total': 0},
                'appeared': {'boys': 0, 'girls': 0, 'total': 0},
                'pass': {'boys': 0, 'girls': 0, 'total': 0},
                'perc_60': {'boys': 0, 'girls': 0, 'total': 0},
            }

        def calculate_fy_sgpa(subjects):
            grade_map = {'O':10,'A+':9,'A':8,'B+':7,'B':6,'C':5,'P':4}
            total = count = 0
            for sub in subjects:
                grd = str(sub.get('grd', sub.get('grade',''))).upper()
                if grd in grade_map:
                    total += grade_map[grd]
                    count += 1
            return round(total/count, 2) if count else 0

        # ---------- INIT ----------
        stats_a, stats_b = init_stats(), init_stats()
        subs_a, subs_b = {}, {}
        tops_a, tops_b = [], []

        annual_stats = {
            'pass':0,'atkt':0,'fail':0,
            'male_pass':0,'male_atkt':0,'male_fail':0,
            'female_pass':0,'female_atkt':0,'female_fail':0,
            'dist':0,'first':0,'higher_sec':0,'second':0,'pass_class':0
        }

        all_ann, male_ann, fem_ann = [], [], []

        # ================= MAIN LOOP =================
        for idx, std in enumerate(source_data):
            gender = str(std.get('gender','')).lower()
            g_key = 'boys' if gender in ['male','m','b'] else 'girls'

            res = str(std.get('result','')).upper()
            cgpa = safe_float(std.get('dashboard_sgpa') or std.get('cgpa') or 0)

            # [DEBUG SAMPLE] Print first student SGPA logic to debug T.Y.
            if idx == 0 and "Third" in active_year:
                print(f"[DEBUG TY Sample] Name: {std.get('full_name')}")
                print(f" - SGPA Obj: {std.get('sgpa')}")
                print(f" - Sem5 Raw: {std.get('sem5_sgpa')}")

            status = 'fail'
            if "PASS" in res: status = 'pass'
            elif any(x in res for x in ['ATKT','A.T.K.T','PROMOTED']): status = 'atkt'

            annual_stats[status] += 1
            annual_stats[f"{'male' if g_key=='boys' else 'female'}_{status}"] += 1

            if status == 'pass':
                if cgpa >= 7.75: annual_stats['dist'] += 1
                elif cgpa >= 6.75: annual_stats['first'] += 1
                elif cgpa >= 6.25: annual_stats['higher_sec'] += 1
                elif cgpa >= 5.75: annual_stats['second'] += 1
                else: annual_stats['pass_class'] += 1

            ann_obj = {'full_name': std.get('full_name'), 'cgpa': cgpa, 'perc': round(calculate_precise_percentage(cgpa), 2)}
            all_ann.append(ann_obj)
            (male_ann if g_key=='boys' else fem_ann).append(ann_obj)

            # ---------- SEM LOOP ----------
            for s_num, s_obj, t_list, s_map, prefix in [
                (sem_a, stats_a, tops_a, subs_a, pre_a),
                (sem_b, stats_b, tops_b, subs_b, pre_b)
            ]:
                s_obj['enrolled'][g_key] += 1
                if res not in ['ABSENT', 'AB', 'A.B.']:
                    s_obj['appeared'][g_key] += 1

                # SGPA Logic
                sgpa_val = safe_float(std.get(f'sem{s_num}_sgpa', 0))
                
                # Jar direct key nasel tr 'sgpa' dictionary check kar
                if sgpa_val == 0:
                    sgpa_dict = std.get('sgpa', {})
                    # Kahi veles sgpa dict string asu shakate
                    if isinstance(sgpa_dict, str):
                        try: sgpa_dict = json.loads(sgpa_dict)
                        except: sgpa_dict = {}
                    sgpa_val = safe_float(sgpa_dict.get(str(s_num), 0))

                sem_subs = std.get(f'sem{s_num}_subjects', [])

                # F.Y. Fallback
                if sgpa_val == 0 and "First" in active_year:
                    sgpa_val = calculate_fy_sgpa(sem_subs)

                # S.Y. & T.Y. Regex Fallback (Summary string madhun shodha)
                if sgpa_val == 0:
                    summary = str(std.get(f'sem{s_num}_summary', ''))
                    match = re.search(r"SGPA\s*:\s*([\d\.]+)", summary)
                    if match:
                        sgpa_val = safe_float(match.group(1))

                # Failed Check
                failed = any(str(sub.get('grd', sub.get('grade', ''))).upper() in ['F', 'FAIL', 'FFF', 'AB'] for sub in sem_subs)

                if sgpa_val > 0 and not failed:
                    s_obj['pass'][g_key] += 1
                    perc_val = calculate_precise_percentage(sgpa_val)
                    if perc_val >= 60:
                        s_obj['perc_60'][g_key] += 1
                    t_list.append({'full_name': std.get('full_name'), 'sgpa': sgpa_val, 'perc': round(perc_val, 2)})

                # Subject Stats
                for sub in sem_subs + std.get('subjects', []):
                    code = str(sub.get('code', ''))
                    
                    # ✅ FIX 2: T.Y. Subject logic सुधारले (startswith -> in)
                    if "First" in active_year:
                        valid = prefix in code
                    elif "Second" in active_year:
                        valid = (prefix in code) or ("AECC" in code.upper())
                    else:  # Third Year
                        # CS-351 madhe '35' start la nahiye, pan 'in' aahe
                        valid = prefix in code 

                    if not valid: continue

                    if code not in s_map:
                        s_map[code] = {'name': subject_map.get(code, sub.get('name', 'Unknown')), 'app': 0, 'pass': 0}

                    s_map[code]['app'] += 1
                    if str(sub.get('grd', sub.get('grade', ''))).upper() not in ['F', 'FAIL', 'FFF', 'AB']:
                        s_map[code]['pass'] += 1

        # ---------- FINAL TOTALS ----------
        for s in (stats_a, stats_b):
            for k in ['enrolled','appeared','pass','perc_60']:
                s[k]['total'] = s[k]['boys'] + s[k]['girls']

        print(f"[DEBUG] Sem {sem_a} 60%+: {stats_a['perc_60']['total']}")
        print(f"[DEBUG] Sem {sem_b} 60%+: {stats_b['perc_60']['total']}")

        return render_template(
            'class_report.html',
            year=active_year,
            sem_a=sem_a, sem_b=sem_b,
            stats_a=stats_a, stats_b=stats_b,
            subs_a=subs_a, subs_b=subs_b,
            tops_a=sorted(tops_a, key=lambda x:x['sgpa'], reverse=True)[:3],
            tops_b=sorted(tops_b, key=lambda x:x['sgpa'], reverse=True)[:3],
            annual=annual_stats,
            top_year=sorted(all_ann, key=lambda x:x['cgpa'], reverse=True)[:3],
            top_male=sorted(male_ann, key=lambda x:x['cgpa'], reverse=True)[:3],
            top_female=sorted(fem_ann, key=lambda x:x['cgpa'], reverse=True)[:3]
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        print("[ERROR]", e)
        return f"Error: {e}"


# c-27-1-26 old code
# @app.route('/view_saved')
# def view_saved():
#     """
#     Retrieves and loads saved student records from the database into the global store.
#     """
#     try:
#         course_full = COURSE_MAP.get(request.args.get('course'))
#         year_full = YEAR_MAP.get(request.args.get('year'))
#         conn = sqlite3.connect('college_results.db')
#         conn.row_factory = sqlite3.Row
#         cursor = conn.cursor()
#         cursor.execute('SELECT * FROM students WHERE course = ? AND year = ?', (course_full, year_full))
#         rows = cursor.fetchall()
#         conn.close()
        
#         if not rows:
#             flash("Database Inquiry: No saved reports found for this selection.", "warning")
#             return redirect(url_for('home'))
            
#         saved_students = [json.loads(row['all_data_json']) for row in rows]
#         PDF_DATA_STORE.update({
#             'all_students': saved_students, 'display_students': saved_students,
#             'course_display': course_full, 'year_display': year_full,
#             'pattern': rows[0]['pattern'], 'stats': calculate_stats(saved_students)
#         })
#         return redirect(url_for('dashboard'))
#     except Exception as e:
#         flash(f"System Retrieval Error: {str(e)}", "danger")
#         return redirect(url_for('home'))

@app.route('/view_saved')
def view_saved():
    """
    Retrieves and loads saved student records using dynamic dropdown values.
    """
    try:
        # 1. Get separate parameters from the two dropdowns
        course_val = request.args.get('course')
        year_val = request.args.get('year')
        
        if not course_val or not year_val:
            flash("Selection Error: Please choose both Department and Year.", "warning")
            return redirect(url_for('home'))

        conn = sqlite3.connect('college_results.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM students WHERE course = ? AND year = ?', (course_val, year_val))
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            flash("Database Inquiry: No saved reports found for this selection.", "warning")
            return redirect(url_for('home'))
            
        # 4. Load the data into the global store
        saved_students = [json.loads(row['all_data_json']) for row in rows]
        PDF_DATA_STORE.update({
            'all_students': saved_students, 
            'display_students': saved_students,
            'course_display': course_val, 
            'year_display': year_val,
            'college_info': {
                'college_name': rows[0]['college_name'], # Updates the dynamic navbar
                'pun_code': rows[0]['pun_code']
            },
            'pattern': rows[0]['pattern'], 
            'stats': calculate_stats(saved_students)
        })
        
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        flash(f"System Retrieval Error: {str(e)}", "danger")
        return redirect(url_for('home'))


@app.route('/student_analysis')
def student_analysis():
    """
    Renders the analysis landing page.
    """
    return render_template('analysis.html')

@app.route('/reset_filter')
def reset_filter():
    """
    Resets display filters to show all parsed students.
    """
    PDF_DATA_STORE['display_students'] = PDF_DATA_STORE['all_students']
    PDF_DATA_STORE['stats'] = calculate_stats(PDF_DATA_STORE['all_students'])
    return redirect(url_for('dashboard'))

@app.route('/report/<string:seat_no>')
def view_report(seat_no):
    """
    Displays a detailed result report for a specific student.
    """
    all_students = PDF_DATA_STORE.get('all_students', [])
    student = next((s for s in all_students if str(s['seat_no']).strip() == str(seat_no).strip()), None)
    
    if not student:
        try:
            conn = get_db_connection()
            row = conn.execute('SELECT all_data_json, pattern FROM students WHERE seat_no = ?', (seat_no.strip(),)).fetchone()
            conn.close()
            
            if row:
                student = json.loads(row['all_data_json'])
                if not PDF_DATA_STORE.get('pattern'):
                    PDF_DATA_STORE['pattern'] = row['pattern']
        except Exception as e:
            print(f"Database Retrieval Error for Report: {e}")

    if student:
        try:
            conn = get_db_connection()
            cursor = conn.execute("SELECT subject_code, subject_name FROM subjects")
            subject_map = {str(row['subject_code']).strip().upper(): row['subject_name'] for row in cursor.fetchall()}
            conn.close()

            def map_names(sub_list):
                for sub in sub_list:
                    raw_code = str(sub.get('code', '')).replace('*', '').strip().upper()
                    if raw_code in subject_map:
                        sub['name'] = subject_map[raw_code]

            if 'subjects' in student: map_names(student['subjects'])
            for i in range(1, 5):
                sem_key = f'sem{i}_subjects'
                if sem_key in student: map_names(student[sem_key])

            pattern = PDF_DATA_STORE.get('pattern', '')
            if pattern == 'SY_4SEM': 
                return render_template('report_sy.html', student=student)
            else: 
                return render_template('report_card.html', student=student)
        except Exception as e:
            return f"Report Rendering Error: {str(e)}"

    return "System Fault: Records for the specified student could not be located."

@app.route('/subject_analysis', methods=['GET', 'POST'])
def subject_analysis():
    """
    Analyzes student performance for a specific subject, including external Excel filtering.
    """
    all_students = PDF_DATA_STORE.get('all_students', [])
    unique_subjects = get_unique_subjects()
    
    try:
        conn = get_db_connection()
        cursor = conn.execute("SELECT subject_code, subject_name FROM subjects")
        subject_map = {row['subject_code']: row['subject_name'] for row in cursor.fetchall()}
        conn.close()
    except Exception as e:
        subject_map = {}
        print(f"Subject Map Error: {e}")

    selected_subject, subject_data, top_3, filter_active = None, [], [], False
    selected_subject_name = "" 
    stats = {
        'total': 0, 'pass': 0, 'fail': 0, 'male': 0, 'female': 0, 
        'male_pass': 0, 'male_fail': 0, 'female_pass': 0, 'female_fail': 0, 
        'distinction': 0, 'first_class': 0, 'higher_second': 0, 'second_class': 0, 'pass_class': 0
    }

    if request.method == 'POST':
        try:
            selected_subject = request.form.get('subject_code')
            selected_subject_name = subject_map.get(selected_subject, "Unknown Subject")
            excel_file = request.files.get('student_excel')
            target_seats, gender_map = [], {}
            
            if excel_file and excel_file.filename != '':
                df = pd.read_excel(excel_file)
                df.columns = [str(c).strip().lower() for c in df.columns]
                clean_s = lambda x: str(x).split('.')[0].strip()
                target_seats = df['seat no'].apply(clean_s).tolist()
                filter_active = True
                g_col = next((c for c in df.columns if c in ['gender', 'sex']), None)
                if g_col:
                    gender_map = dict(zip(df['seat no'].apply(clean_s), df[g_col].astype(str).str.strip().str.lower()))

            active_filtered_students = []

            for std in all_students:
                s_no = str(std.get('seat_no', '')).split('.')[0].strip()
                if filter_active and s_no not in target_seats: continue
                active_filtered_students.append(std)

                all_subs = []
                for k in ['subjects', 'sem1_subjects', 'sem2_subjects', 'sem3_subjects', 'sem4_subjects']:
                    if k in std: all_subs += std[k]

                target_sub = next((s for s in all_subs if s['code'] == selected_subject), None)
                if target_sub:
                    grade = str(target_sub.get('grd', target_sub.get('grade', '-'))).upper()
                    status = "FAIL" if grade in ['F', 'FFF', 'FAIL', 'AB', '---'] else "PASS"
                    gender = "Male"
                    if s_no in gender_map: 
                        gender = "Female" if gender_map[s_no] in ['f', 'female'] else "Male"
                        std['gender'] = gender 
                    elif 'gender' in std: 
                        gender = std['gender']

                    grade_class = "fail"
                    if status == "PASS":
                        stats['pass'] += 1
                        if grade in ['O', 'A+']: grade_class = "distinction"; stats['distinction'] += 1
                        elif grade == 'A': grade_class = "first_class"; stats['first_class'] += 1
                        elif grade == 'B+': grade_class = "higher_second"; stats['higher_second'] += 1
                        elif grade == 'B': grade_class = "second_class"; stats['second_class'] += 1
                        else: grade_class = "pass_class"; stats['pass_class'] += 1
                    else:
                        stats['fail'] += 1

                    stats['total'] += 1
                    if gender == 'Male':
                        stats['male'] += 1
                        if status == "PASS": stats['male_pass'] += 1
                        else: stats['male_fail'] += 1
                    else:
                        stats['female'] += 1
                        if status == "PASS": stats['female_pass'] += 1
                        else: stats['female_fail'] += 1

                    subject_data.append({
                        'seat_no': s_no, 'name': std.get('full_name', 'Unknown'), 'gender': gender,
                        'internal': target_sub.get('int_m', target_sub.get('internal', '-')),
                        'external': target_sub.get('ext_m', target_sub.get('external', '-')),
                        'total': str(target_sub.get('total', '0')), 'grade': grade, 'status': status, 'grade_class': grade_class,
                        'marks_val': int(''.join(filter(str.isdigit, str(target_sub.get('total', '0')))) or 0)
                    })

            if filter_active:
                PDF_DATA_STORE['display_students'] = active_filtered_students
            else:
                PDF_DATA_STORE['display_students'] = all_students

            passed = [s for s in subject_data if s['status'] == "PASS"]
            passed.sort(key=lambda x: x['marks_val'], reverse=True)
            top_3 = passed[:3]

        except Exception as e:
            flash(f"Error during subject analysis: {str(e)}", "danger")

    pattern = PDF_DATA_STORE.get('pattern', '')
    is_nep = (pattern == 'NEP' or pattern == 'SY_4SEM')
    show_gender = (not is_nep) or filter_active

    return render_template('subject_analysis.html', unique_subjects=unique_subjects, 
                           selected_subject=selected_subject, 
                           selected_subject_name=selected_subject_name,
                           subject_map=subject_map,
                           subject_data=subject_data, 
                           stats=stats, top_3=top_3, filter_active=filter_active, 
                           is_nep=is_nep, show_gender=show_gender)

# @app.route('/filter_excel', methods=['POST'])
# def filter_excel():
#     """
#     Applies filters to the student list using an uploaded Excel file (matching seat numbers).
#     """
#     excel_file = request.files.get('student_excel')
#     if not excel_file or excel_file.filename == '': 
#         flash("Validation Warning: No Excel file provided for filtering.", "warning")
#         return redirect(url_for('student_analysis'))
        
#     file_path = os.path.join(app.config['UPLOAD_FOLDER'], excel_file.filename)
#     excel_file.save(file_path)
    
#     try:
#         df = pd.read_excel(file_path)
#         df.columns = [str(c).replace(' ', '').replace('_', '').strip().lower() for c in df.columns]
        
#         clean_s = lambda x: str(x).split('.')[0].strip()
#         seat_col = next((c for c in df.columns if 'seat' in c), None)

#         if not seat_col:
#             flash("File Structure Error: Could not find 'Seat No' column in the uploaded Excel.", "danger")
#             return redirect(url_for('student_analysis'))

#         target_seats = df[seat_col].apply(clean_s).tolist()
#         current_db_seats = [clean_s(s['seat_no']) for s in PDF_DATA_STORE.get('all_students', [])]
#         common_seats = set(target_seats).intersection(set(current_db_seats))

#         if not common_seats:
#             flash("❌ Filter Refused: No matching seat numbers found.", "danger")
#             return redirect(url_for('student_analysis'))

#         g_col = next((c for c in df.columns if c in ['gender', 'sex']), None)
#         if g_col:
#             gender_map = dict(zip(df[seat_col].apply(clean_s), df[g_col].astype(str).str.strip().str.lower()))
#             for std in PDF_DATA_STORE['all_students']:
#                 s_no = clean_s(std['seat_no'])
#                 if s_no in gender_map:
#                     std['gender'] = "Female" if gender_map[s_no] in ['f', 'female'] else "Male"
#             session['show_gender_forcefully'] = True
        
#         filtered = [s for s in PDF_DATA_STORE['all_students'] if clean_s(s['seat_no']) in target_seats]
#         PDF_DATA_STORE['display_students'] = filtered
#         PDF_DATA_STORE['stats'] = calculate_stats(filtered)
        
#         flash(f"✅ Filter Engaged: Displaying {len(filtered)} selected students.", "success")
#         return redirect(url_for('dashboard'))

#     except Exception as e: 
#         flash(f"Excel Filtering Error: {str(e)}", "danger")
#         return redirect(url_for('student_analysis'))

@app.route('/filter_excel', methods=['POST'])
def filter_excel():
    """
    Applies filters to the student list using an uploaded Excel file (matching seat numbers).
    """
    excel_file = request.files.get('student_excel')
    if not excel_file or excel_file.filename == '':
        flash("Validation Warning: No Excel file provided for filtering.", "warning")
        return redirect(url_for('student_analysis'))

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], excel_file.filename)
    excel_file.save(file_path)

    try:
        df = pd.read_excel(file_path)

        # 🔹 Clean column names
        df.columns = [str(c).replace(' ', '').replace('_', '').strip().lower() for c in df.columns]

        # 🔹 Seat normalizer (SAFE)
        def clean_s(val):
            if val is None:
                return None
            val = str(val).strip()
            if not val or val.lower() == 'nan':
                return None
            return val.split('.')[0].replace(' ', '').upper()

        # 🔹 Detect seat column
        seat_col = next((c for c in df.columns if 'seat' in c), None)
        if not seat_col:
            flash("File Structure Error: Could not find 'Seat No' column in the uploaded Excel.", "danger")
            return redirect(url_for('student_analysis'))

        # 🔹 Excel seats
        target_seats = set(
            clean_s(x) for x in df[seat_col].tolist() if clean_s(x)
        )

        # 🔹 PDF seats
        all_students = PDF_DATA_STORE.get('all_students', [])
        current_db_seats = set(
            clean_s(s.get('seat_no')) for s in all_students if clean_s(s.get('seat_no'))
        )

        # 🐞 DEBUG
        print("DEBUG → Excel seats count:", len(target_seats))
        print("DEBUG → PDF seats count:", len(current_db_seats))

        common_seats = target_seats.intersection(current_db_seats)
        print("DEBUG → Matched seats count:", len(common_seats))

        if not common_seats:
            print("DEBUG → Sample Excel seats:", list(target_seats)[:10])
            print("DEBUG → Sample PDF seats:", list(current_db_seats)[:10])
            flash("❌ Filter Refused: No matching seat numbers found.", "danger")
            return redirect(url_for('student_analysis'))

        # 🔹 Gender mapping (optional)
        g_col = next((c for c in df.columns if c in ['gender', 'sex']), None)
        gender_map = {}

        if g_col:
            gender_map = {
                clean_s(seat): str(gen).strip().lower()
                for seat, gen in zip(df[seat_col], df[g_col])
                if clean_s(seat)
            }

            for std in all_students:
                s_no = clean_s(std.get('seat_no'))
                if s_no in gender_map:
                    std['gender'] = "Female" if gender_map[s_no] in ['f', 'female'] else "Male"

            session['show_gender_forcefully'] = True

        # 🔹 Final filtering
        filtered = [
            s for s in all_students
            if clean_s(s.get('seat_no')) in target_seats
        ]

        # 🐞 DEBUG
        print("DEBUG → Final filtered students:", len(filtered))

        PDF_DATA_STORE['display_students'] = filtered
        PDF_DATA_STORE['stats'] = calculate_stats(filtered)

        flash(f"✅ Filter Engaged: Displaying {len(filtered)} selected students.", "success")
        return redirect(url_for('dashboard'))

    except Exception as e:
        print("❌ EXCEPTION:", e)
        flash(f"Excel Filtering Error: {str(e)}", "danger")
        return redirect(url_for('student_analysis'))
    finally:
        # Auto-delete logic: Cleanup the file from the upload folder
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"Cleanup Successful: Deleted {file_path}")
            except Exception as cleanup_error:
                print(f"Warning: Could not delete temporary file: {cleanup_error}")


@app.route('/download_subject_template', methods=['POST'])
def download_subject_template():
    dept = request.form.get('department')
    year = request.form.get('year')

    sem_map = {'fy': (1, 2), 'sy': (3, 4), 'ty': (5, 6), '4y': (7, 8)}
    sem_a, sem_b = sem_map.get(year, (1, 2))

    data = {
        'DEPARTMENT': [dept] * 50,
        'ACADEMIC_YEAR': [year.upper()] * 50,
        'SEMESTER': [sem_a] * 25 + [sem_b] * 25,
        'SUBJECT_CODE': [''] * 50,
        'SUBJECT_NAME': [''] * 50
    }

    df = pd.DataFrame(data)

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Template')

    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name=f'Subject_Template_{year}_{dept}.xlsx'
    )


# ३. नवीन: सब्जेक्ट एक्सेल अपलोड आणि व्हॅलिडेशन
@app.route('/upload_subjects', methods=['POST'])
def upload_subjects():

    init_subject_db()

    file = request.files.get('subject_excel')
    

    if not file or file.filename == '':
        
        flash("Action Required: Please select an Excel file.", "warning")
        return redirect(url_for('student_analysis'))

    try:        
        df = pd.read_excel(file, dtype=str)
        # 3️⃣ Normalize column names
        df.columns = [c.strip().upper() for c in df.columns]
        required_cols = ['DEPARTMENT', 'SEMESTER', 'SUBJECT_CODE', 'SUBJECT_NAME', 'ACADEMIC_YEAR']
        missing_cols = [c for c in required_cols if c not in df.columns]

        if missing_cols:
            flash(f"❌ Column Mismatch! Missing: {missing_cols}", "danger")
            return redirect(url_for('student_analysis'))

        # 4️⃣ Data cleaning
        df['SUBJECT_CODE'] = df['SUBJECT_CODE'].fillna('').str.strip()
        df['SUBJECT_NAME'] = df['SUBJECT_NAME'].fillna('').str.strip()

        df_clean = df[(df['SUBJECT_CODE'] != "") & (df['SUBJECT_NAME'] != "")]

        if df_clean.empty:
            flash("⚠️ Error: Uploaded Excel has 0 valid rows with Subject Code/Name.", "warning")
            return redirect(url_for('student_analysis'))

        # 5️⃣ DB Insert
        conn = get_db_connection()
        success_count = 0
        duplicate_count = 0
        for index, row in df_clean.iterrows():
            try:
                conn.execute("""
                    INSERT INTO subjects (subject_code, subject_name, course, semester, academic_year)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    row['SUBJECT_CODE'],
                    row['SUBJECT_NAME'],
                    row['DEPARTMENT'],
                    int(float(row['SEMESTER'])),
                    row['ACADEMIC_YEAR']
                ))
                success_count += 1
            except sqlite3.IntegrityError:
                duplicate_count += 1
                continue

        # 6️⃣ Commit
        conn.commit()
        conn.close()
        if success_count > 0:
            flash(f"✅ Success: {success_count} subjects saved to database!", "success")
        else:
            flash("ℹ️ Info: All subjects in the file already exist in the database.", "info")

    except Exception as e:
        print("🔥 ERROR during upload:", str(e))
        flash(f"❌ Upload Error: {str(e)}", "danger")

    print("🔁 Redirecting back to student_analysis")
    return redirect(url_for('student_analysis'))



@app.route('/generate_subject_report/<string:subject_code>')
def generate_subject_report(subject_code):
    try:
        def safe_int(val):
            if val is None or str(val).strip() in ['-', '', 'AB']: return 0
            cleaned = "".join(filter(str.isdigit, str(val)))
            return int(cleaned) if cleaned else 0

        conn = get_db_connection()
        subject_info = conn.execute("SELECT subject_name FROM subjects WHERE subject_code = ?", (subject_code,)).fetchone()
        subject_name = subject_info['subject_name'] if subject_info else "Unknown Subject"
        conn.close()

        source_data = PDF_DATA_STORE.get('display_students', []) or PDF_DATA_STORE.get('all_students', [])

        stats = {
            'male_app': 0, 'male_pass': 0, 'male_fail': 0, 'male_atkt': 0, 'male_perc': 0,
            'female_app': 0, 'female_pass': 0, 'female_fail': 0, 'female_atkt': 0, 'female_perc': 0,
            'overall_app': 0, 'overall_pass': 0, 'overall_fail': 0, 'overall_perc': 0
        }
        
        overall_candidates, male_candidates, female_candidates = [], [], []
        grades = {'dist': 0, 'first': 0, 'h_second': 0, 'second': 0, 'p_class': 0}

        for student_data in source_data:
            gender = str(student_data.get('gender', 'Male')).strip().title() # ✨ Gender शोधण्याचे लॉजिक सुधारले
            all_subs = []
            for k in ['subjects', 'sem1_subjects', 'sem2_subjects', 'sem3_subjects', 'sem4_subjects', 'sem5_subjects', 'sem6_subjects']:
                if k in student_data: all_subs += student_data[k]

            target_sub = next((s for s in all_subs if str(s.get('code')) == subject_code), None)
            
            if target_sub:
                grade = str(target_sub.get('grd', target_sub.get('grade', 'F'))).upper()
                # ✨ Fail कॅटेगरी सुधारली
                is_fail = grade in ['F', 'FFF', 'FAIL', 'AB', '---', 'FX']
                res_string = str(student_data.get('result', '')).upper()
                is_at_risk = "A.T.K.T" in res_string or "ATKT" in res_string

                stats['overall_app'] += 1
                if gender == 'Female': stats['female_app'] += 1
                else: stats['male_app'] += 1

                if is_fail:
                    stats['overall_fail'] += 1
                    if is_at_risk:
                        if gender == 'Female': stats['female_atkt'] += 1
                        else: stats['male_atkt'] += 1
                    else:
                        if gender == 'Female': stats['female_fail'] += 1
                        else: stats['male_fail'] += 1
                else:
                    stats['overall_pass'] += 1
                    if gender == 'Female': stats['female_pass'] += 1
                    else: stats['male_pass'] += 1

                # मार्क्स प्रोसेसिंग
                raw_int = target_sub.get('int_m', target_sub.get('internal', 0)) or 0
                raw_ext = target_sub.get('ext_m', target_sub.get('external', 0)) or 0
                raw_tot = target_sub.get('total', None)
                int_val, ext_val = safe_int(raw_int), safe_int(raw_ext)
                tot_val = safe_int(raw_tot) if raw_tot else (int_val + ext_val)
                percentage = round((tot_val / 50) * 100, 2)

                if not is_fail:
                    student_info = {
                        'seat_no': student_data.get('seat_no'), 'prn': student_data.get('prn'),
                        'full_name': student_data.get('full_name'), 'internal': raw_int, 
                        'external': raw_ext, 'total': raw_tot if raw_tot else tot_val,
                        'percentage': percentage, 'total_val': tot_val 
                    }
                    overall_candidates.append(student_info)
                    if gender == 'Female': female_candidates.append(student_info)
                    else: male_candidates.append(student_info)

                    if grade in ['O', 'A+']: grades['dist'] += 1
                    elif grade == 'A': grades['first'] += 1
                    elif grade == 'B+': grades['h_second'] += 1
                    elif grade == 'B': grades['second'] += 1
                    else: grades['p_class'] += 1

        # ✨ निकाल टक्केवारीचे गणित (Final Percentages)
        stats['male_perc'] = round((stats['male_pass'] / stats['male_app'] * 100), 2) if stats['male_app'] > 0 else 0
        stats['female_perc'] = round((stats['female_pass'] / stats['female_app'] * 100), 2) if stats['female_app'] > 0 else 0
        stats['overall_perc'] = round((stats['overall_pass'] / stats['overall_app'] * 100), 2) if stats['overall_app'] > 0 else 0

        target_year_text = PDF_DATA_STORE.get('year_display', '')

        return render_template('subject_report.html', 
                               subject_name=subject_name, subject_code=subject_code,
                               class_year=target_year_text, stats=stats, 
                               overall_toppers=sorted(overall_candidates, key=lambda x: x['total_val'], reverse=True)[:3],
                               male_toppers=sorted(male_candidates, key=lambda x: x['total_val'], reverse=True)[:3], 
                               female_toppers=sorted(female_candidates, key=lambda x: x['total_val'], reverse=True)[:3], 
                               grades=grades)
    except Exception as e:
        return f"Subject Report Error: {str(e)}"
# ---------------------------------------------------
# ERROR HANDLERS
# ---------------------------------------------------

@app.errorhandler(404)
def page_not_found(e):
    """
    Redirects users to the dashboard on 404 errors.
    """
    flash("Navigation Warning: The requested URL was not found.", "warning")
    return redirect(url_for('dashboard'))

@app.errorhandler(500)
def internal_server_error(e):
    """
    Redirects users to the home page on internal server errors.
    """
    flash("Critical Error: An unexpected issue occurred.", "danger")
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)
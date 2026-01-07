# # Import core Flask modules
# from flask import Flask, render_template, request, flash, redirect, url_for, session

# # Standard libraries
# import os

# # Data handling
# import pandas as pd

# # Custom PDF parsers
# import parser              # Old pattern (2019) - For TY
# import parser_nep          # New NEP parser - For FY Only
# import parser_sy           # ✨ NEW: 4 Semester Parser for SY (Save previous code as parser_sy.py)

# # ---------------------------------------------------
# # Flask app initialization
# # ---------------------------------------------------
# app = Flask(__name__)

# # Secret key for session & flash messages
# app.secret_key = "supersecretkey"

# # ---------------------------------------------------
# # File upload configuration
# # ---------------------------------------------------
# UPLOAD_FOLDER = 'uploads'
# os.makedirs(UPLOAD_FOLDER, exist_ok=True)
# app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# # ---------------------------------------------------
# # In-memory global data store
# # ---------------------------------------------------
# PDF_DATA_STORE = {
#     'all_students': [],          
#     'display_students': [],      
#     'course_display': '',        
#     'year_display': '',          
#     'stats': {},                 
#     'pattern': ''                # 'NEP', 'SY_4SEM', or '2019'
# }

# # ---------------------------------------------------
# # Mapping codes to display names
# # ---------------------------------------------------
# COURSE_MAP = {
#     'bcs': 'B.Sc. (Computer Science)',
#     'bca': 'B.C.A. (Science)',
#     'other': 'Other Course'
# }

# YEAR_MAP = {
#     'fy': 'First Year (F.Y.)',
#     'sy': 'Second Year (S.Y.)',
#     'ty': 'Third Year (T.Y.)'
# }

# # ---------------------------------------------------
# # Calculate statistics
# # ---------------------------------------------------
# def calculate_stats(student_list):
#     stats = {
#         'total': len(student_list),
#         'male_pass': 0, 'male_atkt': 0, 'male_fail': 0,
#         'female_pass': 0, 'female_atkt': 0, 'female_fail': 0,
#         'pass': 0, 'atkt': 0, 'fail': 0
#     }

#     for std in student_list:
#         res = std.get('result', 'FAIL').upper()
#         # SY parser might not have gender, default to Male or logic
#         gender = std.get('gender', 'Male') 

#         # Default status
#         status = 'fail'

#         # Result classification
#         if "PASS" in res:
#             status = 'pass'
#             stats['pass'] += 1
#         elif "A.T.K.T" in res or "ATKT" in res:
#             status = 'atkt'
#             stats['atkt'] += 1
#         else:
#             stats['fail'] += 1

#         # Gender-wise stats
#         key = f"{gender.lower()}_{status}"
#         if key in stats:
#             stats[key] += 1

#     return stats

# # ---------------------------------------------------
# # Home page
# # ---------------------------------------------------
# @app.route('/')
# def home():
#     return render_template('index.html')

# # ---------------------------------------------------
# # Analyze uploaded PDF ledger
# # ---------------------------------------------------
# @app.route('/analyze', methods=['POST'])
# def analyze():

#     if 'ledger_pdf' not in request.files:
#         flash('No file uploaded')
#         return redirect(url_for('home'))

#     file = request.files['ledger_pdf']
#     if file.filename == '':
#         return redirect(url_for('home'))

#     class_year = request.form.get('class_year')
#     raw_course = request.form.get('course_name')

#     file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
#     file.save(file_path)

#     # ---------------------------------------------------------
#     # 👇 CHANGE HERE: Split Logic for FY and SY 
#     # ---------------------------------------------------------
#     if class_year == 'fy':
#         print(f"Using NEP Parser for {class_year}")
#         result = parser_nep.main(file_path)
#         PDF_DATA_STORE['pattern'] = 'NEP'
        
#     elif class_year == 'sy':
#         print(f"Using SY (4 Sem) Parser for {class_year}")
#         result = parser_sy.main(file_path) 
#         PDF_DATA_STORE['pattern'] = 'SY_4SEM'
        
#     else:
#         print("Using Standard Parser (3rd Year)")
#         result = parser.main(file_path)
#         PDF_DATA_STORE['pattern'] = '2019'
#     # ---------------------------------------------------------

#     if result['success']:
#         PDF_DATA_STORE['course_display'] = COURSE_MAP.get(raw_course, raw_course)
#         PDF_DATA_STORE['year_display'] = YEAR_MAP.get(class_year, class_year)
#         PDF_DATA_STORE['all_students'] = result.get('data', result.get('student_data')) # handle key diff
#         PDF_DATA_STORE['display_students'] = PDF_DATA_STORE['all_students']
#         PDF_DATA_STORE['stats'] = calculate_stats(PDF_DATA_STORE['all_students'])

#         return redirect(url_for('dashboard'))
#     else:
#         flash(f"Error: {result.get('error')}")
#         return redirect(url_for('home'))

# # ---------------------------------------------------
# # Dashboard page
# # ---------------------------------------------------
# @app.route('/dashboard')
# def dashboard():
#     year_display = PDF_DATA_STORE['year_display']
#     # Hide gender chart for FY and SY (since new parsers might not extract gender)
#     hide_gender = True if ("First Year" in year_display or "Second Year" in year_display) else False

#     return render_template(
#         'dashboard.html',
#         student_data=PDF_DATA_STORE['display_students'],
#         course=PDF_DATA_STORE['course_display'],
#         year=PDF_DATA_STORE['year_display'],
#         stats=PDF_DATA_STORE['stats'],
#         is_fy=hide_gender
#     )

# # ---------------------------------------------------
# # Filter students using Excel seat numbers
# # ---------------------------------------------------
# @app.route('/filter_excel', methods=['POST'])
# def filter_excel():
#     if 'student_excel' not in request.files:
#         return redirect(url_for('dashboard'))

#     excel_file = request.files['student_excel']
#     if excel_file.filename == '':
#         return redirect(url_for('dashboard'))

#     file_path = os.path.join(app.config['UPLOAD_FOLDER'], excel_file.filename)
#     excel_file.save(file_path)

#     try:
#         df = pd.read_excel(file_path)
#         df.columns = [str(c).strip().lower() for c in df.columns]

#         if 'seat no' in df.columns:
#             target_seats = df['seat no'].astype(str).str.strip().tolist()

#             filtered_list = [
#                 s for s in PDF_DATA_STORE['all_students']
#                 if str(s['seat_no']).strip() in target_seats
#             ]

#             PDF_DATA_STORE['display_students'] = filtered_list
#             PDF_DATA_STORE['stats'] = calculate_stats(filtered_list)

#             flash(f"Filter Applied! Showing {len(filtered_list)} students.")
#         else:
#             flash("Error: Excel must have a 'Seat No' column.")
#     except Exception as e:
#         flash(f"Error reading Excel: {str(e)}")

#     return redirect(url_for('dashboard'))

# @app.route('/reset_filter')
# def reset_filter():
#     PDF_DATA_STORE['display_students'] = PDF_DATA_STORE['all_students']
#     PDF_DATA_STORE['stats'] = calculate_stats(PDF_DATA_STORE['all_students'])
#     return redirect(url_for('dashboard'))

# # ---------------------------------------------------
# # Report View
# # ---------------------------------------------------
# @app.route('/report/<string:seat_no>')
# def view_report(seat_no):
#     all_students = PDF_DATA_STORE.get('all_students', [])
#     student = next((s for s in all_students if str(s['seat_no']).strip() == str(seat_no).strip()), None)
    
#     if student:
#         # 👇 CHECK PATTERN HERE
#         pattern = PDF_DATA_STORE.get('pattern', '')
        
#         if pattern == 'SY_4SEM':
#             # This loads the 4-semester HTML template for SY
#             return render_template('report_sy.html', student=student)
#         else:
#             # FY or TY
#             return render_template('report_card.html', student=student)
#     else:
#         return "Student Not Found"

# # ---------------------------------------------------
# # Subject Analysis
# # ---------------------------------------------------
# @app.route('/student_analysis')
# def student_analysis():
#     return render_template('analysis.html')

# def get_unique_subjects():
#     all_students = PDF_DATA_STORE.get('all_students', [])
#     subjects = set()

#     for std in all_students:
#         # Check all possible subject keys
#         keys_to_check = ['subjects', 'sem1_subjects', 'sem2_subjects', 'sem3_subjects', 'sem4_subjects']
#         for key in keys_to_check:
#             if key in std:
#                 for sub in std[key]:
#                     subjects.add(sub['code'])
#     return sorted(list(subjects))

# @app.route('/subject_analysis', methods=['GET', 'POST'])
# def subject_analysis():
#     all_students = PDF_DATA_STORE.get('all_students', [])
#     unique_subjects = get_unique_subjects()

#     selected_subject = None
#     subject_data = []
    
#     stats = {
#         'total': 0, 'pass': 0, 'fail': 0,
#         'male': 0, 'female': 0,
#         'male_pass': 0, 'male_fail': 0,
#         'female_pass': 0, 'female_fail': 0
#     }
#     top_3 = []
#     filter_active = False
#     target_seats = []

#     if request.method == 'POST':
#         selected_subject = request.form.get('subject_code')
#         excel_file = request.files.get('student_excel')

#         # Excel Filter Logic
#         if excel_file and excel_file.filename != '':
#             try:
#                 df = pd.read_excel(excel_file)
#                 df.columns = [str(c).strip().lower() for c in df.columns]
#                 if 'seat no' in df.columns:
#                     target_seats = df['seat no'].astype(str).apply(lambda x: x.split('.')[0].strip()).tolist()
#                     filter_active = True
#             except:
#                 pass

#         # Processing Students
#         for std in all_students:
#             current_seat = str(std.get('seat_no', '')).strip()
#             if filter_active and current_seat not in target_seats:
#                 continue

#             # Merge Subjects
#             student_all_subjects = []
#             keys_to_check = ['subjects', 'sem1_subjects', 'sem2_subjects', 'sem3_subjects', 'sem4_subjects']
#             for key in keys_to_check:
#                 if key in std:
#                     student_all_subjects += std[key]

#             # Find Subject
#             target_sub = next((s for s in student_all_subjects if s['code'] == selected_subject), None)

#             if target_sub:
#                 # --- DEBUG PRINT (Check Terminal Output) ---
#                 # print(f"DEBUG: {std['full_name']} - {selected_subject} - Keys: {target_sub.keys()}")
#                 # -------------------------------------------

#                 grade = str(target_sub.get('grd', target_sub.get('grade', '-'))).upper()
#                 status = "FAIL" if grade in ['F', 'FFF', 'FAIL', 'AB', '---'] else "PASS"
#                 gender = std.get('gender', 'Male')

#                 # Marks Calculation Logic
#                 p_int = target_sub.get('p_int', '')
#                 m_int = target_sub.get('int_m', target_sub.get('internal', ''))
                
#                 # Internal
#                 if m_int in ['-', '', None, 'AAA', 'AA']:
#                     display_int = "-"
#                 elif p_int in ['-', '', None]:
#                     display_int = str(m_int)
#                 else:
#                     display_int = f"{p_int} {m_int}"

#                 # External
#                 p_ext = target_sub.get('p_ext', '')
#                 m_ext = target_sub.get('ext_m', target_sub.get('external', ''))
                
#                 if m_ext in ['-', '', None, 'AAA', 'AA']:
#                     # Check Practical if External missing
#                     p_pr = target_sub.get('p_pr', '')
#                     m_pr = target_sub.get('pr_m', '')
#                     if m_pr not in ['-', '', None]:
#                         display_ext = f"{p_pr} {m_pr} (PR)"
#                     else:
#                         display_ext = "-"
#                 elif p_ext in ['-', '', None]:
#                     display_ext = str(m_ext)
#                 else:
#                     display_ext = f"{p_ext} {m_ext}"

#                 # Stats Update
#                 stats['total'] += 1
#                 if gender == 'Male':
#                     stats['male'] += 1
#                     if status == "PASS": stats['male_pass'] += 1
#                     else: stats['male_fail'] += 1
#                 else:
#                     stats['female'] += 1
#                     if status == "PASS": stats['female_pass'] += 1
#                     else: stats['female_fail'] += 1

#                 if status == "PASS": stats['pass'] += 1
#                 else: stats['fail'] += 1

#                 total_marks_raw = str(target_sub.get('total', '0'))
#                 clean_tot = ''.join(filter(str.isdigit, total_marks_raw))

#                 subject_data.append({
#                     'seat_no': current_seat,
#                     'name': std.get('full_name', std.get('name', 'Unknown')),
#                     'gender': gender,
#                     'internal': display_int,
#                     'external': display_ext,
#                     'total': total_marks_raw,
#                     'grade': grade,
#                     'status': status,
#                     'marks_val': int(clean_tot) if clean_tot else 0
#                 })

#         # Top 3 Logic
#         passed_students = [s for s in subject_data if s['status'] == "PASS"]
#         passed_students.sort(key=lambda x: x['marks_val'], reverse=True)
#         top_3 = passed_students[:3]

#     is_nep = (PDF_DATA_STORE.get('pattern') == 'NEP')

#     return render_template(
#         'subject_analysis.html',
#         unique_subjects=unique_subjects,
#         selected_subject=selected_subject,
#         subject_data=subject_data,
#         stats=stats,
#         top_3=top_3,
#         filter_active=filter_active,
#         is_nep=is_nep
#     )
# if __name__ == '__main__':
#     app.run(debug=True)


from flask import Flask, render_template, request, flash, redirect, url_for, session
import os
import pandas as pd
import sqlite3
import json
import parser
import parser_nep
import parser_sy

app = Flask(__name__)
app.secret_key = "supersecretkey"

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# डेटा स्टोअर करण्यासाठी ग्लोबल व्हेरिएबल
PDF_DATA_STORE = {
    'all_students': [],          
    'display_students': [],      
    'course_display': '',        
    'year_display': '',          
    'stats': {},                 
    'pattern': ''                
}

COURSE_MAP = {
    'bcs': 'B.Sc. (Computer Science)',
    'bca': 'B.C.A. (Science)',
    'other': 'Other Course'
}

YEAR_MAP = {
    'fy': 'First Year (F.Y.)',
    'sy': 'Second Year (S.Y.)',
    'ty': 'Third Year (T.Y.)'
}

# ---------------------------------------------------
# DATABASE SETUP
# ---------------------------------------------------
def init_db():
    conn = sqlite3.connect('college_results.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prn TEXT,
            seat_no TEXT,
            full_name TEXT,
            mother_name TEXT,
            course TEXT,
            year TEXT,
            result TEXT,
            total_marks TEXT,
            pattern TEXT,
            all_data_json TEXT,
            UNIQUE(prn, year)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ---------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------
def calculate_stats(student_list):
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
        else:
            stats['fail'] += 1
        key = f"{gender.lower()}_{status}"
        if key in stats: stats[key] += 1
    return stats

# ---------------------------------------------------
# ROUTES
# ---------------------------------------------------
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    if 'ledger_pdf' not in request.files:
        flash('No file uploaded')
        return redirect(url_for('home'))

    file = request.files['ledger_pdf']
    if file.filename == '': return redirect(url_for('home'))

    class_year = request.form.get('class_year')
    raw_course = request.form.get('course_name')
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(file_path)

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
        PDF_DATA_STORE['course_display'] = COURSE_MAP.get(raw_course, raw_course)
        PDF_DATA_STORE['year_display'] = YEAR_MAP.get(class_year, class_year)
        PDF_DATA_STORE['all_students'] = result.get('data', result.get('student_data'))
        PDF_DATA_STORE['display_students'] = PDF_DATA_STORE['all_students']
        PDF_DATA_STORE['stats'] = calculate_stats(PDF_DATA_STORE['all_students'])
        return redirect(url_for('dashboard'))
    else:
        flash(f"Error: {result.get('error')}")
        return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    year_display = PDF_DATA_STORE['year_display']
    hide_gender = True if ("First Year" in year_display or "Second Year" in year_display) else False
    return render_template('dashboard.html', 
                           student_data=PDF_DATA_STORE['display_students'],
                           course=PDF_DATA_STORE['course_display'],
                           year=PDF_DATA_STORE['year_display'],
                           stats=PDF_DATA_STORE['stats'],
                           is_fy=hide_gender)

# --- नवीन: डेटाबेसमध्ये डेटा सेव्ह करणे ---
@app.route('/save_to_db', methods=['POST'])
def save_to_db():
    all_students = PDF_DATA_STORE.get('all_students', [])
    course = PDF_DATA_STORE.get('course_display', '')
    year = PDF_DATA_STORE.get('year_display', '')
    pattern = PDF_DATA_STORE.get('pattern', '')

    if not all_students:
        flash("No data to save!")
        return redirect(url_for('dashboard'))

    try:
        conn = sqlite3.connect('college_results.db')
        cursor = conn.cursor()
        for std in all_students:
            student_json = json.dumps(std)
            cursor.execute('''
                INSERT OR REPLACE INTO students 
                (prn, seat_no, full_name, mother_name, course, year, result, total_marks, pattern, all_data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (std['prn'], std['seat_no'], std['full_name'], std['mother_name'], 
                  course, year, std['result'], std.get('total_marks', '-'), pattern, student_json))
        conn.commit()
        conn.close()
        flash(f"Successfully saved {len(all_students)} students to database!")
    except Exception as e:
        flash(f"Database Error: {str(e)}")
    return redirect(url_for('dashboard'))

# --- नवीन: सेव्ह केलेला डेटा लोड करणे ---
@app.route('/view_saved')
def view_saved():
    course_code = request.args.get('course')
    year_code = request.args.get('year')
    course_full = COURSE_MAP.get(course_code)
    year_full = YEAR_MAP.get(year_code)

    conn = sqlite3.connect('college_results.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM students WHERE course = ? AND year = ?', (course_full, year_full))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        flash("No saved data found for this selection.")
        return redirect(url_for('home'))

    saved_students = [json.loads(row['all_data_json']) for row in rows]
    
    # ग्लोबल स्टोअर अपडेट करा
    PDF_DATA_STORE['all_students'] = saved_students
    PDF_DATA_STORE['display_students'] = saved_students
    PDF_DATA_STORE['course_display'] = course_full
    PDF_DATA_STORE['year_display'] = year_full
    PDF_DATA_STORE['pattern'] = rows[0]['pattern']
    PDF_DATA_STORE['stats'] = calculate_stats(saved_students)

    return redirect(url_for('dashboard'))

@app.route('/filter_excel', methods=['POST'])
def filter_excel():
    if 'student_excel' not in request.files: return redirect(url_for('dashboard'))
    excel_file = request.files['student_excel']
    if excel_file.filename == '': return redirect(url_for('dashboard'))
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], excel_file.filename)
    excel_file.save(file_path)
    try:
        df = pd.read_excel(file_path)
        df.columns = [str(c).strip().lower() for c in df.columns]
        if 'seat no' in df.columns:
            target_seats = df['seat no'].astype(str).str.strip().tolist()
            filtered_list = [s for s in PDF_DATA_STORE['all_students'] if str(s['seat_no']).strip() in target_seats]
            PDF_DATA_STORE['display_students'] = filtered_list
            PDF_DATA_STORE['stats'] = calculate_stats(filtered_list)
            flash(f"Filter Applied! Showing {len(filtered_list)} students.")
        else: flash("Error: Excel must have a 'Seat No' column.")
    except Exception as e: flash(f"Error reading Excel: {str(e)}")
    return redirect(url_for('dashboard'))

@app.route('/reset_filter')
def reset_filter():
    PDF_DATA_STORE['display_students'] = PDF_DATA_STORE['all_students']
    PDF_DATA_STORE['stats'] = calculate_stats(PDF_DATA_STORE['all_students'])
    return redirect(url_for('dashboard'))

@app.route('/report/<string:seat_no>')
def view_report(seat_no):
    all_students = PDF_DATA_STORE.get('all_students', [])
    student = next((s for s in all_students if str(s['seat_no']).strip() == str(seat_no).strip()), None)
    if student:
        pattern = PDF_DATA_STORE.get('pattern', '')
        if pattern == 'SY_4SEM': return render_template('report_sy.html', student=student)
        else: return render_template('report_card.html', student=student)
    return "Student Not Found"

@app.route('/student_analysis')
def student_analysis():
    return render_template('analysis.html')

def get_unique_subjects():
    all_students = PDF_DATA_STORE.get('all_students', [])
    subjects = set()
    for std in all_students:
        for key in ['subjects', 'sem1_subjects', 'sem2_subjects', 'sem3_subjects', 'sem4_subjects']:
            if key in std:
                for sub in std[key]: subjects.add(sub['code'])
    return sorted(list(subjects))

# @app.route('/subject_analysis', methods=['GET', 'POST'])
# def subject_analysis():
#     all_students = PDF_DATA_STORE.get('all_students', [])
#     unique_subjects = get_unique_subjects()
#     selected_subject, subject_data, top_3, filter_active = None, [], [], False
    
#     # नवीन काउंटर्स ॲड केले आहेत
#     stats = {
#         'total': 0, 'pass': 0, 'fail': 0, 'male': 0, 'female': 0,
#         'male_pass': 0, 'male_fail': 0, 'female_pass': 0, 'female_fail': 0,
#         'distinction': 0, 'first_class': 0, 'higher_second': 0, 
#         'second_class': 0, 'pass_class': 0
#     }

#     if request.method == 'POST':
#         selected_subject = request.form.get('subject_code')
#         # ... (Excel filter logic तसेच ठेवा) ...

#         for std in all_students:
#             # ... (तुमचा जुना फिल्टर आणि सब्जेक्ट शोधण्याचा कोड) ...
#             if target_sub:
#                 grade = str(target_sub.get('grd', target_sub.get('grade', '-'))).upper()
#                 status = "FAIL" if grade in ['F', 'FFF', 'FAIL', 'AB', '---'] else "PASS"
#                 gender = std.get('gender', 'Male')
                
#                 # क्लास ठरवणे (JavaScript फिल्टरसाठी)
#                 grade_class = "fail"
#                 if status == "PASS":
#                     if grade in ['O', 'A+']: 
#                         grade_class = "distinction"
#                         stats['distinction'] += 1
#                     elif grade == 'A': 
#                         grade_class = "first_class"
#                         stats['first_class'] += 1
#                     elif grade == 'B+': 
#                         grade_class = "higher_second"
#                         stats['higher_second'] += 1
#                     elif grade == 'B': 
#                         grade_class = "second_class"
#                         stats['second_class'] += 1
#                     elif grade in ['C', 'D', 'P']: 
#                         grade_class = "pass_class"
#                         stats['pass_class'] += 1
#                 else:
#                     stats['fail'] += 1

#                 # Record मध्ये 'grade_class' ॲड करा
#                 subject_data.append({
#                     'seat_no': str(std.get('seat_no', '')).strip(),
#                     'name': std.get('full_name', 'Unknown'),
#                     'gender': gender,
#                     'internal': target_sub.get('int_m', target_sub.get('internal', '-')),
#                     'external': target_sub.get('ext_m', target_sub.get('external', '-')),
#                     'total': str(target_sub.get('total', '0')),
#                     'grade': grade,
#                     'status': status,
#                     'grade_class': grade_class, # फिल्टरसाठी महत्त्वाचे
#                     'marks_val': int(''.join(filter(str.isdigit, str(target_sub.get('total', '0')))) or 0)
#                 })

#         passed = [s for s in subject_data if s['status'] == "PASS"]
#         passed.sort(key=lambda x: x['marks_val'], reverse=True)
#         top_3 = passed[:3]

#     is_nep = (PDF_DATA_STORE.get('pattern') == 'NEP' or PDF_DATA_STORE.get('pattern') == 'SY_4SEM')
#     return render_template('subject_analysis.html', unique_subjects=unique_subjects, 
#                            selected_subject=selected_subject, subject_data=subject_data, 
#                            stats=stats, top_3=top_3, filter_active=filter_active, is_nep=is_nep)

@app.route('/subject_analysis', methods=['GET', 'POST'])
def subject_analysis():
    all_students = PDF_DATA_STORE.get('all_students', [])
    unique_subjects = get_unique_subjects()
    selected_subject, subject_data, top_3, filter_active = None, [], [], False
    
    stats = {
        'total': 0, 'pass': 0, 'fail': 0, 'male': 0, 'female': 0,
        'male_pass': 0, 'male_fail': 0, 'female_pass': 0, 'female_fail': 0,
        'distinction': 0, 'first_class': 0, 'higher_second': 0, 
        'second_class': 0, 'pass_class': 0
    }

    if request.method == 'POST':
        selected_subject = request.form.get('subject_code')
        excel_file = request.files.get('student_excel')
        target_seats = []
        if excel_file and excel_file.filename != '':
            try:
                df = pd.read_excel(excel_file)
                df.columns = [str(c).strip().lower() for c in df.columns]
                if 'seat no' in df.columns:
                    target_seats = df['seat no'].astype(str).apply(lambda x: x.split('.')[0].strip()).tolist()
                    filter_active = True
            except: pass

        for std in all_students:
            current_seat = str(std.get('seat_no', '')).strip()
            if filter_active and current_seat not in target_seats: continue
            
            student_all_subjects = []
            for key in ['subjects', 'sem1_subjects', 'sem2_subjects', 'sem3_subjects', 'sem4_subjects']:
                if key in std: student_all_subjects += std[key]

            target_sub = next((s for s in student_all_subjects if s['code'] == selected_subject), None)
            if target_sub:
                grade = str(target_sub.get('grd', target_sub.get('grade', '-'))).upper()
                status = "FAIL" if grade in ['F', 'FFF', 'FAIL', 'AB', '---'] else "PASS"
                gender = std.get('gender', 'Male')
                
                # --- ग्रेड नुसार क्लासचे वर्गीकरण आणि मोजणी ---
                grade_class = "fail" # Default
                if status == "PASS":
                    if grade in ['O', 'A+']: 
                        grade_class = "distinction"; stats['distinction'] += 1
                    elif grade == 'A': 
                        grade_class = "first_class"; stats['first_class'] += 1
                    elif grade == 'B+': 
                        grade_class = "higher_second"; stats['higher_second'] += 1
                    elif grade == 'B': 
                        grade_class = "second_class"; stats['second_class'] += 1
                    elif grade in ['C', 'D', 'P']: 
                        grade_class = "pass_class"; stats['pass_class'] += 1
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
                
                if status == "PASS": stats['pass'] += 1
                else: stats['fail'] += 1

                subject_data.append({
                    'seat_no': current_seat,
                    'name': std.get('full_name', 'Unknown'),
                    'gender': gender,
                    'internal': target_sub.get('int_m', target_sub.get('internal', '-')),
                    'external': target_sub.get('ext_m', target_sub.get('external', '-')),
                    'total': str(target_sub.get('total', '0')),
                    'grade': grade,
                    'status': status,
                    'grade_class': grade_class, # JavaScript फिल्टरसाठी महत्त्वाचे
                    'marks_val': int(''.join(filter(str.isdigit, str(target_sub.get('total', '0')))) or 0)
                })

        passed = [s for s in subject_data if s['status'] == "PASS"]
        passed.sort(key=lambda x: x['marks_val'], reverse=True)
        top_3 = passed[:3]

    is_nep = (PDF_DATA_STORE.get('pattern') == 'NEP' or PDF_DATA_STORE.get('pattern') == 'SY_4SEM')
    return render_template('subject_analysis.html', unique_subjects=unique_subjects, 
                           selected_subject=selected_subject, subject_data=subject_data, 
                           stats=stats, top_3=top_3, filter_active=filter_active, is_nep=is_nep)

if __name__ == '__main__':
    app.run(debug=True)
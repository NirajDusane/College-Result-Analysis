# Import core Flask modules
from flask import Flask, render_template, request, flash, redirect, url_for, session

# Standard libraries
import os

# Data handling
import pandas as pd

# Custom PDF parsers
import parser              # Old pattern (2019)
import parser_nep          # New NEP parser (First Year)

# ---------------------------------------------------
# Flask app initialization
# ---------------------------------------------------
app = Flask(__name__)

# Secret key for session & flash messages
app.secret_key = "supersecretkey"

# ---------------------------------------------------
# File upload configuration
# ---------------------------------------------------
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# ---------------------------------------------------
# In-memory global data store
# (Used instead of database)
# ---------------------------------------------------
PDF_DATA_STORE = {
    'all_students': [],          # All parsed students
    'display_students': [],      # Students after filter
    'course_display': '',        # Course name for UI
    'year_display': '',          # Year name for UI
    'stats': {},                 # Calculated statistics
    'pattern': ''                # NEP or 2019 pattern
}

# ---------------------------------------------------
# Mapping codes to display names
# ---------------------------------------------------
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
# Calculate overall pass / fail / ATKT statistics
# ---------------------------------------------------
def calculate_stats(student_list):
    stats = {
        'total': len(student_list),
        'male_pass': 0, 'male_atkt': 0, 'male_fail': 0,
        'female_pass': 0, 'female_atkt': 0, 'female_fail': 0,
        'pass': 0, 'atkt': 0, 'fail': 0
    }

    for std in student_list:
        res = std['result'].upper()
        gender = std.get('gender', 'Male')

        # Default status
        status = 'fail'

        # Result classification
        if "PASS" in res:
            status = 'pass'
            stats['pass'] += 1
        elif "A.T.K.T" in res:
            status = 'atkt'
            stats['atkt'] += 1
        else:
            stats['fail'] += 1

        # Gender-wise stats
        key = f"{gender.lower()}_{status}"
        if key in stats:
            stats[key] += 1

    return stats

# ---------------------------------------------------
# Home page
# ---------------------------------------------------
@app.route('/')
def home():
    return render_template('index.html')

# ---------------------------------------------------
# Analyze uploaded PDF ledger
# ---------------------------------------------------
@app.route('/analyze', methods=['POST'])
def analyze():

    # Check file presence
    if 'ledger_pdf' not in request.files:
        flash('No file uploaded')
        return redirect(url_for('home'))

    file = request.files['ledger_pdf']
    if file.filename == '':
        return redirect(url_for('home'))

    # Read form values
    class_year = request.form.get('class_year')
    raw_course = request.form.get('course_name')

    # Save uploaded file
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(file_path)

    # Choose parser based on year
    if class_year == 'fy':
        result = parser_nep.main(file_path)
        PDF_DATA_STORE['pattern'] = 'NEP'
    else:
        result = parser.main(file_path)
        PDF_DATA_STORE['pattern'] = '2019'

    # If parsing successful
    if result['success']:
        PDF_DATA_STORE['course_display'] = COURSE_MAP.get(raw_course, raw_course)
        PDF_DATA_STORE['year_display'] = YEAR_MAP.get(class_year, class_year)

        PDF_DATA_STORE['all_students'] = result['student_data']
        PDF_DATA_STORE['display_students'] = result['student_data']

        PDF_DATA_STORE['stats'] = calculate_stats(result['student_data'])

        return redirect(url_for('dashboard'))
    else:
        flash(f"Error: {result.get('error')}")
        return redirect(url_for('home'))

# ---------------------------------------------------
# Dashboard page
# ---------------------------------------------------
@app.route('/dashboard')
def dashboard():

    # Identify First Year (NEP)
    is_fy = True if "First Year" in PDF_DATA_STORE['year_display'] else False

    return render_template(
        'dashboard.html',
        student_data=PDF_DATA_STORE['display_students'],
        course=PDF_DATA_STORE['course_display'],
        year=PDF_DATA_STORE['year_display'],
        stats=PDF_DATA_STORE['stats'],
        is_fy=is_fy
    )

# ---------------------------------------------------
# Filter students using Excel seat numbers
# ---------------------------------------------------
@app.route('/filter_excel', methods=['POST'])
def filter_excel():

    if 'student_excel' not in request.files:
        return redirect(url_for('dashboard'))

    excel_file = request.files['student_excel']
    if excel_file.filename == '':
        return redirect(url_for('dashboard'))

    file_path = os.path.join(app.config['UPLOAD_FOLDER'], excel_file.filename)
    excel_file.save(file_path)

    try:
        df = pd.read_excel(file_path)
        df.columns = [str(c).strip().lower() for c in df.columns]

        if 'seat no' in df.columns:
            target_seats = df['seat no'].astype(str).str.strip().tolist()

            # Filter students
            filtered_list = [
                s for s in PDF_DATA_STORE['all_students']
                if str(s['seat_no']).strip() in target_seats
            ]

            PDF_DATA_STORE['display_students'] = filtered_list
            PDF_DATA_STORE['stats'] = calculate_stats(filtered_list)

            flash(f"Filter Applied! Showing {len(filtered_list)} students.")
        else:
            flash("Error: Excel must have a 'Seat No' column.")
    except Exception as e:
        flash(f"Error reading Excel: {str(e)}")

    return redirect(url_for('dashboard'))

# ---------------------------------------------------
# Reset Excel filter
# ---------------------------------------------------
@app.route('/reset_filter')
def reset_filter():
    PDF_DATA_STORE['display_students'] = PDF_DATA_STORE['all_students']
    PDF_DATA_STORE['stats'] = calculate_stats(PDF_DATA_STORE['all_students'])
    return redirect(url_for('dashboard'))

# ---------------------------------------------------
# Individual student report card
# ---------------------------------------------------
@app.route('/report/<string:seat_no>')
def view_report(seat_no):

    all_students = PDF_DATA_STORE.get('all_students', [])

    student = next(
        (s for s in all_students if str(s['seat_no']).strip() == str(seat_no).strip()),
        None
    )

    if student:
        return render_template('report_card.html', student=student)
    else:
        return "Student Not Found"

# ---------------------------------------------------
# Student analysis landing page
# ---------------------------------------------------
@app.route('/student_analysis')
def student_analysis():
    return render_template('analysis.html')

# ---------------------------------------------------
# Extract unique subject codes
# ---------------------------------------------------
def get_unique_subjects():
    all_students = PDF_DATA_STORE.get('all_students', [])
    subjects = set()

    for std in all_students:
        if 'subjects' in std:
            for sub in std['subjects']:
                subjects.add(sub['code'])

        if 'sem1_subjects' in std:
            for sub in std['sem1_subjects']:
                subjects.add(sub['code'])

        if 'sem2_subjects' in std:
            for sub in std['sem2_subjects']:
                subjects.add(sub['code'])

    return sorted(list(subjects))

# ---------------------------------------------------
# Subject-wise analysis
# ---------------------------------------------------
@app.route('/subject_analysis', methods=['GET', 'POST'])
def subject_analysis():

    all_students = PDF_DATA_STORE.get('all_students', [])
    unique_subjects = get_unique_subjects()

    selected_subject = None
    subject_data = []

    # Stats container
    stats = {
        'total': 0, 'pass': 0, 'fail': 0,
        'male': 0, 'female': 0,
        'male_pass': 0, 'male_fail': 0,
        'female_pass': 0, 'female_fail': 0
    }

    top_3 = []
    filter_active = False

    if request.method == 'POST':
        selected_subject = request.form.get('subject_code')
        excel_file = request.files.get('student_excel')

        target_seats = []

        # Optional Excel filter
        if excel_file and excel_file.filename != '':
            try:
                df = pd.read_excel(excel_file)
                df.columns = [str(c).strip().lower() for c in df.columns]
                if 'seat no' in df.columns:
                    target_seats = df['seat no'].astype(str).str.strip().tolist()
                    filter_active = True
            except:
                pass

        # Process each student
        for std in all_students:

            if filter_active and str(std['seat_no']).strip() not in target_seats:
                continue

            # Merge all subject lists
            student_all_subjects = []
            if 'subjects' in std:
                student_all_subjects += std['subjects']
            if 'sem1_subjects' in std:
                student_all_subjects += std['sem1_subjects']
            if 'sem2_subjects' in std:
                student_all_subjects += std['sem2_subjects']

            target_sub = next(
                (s for s in student_all_subjects if s['code'] == selected_subject),
                None
            )

            if target_sub:
                grade = str(target_sub.get('grd', target_sub.get('grade', '-'))).upper()
                status = "FAIL" if grade in ['F', 'FFF', 'FAIL'] else "PASS"
                gender = std.get('gender', 'Male')

                # Handle NEP & 2019 formats
                int_val = target_sub.get('int_m', target_sub.get('internal', '-'))
                ext_val = target_sub.get('ext_m', target_sub.get('external', '-'))

                p_int = target_sub.get('p_int', '')
                p_ext = target_sub.get('p_ext', '')

                display_int = f"{p_int} {int_val}".strip() if p_int and p_int != "-" else int_val
                display_ext = f"{p_ext} {ext_val}".strip() if p_ext and p_ext != "-" else ext_val

                # Stats update
                stats['total'] += 1
                if gender == 'Male':
                    stats['male'] += 1
                    stats['male_pass' if status == "PASS" else 'male_fail'] += 1
                else:
                    stats['female'] += 1
                    stats['female_pass' if status == "PASS" else 'female_fail'] += 1

                stats['pass' if status == "PASS" else 'fail'] += 1

                total_marks_raw = str(target_sub.get('total', '0'))
                clean_tot = ''.join(filter(str.isdigit, total_marks_raw))

                subject_data.append({
                    'seat_no': std['seat_no'],
                    'name': std['full_name'],
                    'gender': gender,
                    'internal': display_int,
                    'external': display_ext,
                    'total': total_marks_raw,
                    'grade': grade,
                    'status': status,
                    'marks_val': int(clean_tot) if clean_tot else 0
                })

        # Top 3 performers
        passed_students = [s for s in subject_data if s['status'] == "PASS"]
        passed_students.sort(key=lambda x: x['marks_val'], reverse=True)
        top_3 = passed_students[:3]

    is_nep = (PDF_DATA_STORE.get('pattern') == 'NEP')

    return render_template(
        'subject_analysis.html',
        unique_subjects=unique_subjects,
        selected_subject=selected_subject,
        subject_data=subject_data,
        stats=stats,
        top_3=top_3,
        filter_active=filter_active,
        is_nep=is_nep
    )

# ---------------------------------------------------
# Application entry point
# ---------------------------------------------------
if __name__ == '__main__':
    app.run(debug=True)

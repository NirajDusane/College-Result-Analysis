from flask import Flask, render_template, request, flash, redirect, url_for
import os
import pandas as pd
import parser

app = Flask(__name__)
app.secret_key = "supersecretkey"

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# डेटा स्टोअर करण्यासाठी ग्लोबल व्हेरिएबल
PDF_DATA_STORE = {
    'all_students': [],
    'display_students': [],
    'course_display': '', # पूर्ण नाव (उदा. B.Sc. Computer Science)
    'year_display': '',   # पूर्ण वर्ष (उदा. Third Year)
    'stats': {}           # Pass/Fail काउंट्स
}

# कोर्स आणि वर्षाचे पूर्ण नाव दाखवण्यासाठी मॅपिंग
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

def calculate_stats(student_list):
    """विद्यार्थ्यांच्या रिझल्टवरून Pass, Fail, ATKT मोजणे"""
    stats = {
        'total': len(student_list),
        'pass': 0,
        'fail': 0,
        'atkt': 0
    }
    
    for std in student_list:
        res = std['result'].upper()
        if "PASS" in res:
            stats['pass'] += 1
        elif "A.T.K.T" in res:
            stats['atkt'] += 1
        else:
            stats['fail'] += 1
            
    return stats

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    if 'ledger_pdf' not in request.files:
        flash('No file uploaded')
        return redirect(url_for('home'))
    
    file = request.files['ledger_pdf']
    if file.filename == '':
        return redirect(url_for('home'))

    if file:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)
        
        result = parser.main(file_path)
        
        if result['success']:
            # फॉर्ममधून आलेले शॉर्ट कोड्स (bcs, ty)
            raw_course = request.form.get('course_name')
            raw_year = request.form.get('class_year')

            # मॅपिंग वापरून पूर्ण नावे सेट करा
            PDF_DATA_STORE['course_display'] = COURSE_MAP.get(raw_course, raw_course)
            PDF_DATA_STORE['year_display'] = YEAR_MAP.get(raw_year, raw_year)
            
            # डेटा सेव्ह करा
            PDF_DATA_STORE['all_students'] = result['student_data']
            PDF_DATA_STORE['display_students'] = result['student_data']
            
            # आकडेवारी मोजा
            PDF_DATA_STORE['stats'] = calculate_stats(result['student_data'])
            
            return redirect(url_for('dashboard'))
        else:
            flash(f"Error: {result.get('error')}")
            return redirect(url_for('home'))

@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html', 
                           student_data=PDF_DATA_STORE['display_students'],
                           course=PDF_DATA_STORE['course_display'], # पूर्ण नाव
                           year=PDF_DATA_STORE['year_display'],     # पूर्ण वर्ष
                           stats=PDF_DATA_STORE['stats'])           # आकडेवारी

@app.route('/filter_excel', methods=['POST'])
def filter_excel():
    if 'student_excel' not in request.files: return redirect(url_for('dashboard'))
    excel_file = request.files['student_excel']
    if excel_file.filename == '': return redirect(url_for('dashboard'))

    if excel_file:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], excel_file.filename)
        excel_file.save(file_path)
        try:
            df = pd.read_excel(file_path)
            df.columns = [c.strip().lower() for c in df.columns]
            if 'seat no' in df.columns:
                target_seats = df['seat no'].astype(str).str.strip().tolist()
                filtered_list = [s for s in PDF_DATA_STORE['all_students'] if str(s['seat_no']).strip() in target_seats]
                
                PDF_DATA_STORE['display_students'] = filtered_list
                # फिल्टर केल्यानंतर आकडेवारी अपडेट करा
                PDF_DATA_STORE['stats'] = calculate_stats(filtered_list)
                
                flash(f"Filter Applied! Showing {len(filtered_list)} students.")
            else:
                flash("Error: Excel must have a 'Seat No' column.")
        except Exception as e:
            flash(f"Error reading Excel: {str(e)}")

    return redirect(url_for('dashboard'))

@app.route('/reset_filter')
def reset_filter():
    PDF_DATA_STORE['display_students'] = PDF_DATA_STORE['all_students']
    # रिसेट केल्यानंतर आकडेवारी अपडेट करा
    PDF_DATA_STORE['stats'] = calculate_stats(PDF_DATA_STORE['all_students'])
    flash("Filter Reset! Showing all students.")
    return redirect(url_for('dashboard'))

@app.route('/report/<string:seat_no>')
def view_report(seat_no):
    all_students = PDF_DATA_STORE.get('all_students', [])
    student = next((s for s in all_students if str(s['seat_no']).strip() == str(seat_no).strip()), None)
    if student: return render_template('report_card.html', student=student)
    else: return "Student Not Found"

@app.route('/student_analysis')
def student_analysis():
    return render_template('analysis.html')

# === नवीन: Subject Codes लिस्ट काढण्यासाठी ===
def get_unique_subjects():
    all_students = PDF_DATA_STORE.get('all_students', [])
    subjects = set()
    for std in all_students:
        for sub in std['subjects']:
            subjects.add(sub['code'])
    return sorted(list(subjects))

# app.py मध्ये subject_analysis फंक्शन पूर्ण बदला:

# app.py मधील subject_analysis फंक्शन मध्ये हे बदल करा:

@app.route('/subject_analysis', methods=['GET', 'POST'])
def subject_analysis():
    all_students = PDF_DATA_STORE.get('all_students', [])
    unique_subjects = get_unique_subjects()
    
    selected_subject = None
    subject_data = []
    # नवीन काउंटर्स ॲड केले आहेत
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
        if excel_file and excel_file.filename != '':
            try:
                # ... (तुमचा जुना एक्सेल वाचनाचा कोड) ...
                df = pd.read_excel(excel_file)
                df.columns = [c.strip().lower() for c in df.columns]
                if 'seat no' in df.columns:
                    target_seats = df['seat no'].astype(str).str.strip().tolist()
                    filter_active = True
            except: pass

        for std in all_students:
            if filter_active and str(std['seat_no']).strip() not in target_seats:
                continue

            target_sub = next((s for s in std['subjects'] if s['code'] == selected_subject), None)
            
            if target_sub:
                status = "FAIL" if target_sub['grade'] == 'F' else "PASS"
                gender = std.get('gender', 'Male') # Default Male जर सापडले नाही तर

                # --- मोजणी (Counting Logic) ---
                stats['total'] += 1
                if gender == 'Male':
                    stats['male'] += 1
                    if status == "PASS": stats['male_pass'] += 1
                    else: stats['male_fail'] += 1
                else:
                    stats['female'] += 1
                    if status == "PASS": stats['female_pass'] += 1
                    else: stats['female_fail'] += 1

                # Pass/Fail Overall
                if status == "PASS": stats['pass'] += 1
                else: stats['fail'] += 1

                # ... (तुमचा जुना रेकॉर्ड बनवण्याचा कोड) ...
                record = {
                    'seat_no': std['seat_no'], 'name': std['full_name'],
                    'gender': gender, 'internal': target_sub['internal'],
                    'external': target_sub['external'], 'total': target_sub['total'],
                    'grade': target_sub['grade'], 'status': status,
                    'marks_val': int(''.join(filter(str.isdigit, str(target_sub['total']))) or 0)
                }
                subject_data.append(record)

        # Top 3
        passed_students = [s for s in subject_data if s['status'] == "PASS"]
        passed_students.sort(key=lambda x: x['marks_val'], reverse=True)
        top_3 = passed_students[:3]

    return render_template('subject_analysis.html', unique_subjects=unique_subjects, 
                           selected_subject=selected_subject, subject_data=subject_data, 
                           stats=stats, top_3=top_3, filter_active=filter_active)
    
def calculate_stats(student_list):
    stats = {
        'total': len(student_list),
        'male_pass': 0, 'male_atkt': 0, 'male_fail': 0,
        'female_pass': 0, 'female_atkt': 0, 'female_fail': 0,
        'pass': 0, 'atkt': 0, 'fail': 0 # Overall for top cards if needed
    }
    
    for std in student_list:
        res = std['result'].upper()
        gender = std.get('gender', 'Male')
        
        if "PASS" in res:
            status = 'pass'
            stats['pass'] += 1
        elif "A.T.K.T" in res:
            status = 'atkt'
            stats['atkt'] += 1
        else:
            status = 'fail'
            stats['fail'] += 1
            
        # Gender-wise sub-counting
        key = f"{gender.lower()}_{status}"
        if key in stats:
            stats[key] += 1
            
    return stats

if __name__ == '__main__':
    app.run(debug=True)
    

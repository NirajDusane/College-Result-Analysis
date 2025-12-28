import pdfplumber
import re
import sys

def parse_gazette_block(block_text):
    student_data = {}

  # === 1. विद्यार्थी माहिती (Student Info) ===
    info_match = re.search(r"(\d{4,})\s+(.+?)\s+([MF])\s+(\d{10,})", block_text)
    if info_match:
        student_data['seat_no'] = info_match.group(1).strip()
        raw_name = info_match.group(2).strip()
        sex_char = info_match.group(3).strip() # M or F
        student_data['prn'] = info_match.group(4).strip()
        
        # Gender Save करणे (नवीन ओळ)
        student_data['gender'] = 'Male' if sex_char == 'M' else 'Female'

        name_parts = raw_name.split()
        if len(name_parts) > 1:
            student_data['mother_name'] = name_parts[-1]
            student_data['full_name'] = " ".join(name_parts[:-1])
        else:
            student_data['full_name'] = raw_name
            student_data['mother_name'] = "-"
    else:
        return None

    # === 2. विषय आणि मार्क्स (New Logic for Symbols) ===
    subjects = []
    
    # A) रेग्युलर विषय (Subject Codes)
    # 5 अंकी कोड शोधणे (उदा. 23121 :)
    # (?=...) हे पुढचा विषय किंवा GR येईपर्यंतचा टेक्स्ट घेते
    subject_regex = re.compile(r"(\d{5})\s*:\s*(.*?)(?=\s+\d{5}\s*:|\s+GR|$)")
    matches = subject_regex.finditer(block_text)
    
    for match in matches:
        code = match.group(1)
        raw_marks_text = match.group(2).strip()
        
        # मार्क्स टेक्स्टला स्पेसने तोडणे
        parts = raw_marks_text.split()
        
        # parts उदाहरणे:
        # ['10', '8', '*', '18', 'F', 'FF'] (Total 6 parts)
        # ['12', '14$', '26', 'A', '2'] (Total 5 parts)
        
        # शेवटचे दोन नेहमी Grade आणि Credits असतात
        if len(parts) >= 2:
            credits = parts[-1]
            grade = parts[-2]
            marks_part = parts[:-2] # फक्त मार्क्स (Int, Ext, Tot)
        else:
            continue # काहीतरी गडबड आहे, स्किप करा

        # मार्क्स प्रोसेस करणे (* आणि $ हँडल करण्यासाठी)
        processed_marks = []
        i = 0
        while i < len(marks_part):
            curr = marks_part[i]
            
            # जर '*' किंवा '$' किंवा 'AA' सुट्टा असेल आणि पुढे नंबर असेल
            if (curr == '*' or curr == '$') and (i + 1 < len(marks_part)):
                processed_marks.append(curr + " " + marks_part[i+1])
                i += 2
            # जर '*' नंबरला चिकटून असेल (उदा. *AA) तर तसेच ठेवा
            else:
                processed_marks.append(curr)
                i += 1
        
        # आता processed_marks मध्ये 3 व्हॅल्यू असाव्यात (Int, Ext, Tot)
        # जर कमी असतील तर '-' टाका
        internal = processed_marks[0] if len(processed_marks) > 0 else "-"
        external = processed_marks[1] if len(processed_marks) > 1 else "-"
        total = processed_marks[2] if len(processed_marks) > 2 else "-"

        subjects.append({
            "code": code,
            "internal": internal,
            "external": external,
            "total": total,
            "grade": grade,
            "credits": credits
        })

    # B) GR विषय (GR6-A :! O 3)
    # ! आणि : हँडल करण्यासाठी खास Regex
    gr_pattern = re.compile(r"(GR\d-[A-Z])\s*:\s*!?\s*([A-Z\+]+)\s+(\d+)")
    for match in gr_pattern.finditer(block_text):
        subjects.append({
            "code": match.group(1),
            "internal": "-", "external": "-", "total": "-",
            "grade": match.group(2).strip(),
            "credits": match.group(3).strip()
        })
    
    student_data['subjects'] = subjects

    # === 3. SGPA आणि Totals ===
    student_data['sgpa'] = {}
    sgpa_match = re.search(r"SGPA\s*:\s*(.*?)(?:TOTAL|CGPA|$)", block_text, re.DOTALL)
    if sgpa_match:
        sgpa_values = re.findall(r"\((\d)\)\s*([\d\.]+)", sgpa_match.group(1))
        for sem, score in sgpa_values:
            student_data['sgpa'][sem] = score

    # TOTAL 88 4 694
    student_data['total_credits'] = "-"
    student_data['total_marks'] = "-"
    total_match = re.search(r"TOTAL\s+(\d+)\s+\d+\s+(\d+)", block_text)
    if total_match:
        student_data['total_credits'] = total_match.group(1)
        student_data['total_marks'] = total_match.group(2)

    # F.Y.TOTAL
    student_data['fy_credits'] = "-"
    student_data['fy_marks'] = "-"
    fy_match = re.search(r"F\.Y\.TOTAL\s+(\d+)\s+\d+\s+(\d+)", block_text)
    if fy_match:
        student_data['fy_credits'] = fy_match.group(1)
        student_data['fy_marks'] = fy_match.group(2)

    # === 4. Result, CGPA आणि Extra Info ===
    student_data['cgpa'] = "-"
    student_data['final_grade'] = "-"
    student_data['result'] = "FAIL" # Default
    student_data['extra_notes'] = []

    # CGPA
    cgpa_match = re.search(r"CGPA\s*:\s*([\d\.]+)", block_text)
    if cgpa_match:
        student_data['cgpa'] = cgpa_match.group(1)
        student_data['result'] = "PASS"

    # Final Grade (उदा. A & O.163)
    # 'FINAL GRADE :' नंतरच्या ओळीच्या शेवटीपर्यंत सर्व घ्या
    grade_match = re.search(r"FINAL GRADE\s*:\s*(.*?)($|\n|The student)", block_text)
    if grade_match:
        student_data['final_grade'] = grade_match.group(1).strip()

    # Balance Marks / Mandatory Credits
    if "balance marks" in block_text:
        bal_match = re.search(r"(O\.\d+\s+balance marks\s*:\s*\d+)", block_text)
        if bal_match: student_data['extra_notes'].append(bal_match.group(1))

    if "completed mandetory" in block_text or "completed mandatory" in block_text:
        student_data['extra_notes'].append("The student has completed mandetory add-on credits for this programme.")

    # === 5. FAIL Logic (100% Accurate from PDF) ===
    # PDF मध्ये जसे आहे तसेच घ्यायचे आहे (FAIL A.T.K.T. vs FAIL)
    fail_match = re.search(r"(FAIL\s+A\.T\.K\.T\.|RESULT\s*:\s*FAIL|FAIL\s+\$\s+0\.1)", block_text, re.IGNORECASE)
    
    if fail_match:
        status_text = fail_match.group(1).upper()
        if "A.T.K.T" in status_text:
            student_data['result'] = "FAIL A.T.K.T."
        else:
            student_data['result'] = "FAIL"

    return student_data


def analyze_gazette_pattern(full_text):
    all_students_data = []
    # डॅश लाईन्स वापरून विद्यार्थी वेगळे करणे
    student_blocks = re.split(r'-{30,}', full_text) 
    
    for block in student_blocks:
        if block.strip() and "SEAT NO." not in block:
            student_info = parse_gazette_block(block)
            if student_info: 
                all_students_data.append(student_info)
    
    return {"student_data": all_students_data}

def main(pdf_path):
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # x_tolerance वाढवले आहे जेणेकरून गॅप्स नीट वाचले जातील
            all_text = "\n".join([p.extract_text(x_tolerance=3, y_tolerance=3) or "" for p in pdf.pages])
        
        result = analyze_gazette_pattern(all_text)
        return {"success": True, "student_data": result['student_data']} if result['student_data'] else {"success": False, "error": "No data found."}
    except Exception as e:
        return {"success": False, "error": str(e)}
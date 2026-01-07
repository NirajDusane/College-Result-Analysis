import pdfplumber
import re
import json
import os

def extract_subject_mapping(pdf):
    """पहिल्या विद्यार्थ्याचा डेटा मिळेपर्यंत सर्व पानांवरून विषय कोड आणि नावे गोळा करणे"""
    mapping = {}
    for page in pdf.pages:
        text = page.extract_text()
        if not text: continue
        student_start_pos = text.find("PRN:")
        mapping_area = text[:student_start_pos] if student_start_pos != -1 else text
        rows = re.findall(r"^([A-Z0-9-]{3,15})\s+([A-Za-z].*)", mapping_area, re.MULTILINE)
        for code_raw, name_raw in rows:
            code = code_raw.strip()
            name = re.sub(r'^[:\-\s!]+', '', name_raw).strip()
            if len(code) >= 3: mapping[code] = name
        if student_start_pos != -1: break
    return mapping

def parse_nep_block(block_text, subject_map):
    student_data = {}
    
    # 1. Student Basic Info
    prn_match = re.search(r"PRN:?\s*(\d+)", block_text)
    seat_match = re.search(r"SEAT NO\.:?\s*(\d+)", block_text)
    name_match = re.search(r"NAME:?\s*(.*?)(?=Mother|-|PRN|$)", block_text, re.DOTALL)
    mother_match = re.search(r"Mother\s*-?\s*(\w+)", block_text)
    
    if prn_match and seat_match:
        student_data['prn'] = prn_match.group(1).strip()
        student_data['seat_no'] = seat_match.group(1).strip()
        student_data['full_name'] = name_match.group(1).strip().split('\n')[0] if name_match else "Unknown"
        student_data['mother_name'] = mother_match.group(1).strip() if mother_match else "-"
        student_data['gender'] = "Male" if "SEX: M" in block_text or " M " in block_text else "Female"
    else:
        return None

    # 2. Semester-wise Subjects
    student_data['sem1_subjects'] = []
    student_data['sem2_subjects'] = []
    all_grades = []
    sem_parts = re.split(r'Semester\s*:\s*', block_text, flags=re.IGNORECASE)
    
    for sem_idx, part in enumerate(sem_parts[1:], 1):
        lines = part.split('\n')
        for line in lines:
            parts = line.split()
            if len(parts) >= 8:
                code_raw = parts[0].strip().replace(':', '')
                code_clean = re.sub(r'[^A-Z0-9-]', '', code_raw)
                if len(code_clean) >= 3:
                    try:
                        grade = parts[-3]
                        all_grades.append(grade)
                        record = {
                            "code": code_clean, "name": subject_map.get(code_clean, "---"),
                            "p_int": "-", "int_m": "-", "p_ext": "-", "ext_m": "-", "p_pr": "-", "pr_m": "-",
                            "total": parts[-6], "crd": parts[-5], "ern": parts[-4], "grd": grade, "gp": parts[-2], "cp": parts[-1]
                        }
                        marks_area = parts[1:-6]
                        processed = []
                        j = 0
                        while j < len(marks_area):
                            curr = marks_area[j]
                            if curr in ['P', '*', 'AA'] and j+1 < len(marks_area):
                                processed.append(curr + " " + marks_area[j+1]); j += 2
                            else: processed.append(curr); j += 1
                        
                        if len(processed) >= 1:
                            m1 = processed[0].split()
                            record["p_int"] = m1[0] if len(m1)>1 else "-"; record["int_m"] = m1[-1]
                        if len(processed) >= 2:
                            m2 = processed[1].split()
                            record["p_ext"] = m2[0] if len(m2)>1 else "-"; record["ext_m"] = m2[-1]
                        if len(processed) >= 3:
                            m3 = processed[2].split()
                            record["p_pr"] = m3[0] if len(m3)>1 else "-"; record["pr_m"] = m3[-1]

                        if sem_idx == 1: student_data['sem1_subjects'].append(record)
                        else: student_data['sem2_subjects'].append(record)
                    except: continue

    # 3. Dynamic Summary Extraction
    s1_sum_match = re.search(r"(First Semester SGPA\s*:\s*.*?)(?=\n|Second Semester|$)", block_text, re.DOTALL)
    s2_sum_match = re.search(r"(Second Semester SGPA\s*:\s*.*?)(?=\n|First Year|$)", block_text, re.DOTALL)
    student_data['sem1_summary'] = s1_sum_match.group(1).replace('\n', ' ').strip() if s1_sum_match else ""
    student_data['sem2_summary'] = s2_sum_match.group(1).replace('\n', ' ').strip() if s2_sum_match else ""

    # 4. Accurate Result Logic (Fix for 44/44 Credits)
    # पीडीएफ मधून निकालाची ओळ शोधा (उदा. FAIL A.T.K.T. किंवा Result: PASS)
    fy_res_match = re.search(r"(First Year (?:Result|Total Credits Earned)\s*:\s*.*?)(?=\n|$)", block_text)
    fy_text = fy_res_match.group(1).upper() if fy_res_match else ""
    student_data['fy_total_msg'] = fy_text

    # १. जर ग्रेड्समध्ये कोठेही 'F' किंवा 'FFF' असेल तर नापास
    fail_exists = any(g in ['F', 'FFF', 'FAIL'] for g in all_grades)
    
    # २. जर ४४ पैकी ४४ क्रेडिट्स मिळाले असतील किंवा ग्रेड्समध्ये 'F' नसेल तर PASS
    if "44/44" in fy_text or (not fail_exists and len(all_grades) > 0):
        student_data['result'] = "PASS"
    elif "A.T.K.T" in fy_text:
        student_data['result'] = "FAIL A.T.K.T."
    else:
        student_data['result'] = "FAIL"

    student_data['cgpa'] = "-"
    student_data['final_grade'] = "-"
    tcp = re.search(r"Total Credit Points:\s*([\d\.]+)", block_text)
    student_data['total_marks'] = tcp.group(1) if tcp else "-"

    return student_data

def main(pdf_path):
    try:
        all_students = []
        with pdfplumber.open(pdf_path) as pdf:
            subject_map = extract_subject_mapping(pdf)
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=1.5)
                if not text: continue
                blocks = re.split(r'(?=PRN[:\s])', text)
                for b in blocks:
                    if "SEMESTER" in b.upper():
                        res = parse_nep_block(b, subject_map)
                        if res: all_students.append(res)
        return {"success": True, "student_data": all_students}
    except Exception as e:
        return {"success": False, "error": str(e)}
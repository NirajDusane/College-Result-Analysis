import pdfplumber
import re
import json

def extract_subject_mapping(pdf):
    """
    Reads the first few pages to create a dictionary of Subject Code -> Subject Name.
    """
    mapping = {}
    pages_to_scan = min(5, len(pdf.pages))
    
    for i in range(pages_to_scan):
        text = pdf.pages[i].extract_text()
        if not text: continue
        
        lines = text.split('\n')
        capture = False
        for line in lines:
            if "Paper List" in line:
                capture = True
                continue
            if "Semester:" in line:
                continue
            if "PRN:" in line:
                capture = False
                break
            
            if capture:
                match = re.match(r"^\s*([A-Z0-9-]{3,10})\s+(.+)$", line.strip())
                if match:
                    code, name = match.groups()
                    clean_name = re.sub(r'[:\-\s!]+$', '', name.strip())
                    mapping[code.strip()] = clean_name
    return mapping

def split_prefix_marks(val):
    val = val.replace("FFF", "").replace("$", "").replace("#", "").strip()
    if val in ['---', '-', 'AB', 'AA', 'AAA']: return "-", "-"
    if " " in val: return val.split()[0], val.split()[1]
    if val and not val[0].isdigit(): return val[0], val[1:]
    return "", val

def parse_marks_row(line, subject_map):
    if "CODE" in line.upper() or "NAME:" in line.upper() or "PRN:" in line.upper(): return None
    parts = line.split()
    if len(parts) < 6: return None

    valid_grades = ['O', 'A+', 'A', 'B+', 'B', 'C', 'D', 'F', 'P', 'AB', 'FAIL']
    grade_idx = -1
    grade_val = "-"

    for i in range(1, 7):
        if i >= len(parts): break
        if parts[-i] in valid_grades:
            grade_idx = len(parts) - i
            grade_val = parts[-i]
            break
            
    if grade_idx == -1: return None

    try:
        ern = parts[grade_idx - 1]
        crd = parts[grade_idx - 2]
        p1 = parts[grade_idx - 3]
        p2 = parts[grade_idx - 4]
        
        if p1 in ['FFF', 'FAIL', 'AB', 'AA', '$', '#']:
            total = p2
            marks_end_idx = grade_idx - 4
        elif 'FFF' in p1:
            total = p1.replace('FFF', '')
            marks_end_idx = grade_idx - 3
        else:
            total = p1
            marks_end_idx = grade_idx - 3

        gp = parts[grade_idx + 1] if (grade_idx + 1) < len(parts) else "0"
        cp = parts[grade_idx + 2] if (grade_idx + 2) < len(parts) else "0"

        code = parts[0].replace(':', '').strip()
        name = subject_map.get(code, "Subject Name Not Found")

        marks_tokens = parts[1 : marks_end_idx]
        cleaned_columns = []
        i = 0
        while i < len(marks_tokens):
            t = marks_tokens[i]
            if t in ['---', 'AAA', 'AA']:
                cleaned_columns.append(t)
            elif t in ['P', '*', '~', '#', '$', '@'] and (i+1 < len(marks_tokens)):
                cleaned_columns.append(f"{t} {marks_tokens[i+1]}")
                i += 1
            else:
                cleaned_columns.append(t)
            i += 1
            
        while len(cleaned_columns) < 3: cleaned_columns.append("---")
        
        p_int, int_m = split_prefix_marks(cleaned_columns[0])
        p_ext, ext_m = split_prefix_marks(cleaned_columns[1])
        p_pr,  pr_m  = split_prefix_marks(cleaned_columns[2])

        return {
            "code": code, "name": name,
            "p_int": p_int, "int_m": int_m,
            "p_ext": p_ext, "ext_m": ext_m,
            "p_pr": p_pr,   "pr_m": pr_m,
            "total": total, "crd": crd, "ern": ern,
            "grd": grade_val, "gp": gp, "cp": cp
        }
    except: return None

def main(pdf_path):
    all_students = []
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            subject_map = extract_subject_mapping(pdf)
            full_text = "\n".join([page.extract_text(x_tolerance=2) or "" for page in pdf.pages])
            student_blocks = re.split(r'(?=PRN:\s*\d+)', full_text)
            
            for block in student_blocks:
                if "SEMESTER" not in block: continue
                
                student = {
                    'sem1_subjects': [], 'sem2_subjects': [],
                    'sem3_subjects': [], 'sem4_subjects': [],
                    'sem1_summary': '', 'sem2_summary': '',
                    'sem3_summary': '', 'sem4_summary': '',
                    'sem3_sgpa': None, 'sem4_sgpa': None, # New fields for SGPA
                    'full_name': 'Unknown', 'seat_no': '-', 'prn': '-', 'mother_name': '-',
                    'result': None, 'fy_total_msg': '', 'total_marks': '-' # Used for dashboard display
                }
                
                # Basic Details
                prn_m = re.search(r"PRN:\s*(\d+)", block)
                seat_m = re.search(r"SEAT NO\.:\s*(\d+)", block)
                name_m = re.search(r"NAME:\s*(.*?)(?=\s+Mother|\s+PRN|$)", block)
                mother_m = re.search(r"Mother\s*-\s*(\w+)", block)
                
                if prn_m: student['prn'] = prn_m.group(1)
                if seat_m: student['seat_no'] = seat_m.group(1)
                if name_m: student['full_name'] = name_m.group(1).strip()
                if mother_m: student['mother_name'] = mother_m.group(1)
                
                # Result
                res_match = re.search(r"Second Year Result\s*:\s*(.*?)(?=\s+Total|\n)", block, re.IGNORECASE)
                if res_match:
                    student['result'] = res_match.group(1).strip().upper()
                
                # Credits
                cred_match = re.search(r"(Total Credits Earned\s*:\s*[\d\/]+)", block)
                if cred_match:
                    student['fy_total_msg'] = cred_match.group(1)

                # Process Semesters
                sem_parts = re.split(r'(SEMESTER:\s*\d)', block)
                current_sem = None
                
                for part in sem_parts:
                    header_match = re.match(r"SEMESTER:\s*(\d)", part.strip())
                    if header_match:
                        current_sem = header_match.group(1)
                        continue
                    
                    if current_sem:
                        lines = part.split('\n')
                        for line in lines:
                            row = parse_marks_row(line, subject_map)
                            if row:
                                student[f'sem{current_sem}_subjects'].append(row)
                            
                            # Extract SGPA from Summary Line
                            if "SGPA" in line:
                                student[f'sem{current_sem}_summary'] = re.sub(r'Page\s*\d+', '', line).strip()
                                # Regex to find SGPA (e.g. "SGPA : 9.27")
                                sgpa_match = re.search(r"SGPA\s*:\s*(\d+\.?\d*)", line)
                                if sgpa_match:
                                    student[f'sem{current_sem}_sgpa'] = sgpa_match.group(1)

                # === 🛠️ AUTO RESULT LOGIC 🛠️ ===
                if student['result'] is None:
                    all_grades = []
                    for sem in ['sem3', 'sem4']:
                        all_grades.extend([s['grd'] for s in student[f'{sem}_subjects']])
                    if any(g in ['F', 'FFF', 'FAIL', 'AB', 'Absent'] for g in all_grades):
                        student['result'] = 'FAIL'
                    else:
                        student['result'] = 'PASS'

                # === ✨ SHOW SGPA FOR PASS STUDENTS ✨ ===
                # If Passed, show Sem 4 SGPA. If Fail, show "-"
                if "PASS" in student['result']:
                    if student['sem4_sgpa']:
                        student['total_marks'] = student['sem4_sgpa'] # This will show in "Total Pts" col
                    elif student['sem3_sgpa']:
                        student['total_marks'] = student['sem3_sgpa']
                    else:
                        student['total_marks'] = "-"
                else:
                    # For Fail/ATKT, keep it blank or you can set to "-"
                    student['total_marks'] = "-"

                if student['prn'] != '-':
                    all_students.append(student)
                    
        return {"success": True, "data": all_students}

    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    res = main("Result_Ledger.pdf")
    print(f"Extracted {len(res.get('data', []))} students")
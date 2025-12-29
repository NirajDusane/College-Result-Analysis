import pdfplumber
import re
import json
import os

def extract_subject_mapping(pdf):
    """
    Extract subject codes and subject names from all pages
    until the first student's data (PRN) is encountered.
    """
    mapping = {}
    
    for page in pdf.pages:
        text = page.extract_text()
        if not text:
            continue
        
        # Check if student data starts on this page
        student_start_pos = text.find("PRN:")
        
        # Use only text before PRN for subject mapping (dynamic stop)
        mapping_area = text[:student_start_pos] if student_start_pos != -1 else text
        
        # Regex: Subject Code (3–15 alphanumeric chars) + space + Subject Name
        rows = re.findall(
            r"^([A-Z0-9-]{3,15})\s+([A-Za-z].*)",
            mapping_area,
            re.MULTILINE
        )
        
        for code_raw, name_raw in rows:
            code = code_raw.strip()
            
            # Remove unwanted characters at the start of subject name
            name = re.sub(r'^[:\-\s!]+', '', name_raw).strip()
            
            if len(code) >= 3:
                mapping[code] = name
        
        # Stop once PRN is found (subject list completed)
        if student_start_pos != -1:
            break
            
    return mapping


def parse_nep_block(block_text, subject_map):
    """
    Parse a single student's result block under NEP pattern
    and return structured student data.
    """
    student_data = {}
    
    # 1. Student Basic Information Extraction
    prn_match = re.search(r"PRN:?\s*(\d+)", block_text)
    seat_match = re.search(r"SEAT NO\.:?\s*(\d+)", block_text)
    name_match = re.search(
        r"NAME:?\s*(.*?)(?=Mother|-|PRN|$)",
        block_text,
        re.DOTALL
    )
    mother_match = re.search(r"Mother\s*-?\s*(\w+)", block_text)
    
    # Mandatory fields check
    if prn_match and seat_match:
        student_data['prn'] = prn_match.group(1).strip()
        student_data['seat_no'] = seat_match.group(1).strip()
        student_data['full_name'] = (
            name_match.group(1).strip().split('\n')[0]
            if name_match else "Unknown"
        )
        student_data['mother_name'] = (
            mother_match.group(1).strip() if mother_match else "-"
        )
        
        # Gender detection
        student_data['gender'] = (
            "Male" if "SEX: M" in block_text or " M " in block_text else "Female"
        )
    else:
        return None

    # 2. Semester-wise Subject Extraction
    student_data['sem1_subjects'] = []
    student_data['sem2_subjects'] = []
    all_grades = []

    # Split data semester-wise
    sem_parts = re.split(
        r'Semester\s*:\s*',
        block_text,
        flags=re.IGNORECASE
    )
    
    for sem_idx, part in enumerate(sem_parts[1:], 1):
        lines = part.split('\n')
        
        for line in lines:
            parts = line.split()
            
            # Minimum columns required for a valid subject row
            if len(parts) >= 8:
                code_raw = parts[0].strip().replace(':', '')
                code_clean = re.sub(r'[^A-Z0-9-]', '', code_raw)
                
                if len(code_clean) >= 3:
                    try:
                        # Last 5 fields are fixed: CRD, ERN, GRD, GP, CP
                        grade = parts[-3]
                        all_grades.append(grade)
                        
                        record = {
                            "code": code_clean,
                            "name": subject_map.get(code_clean, "---"),
                            "p_int": "-", "int_m": "-",
                            "p_ext": "-", "ext_m": "-",
                            "p_pr": "-", "pr_m": "-",
                            "total": parts[-6],
                            "crd": parts[-5],
                            "ern": parts[-4],
                            "grd": grade,
                            "gp": parts[-2],
                            "cp": parts[-1]
                        }

                        # Extract marks section (between subject code and total)
                        marks_area = parts[1:-6]
                        processed_groups = []
                        j = 0
                        
                        # Combine P/*/AA with their marks
                        while j < len(marks_area):
                            curr = marks_area[j]
                            if curr in ['P', '*', 'AA'] and j + 1 < len(marks_area):
                                processed_groups.append(
                                    curr + " " + marks_area[j + 1]
                                )
                                j += 2
                            else:
                                processed_groups.append(curr)
                                j += 1
                        
                        # Mapping marks: Internal, External, Practical
                        if len(processed_groups) >= 1:
                            m1 = processed_groups[0].split()
                            record["p_int"] = m1[0] if len(m1) > 1 else "-"
                            record["int_m"] = (
                                m1[-1] if m1[-1] != "---" else "-"
                            )
                        
                        if len(processed_groups) >= 2:
                            m2 = processed_groups[1].split()
                            record["p_ext"] = m2[0] if len(m2) > 1 else "-"
                            record["ext_m"] = (
                                m2[-1] if m2[-1] != "---" else "-"
                            )
                        
                        if len(processed_groups) >= 3:
                            m3 = processed_groups[2].split()
                            record["p_pr"] = m3[0] if len(m3) > 1 else "-"
                            record["pr_m"] = (
                                m3[-1] if m3[-1] != "---" else "-"
                            )

                        # Append subject to correct semester
                        if sem_idx == 1:
                            student_data['sem1_subjects'].append(record)
                        else:
                            student_data['sem2_subjects'].append(record)
                    
                    except:
                        continue

    # 3. Summary & Final Result Logic
    s1_m = re.search(
        r"First Semester SGPA\s*:\s*([\d\.]+)",
        block_text
    )
    s2_m = re.search(
        r"Second Semester SGPA\s*:\s*([\d\.]+)",
        block_text
    )
    
    student_data['sem1_summary'] = (
        f"First Semester SGPA : {s1_m.group(1)}" if s1_m else ""
    )
    student_data['sem2_summary'] = (
        f"Second Semester SGPA : {s2_m.group(1)}" if s2_m else ""
    )

    # First Year credit summary
    fy_m = re.search(
        r"(First Year Total Credits Earned\s*:\s*.*?)(\n|$)",
        block_text
    )
    student_data['fy_total_msg'] = fy_m.group(1).strip() if fy_m else ""

    # Result calculation based on grades
    fail_exists = any(
        g in ['F', 'FFF', 'FAIL', 'A.T.K.T', 'FAIL A.T.K.T']
        for g in all_grades
    )
    
    student_data['result'] = (
        "PASS" if not fail_exists and len(all_grades) > 0 else "FAIL"
    )

    # Final values
    student_data['cgpa'] = "-"
    student_data['final_grade'] = "-"
    
    tcp = re.search(
        r"Total Credit Points:\s*([\d\.]+)",
        block_text
    )
    student_data['total_marks'] = tcp.group(1) if tcp else "-"

    return student_data


def main(pdf_path):
    """
    Main controller function:
    - Reads PDF
    - Extracts subject mapping
    - Parses each student block
    """
    try:
        all_students = []
        
        with pdfplumber.open(pdf_path) as pdf:
            subject_map = extract_subject_mapping(pdf)
            
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=1.5)
                if not text:
                    continue
                
                # Split text into student blocks using PRN
                blocks = re.split(r'(?=PRN[:\s])', text)
                
                for b in blocks:
                    if "SEMESTER" in b.upper():
                        res = parse_nep_block(b, subject_map)
                        if res:
                            all_students.append(res)
        
        return {
            "success": True,
            "student_data": all_students
        }
    
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

import pdfplumber
import re
import json
import os


def extract_header_metadata(pdf):
    """
    Extracts metadata based on the SPPU College Ledger format (2024 Pattern).
    """
    metadata = {
        "pun_code": "Unknown",
        "course_name": "Unknown",
        "college_name": "Unknown"
    }
    try:
        first_page_text = pdf.pages[0].extract_text()
        print("\n--- [DEBUG: UPDATED EXTRACTION START] ---")
        
        if not first_page_text:
            return metadata

        # 1. PUN Code Extraction (Already working, but refined)
        pun_match = re.search(r"Puncode\s*:\s*([A-Z]{4}\d{6,10})", first_page_text, re.IGNORECASE)
        if pun_match:
            metadata["pun_code"] = pun_match.group(1).strip()
            print(f"[SUCCESS] PUN Code: {metadata['pun_code']}")

        # 2. Course Name Extraction
        # Captures text between the university address/year and the "College Ledger" line
        # Example: BACHELOR OF SCIENCE(2024 Pattern (NEP 2020))
        course_match = re.search(r"PUNE-\d{3}\s*\d{3}\s*\n(.*?)\nCollege Ledger", first_page_text, re.DOTALL)
        if course_match:
            metadata["course_name"] = course_match.group(1).strip()
            print(f"[SUCCESS] Course Name: {metadata['course_name']}")
        else:
            # Fallback: Look for "BACHELOR OF..." directly
            course_fallback = re.search(r"(BACHELOR|MASTER)\s+OF\s+.*?(?=\n)", first_page_text, re.IGNORECASE)
            if course_fallback:
                metadata["course_name"] = course_fallback.group(0).strip()
                print(f"[SUCCESS] Course (Fallback): {metadata['course_name']}")

        # 3. College Name Extraction
        # Captures the text after the Puncode and bracketed code [0105]
        # Example: [0105]LOKNETE VYANKATRAO HIRAY...
        college_match = re.search(r"\[\d{4}\]\s*(.*?)(?=\n|\[)", first_page_text)
        if college_match:
            metadata["college_name"] = college_match.group(1).strip()
            print(f"[SUCCESS] College Name: {metadata['college_name']}")
        else:
            print("[FAIL] Could not isolate College Name from the Puncode line.")
            
        print("--- [DEBUG: UPDATED EXTRACTION END] ---\n")

    except Exception as e:
        print(f"[ERROR] Metadata extraction error: {e}")
    
    return metadata


# ---------------------------------------------------
# SUBJECT MAPPING EXTRACTION
# ---------------------------------------------------

def extract_subject_mapping(pdf):
    """
    Scans the PDF pages to build a dictionary mapping Subject Codes to Subject Names.
    This scan stops once the first student record (identified by 'PRN:') is encountered.
    """
    mapping = {}
    try:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            
            # Identify the start of student records to isolate the mapping area
            student_start_pos = text.find("PRN:")
            mapping_area = text[:student_start_pos] if student_start_pos != -1 else text
            
            # Regular expression to extract alphanumeric subject codes and their corresponding names
            rows = re.findall(r"^([A-Z0-9-]{3,15})\s+([A-Za-z].*)", mapping_area, re.MULTILINE)
            for code_raw, name_raw in rows:
                code = code_raw.strip()
                # Clean subject names by removing leading symbols or colons
                name = re.sub(r'^[:\-\s!]+', '', name_raw).strip()
                if len(code) >= 3:
                    mapping[code] = name
            
            # Terminate scanning once student data section is reached
            if student_start_pos != -1:
                break
    except Exception as e:
        # Log mapping extraction errors
        print(f"Error in extract_subject_mapping: {e}")
    
    return mapping

# ---------------------------------------------------
# NEP STUDENT BLOCK PARSER
# ---------------------------------------------------

def parse_nep_block(block_text, subject_map):
    """
    Parses an individual text block containing a single student's academic record.
    Extracts profile details, marks for multiple semesters, and determines final results.
    """
    student_data = {}
    
    try:
        # --- Extraction of Basic Student Profile ---
        prn_match = re.search(r"PRN:?\s*(\d+)", block_text)
        seat_match = re.search(r"SEAT NO\.:?\s*(\d+)", block_text)
        name_match = re.search(r"NAME:?\s*(.*?)(?=Mother|-|PRN|$)", block_text, re.DOTALL)
        mother_match = re.search(r"Mother\s*-?\s*(\w+)", block_text)
        
        if prn_match and seat_match:
            student_data['prn'] = prn_match.group(1).strip()
            student_data['seat_no'] = seat_match.group(1).strip()
            student_data['full_name'] = name_match.group(1).strip().split('\n')[0] if name_match else "Unknown"
            student_data['mother_name'] = mother_match.group(1).strip() if mother_match else "-"
            # Identify gender based on standard markers
            student_data['gender'] = "Male" if "SEX: M" in block_text or " M " in block_text else "Unknown"
        else:
            return None

        # --- Extraction of Semester-wise Subject Data ---
        student_data['sem1_subjects'] = []
        student_data['sem2_subjects'] = []
        all_grades = []
        
        # Split text into sections based on the 'Semester' keyword
        sem_parts = re.split(r'Semester\s*:\s*', block_text, flags=re.IGNORECASE)
        
        for sem_idx, part in enumerate(sem_parts[1:], 1):
            lines = part.split('\n')
            for line in lines:
                parts = line.split()
                # Determine if the line represents a valid subject record (minimum 8 components)
                if len(parts) >= 8:
                    try:
                        code_raw = parts[0].strip().replace(':', '')
                        code_clean = re.sub(r'[^A-Z0-9-]', '', code_raw)
                        
                        if len(code_clean) >= 3:
                            grade = parts[-3]
                            all_grades.append(grade)
                            
                            record = {
                                "code": code_clean, 
                                "name": subject_map.get(code_clean, "---"),
                                "p_int": "-", "int_m": "-", 
                                "p_ext": "-", "ext_m": "-", 
                                "p_pr": "-", "pr_m": "-",
                                "total": parts[-6], "crd": parts[-5], 
                                "ern": parts[-4], "grd": grade, 
                                "gp": parts[-2], "cp": parts[-1]
                            }
                            
                            # Parse marks section containing Internal, External, and Practical scores
                            marks_area = parts[1:-6]
                            processed = []
                            j = 0
                            while j < len(marks_area):
                                curr = marks_area[j]
                                # Handle prefixed score markers like 'P', '*', or 'AA'
                                if curr in ['P', '*', 'AA'] and j+1 < len(marks_area):
                                    processed.append(curr + " " + marks_area[j+1])
                                    j += 2
                                else: 
                                    processed.append(curr)
                                    j += 1
                            
                            # Assign processed marks to corresponding categories
                            if len(processed) >= 1:
                                m1 = processed[0].split()
                                record["p_int"] = m1[0] if len(m1) > 1 else "-"
                                record["int_m"] = m1[-1]
                            if len(processed) >= 2:
                                m2 = processed[1].split()
                                record["p_ext"] = m2[0] if len(m2) > 1 else "-"
                                record["ext_m"] = m2[-1]
                            if len(processed) >= 3:
                                m3 = processed[2].split()
                                record["p_pr"] = m3[0] if len(m3) > 1 else "-"
                                record["pr_m"] = m3[-1]

                            if sem_idx == 1:
                                student_data['sem1_subjects'].append(record)
                            else:
                                student_data['sem2_subjects'].append(record)
                    except (IndexError, ValueError):
                        # Skip malformed subject lines without breaking the flow
                        continue

        # --- Summary and SGPA Extraction ---
        s1_sum_match = re.search(r"(First Semester SGPA\s*:\s*.*?)(?=\n|Second Semester|$)", block_text, re.DOTALL)
        s2_sum_match = re.search(r"(Second Semester SGPA\s*:\s*.*?)(?=\n|First Year|$)", block_text, re.DOTALL)
        
        student_data['sem1_summary'] = s1_sum_match.group(1).replace('\n', ' ').strip() if s1_sum_match else ""
        student_data['sem2_summary'] = s2_sum_match.group(1).replace('\n', ' ').strip() if s2_sum_match else ""
        
        # Determine Dashboard SGPA (Prefers Semester 2 data)
        s1_val = re.search(r"First Semester SGPA\s*:\s*([\d\.]+)", block_text)
        s2_val = re.search(r"Second Semester SGPA\s*:\s*([\d\.]+)", block_text)
        
        current_sgpa = "-"
        if s2_val:
            current_sgpa = s2_val.group(1)
        elif s1_val:
            current_sgpa = s1_val.group(1)
        
        student_data['dashboard_sgpa'] = current_sgpa

        # --- Final Result Determination Logic ---
        fy_res_match = re.search(r"(First Year (?:Result|Total Credits Earned)\s*:\s*.*?)(?=\n|$)", block_text)
        fy_text = fy_res_match.group(1).upper() if fy_res_match else ""
        student_data['fy_total_msg'] = fy_text

        # Detect any 'Fail' grades in the entire record
        fail_exists = any(g in ['F', 'FFF', 'FAIL'] for g in all_grades)
        
        # Logic to determine PASS status based on total credits or absence of Fail grades
        if "44/44" in fy_text or (not fail_exists and len(all_grades) > 0):
            student_data['result'] = "PASS"
        elif "A.T.K.T" in fy_text:
            student_data['result'] = "FAIL A.T.K.T."
        else:
            student_data['result'] = "FAIL"

        student_data['cgpa'] = "-"
        student_data['final_grade'] = "-"
        
        tcp_match = re.search(r"Total Credit Points:\s*([\d\.]+)", block_text)
        student_data['total_marks'] = tcp_match.group(1) if tcp_match else "-"

        return student_data

    except Exception as e:
        # Handle unexpected parsing failures for a specific block
        print(f"Critical error parsing NEP student block: {e}")
        return None

# ---------------------------------------------------
# MAIN PARSER ENTRY POINT
# ---------------------------------------------------

def main(pdf_path):
    """
    Entry point for parsing University NEP Result Ledger PDFs.
    Iterates through the document and returns a structured dictionary of student data.
    """
    try:
        all_students = []
        metadata = {}
        with pdfplumber.open(pdf_path) as pdf:
            # Build initial subject reference from the PDF content
            subject_map = extract_subject_mapping(pdf)
            metadata = extract_header_metadata(pdf)
            print(f"[PARSER SUMMARY] College: {metadata['college_name']} | Course: {metadata['course_name']}")
            
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=1.5)
                if not text:
                    continue
                
                # Split the page text into individual student blocks
                blocks = re.split(r'(?=PRN[:\s])', text)
                for b in blocks:
                    # Filter for blocks that actually contain academic results
                    if "SEMESTER" in b.upper():
                        res = parse_nep_block(b, subject_map)
                        if res:
                            res['course_name'] = metadata['course_name']
                            all_students.append(res)
        
        # Structure the return value based on parsing outcome
        if all_students:
            return {"success": True, "college_info": metadata, "student_data": all_students}
        else:
            return {"success": False, "error": "No valid NEP student records found."}

    except Exception as e:
        # Catch and return global parser failures
        return {"success": False, "error": f"NEP Parser Global Error: {str(e)}"}
    
    
    
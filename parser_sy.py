import pdfplumber
import re
import json

# ---------------------------------------------------
# METADATA EXTRACTION (NEWLY ADDED)
# ---------------------------------------------------


def extract_header_metadata(pdf):
    """
    Primary metadata extractor focused on capturing the full department name.
    Now supports multi-line course names and nested parentheses.
    """
    metadata = {
        "pun_code": "Unknown",
        "course_name": "Unknown",
        "college_name": "Unknown"
    }
    try:
        header_text = ""
        for i in range(min(2, len(pdf.pages))):
            header_text += pdf.pages[i].extract_text(x_tolerance=2) or ""
            
        if not header_text:
            return metadata

        # 1. PUN Code Extraction
        pun_match = re.search(r"Puncode\s*:\s*([A-Z]{4}\d{6,10})", header_text, re.IGNORECASE)
        if pun_match:
            metadata["pun_code"] = pun_match.group(1).strip()

        # 2. Course Name Extraction: UPDATED REGEX
        # [\s\S]*? मुळे नवीन ओळीवरील (COMPUTER SCIENCE) सारखा मजकूर सुद्धा कॅप्चर होतो.
        # हा पॅटर्न फक्त (REV. 2019) किंवा Pattern शब्दाजवळ थांबतो.
        course_match = re.search(
            r"((?:BACHELOR|MASTER)\s+OF\s+[\s\S]*?)(?=\s*\((?:REV|20\d{2})|\s*\(?\d{4}\s*Pattern|College Ledger|\n\n|$)", 
            header_text, 
            re.IGNORECASE
        )
        if course_match:
            # मजकूरातील नवीन ओळी (newlines) काढून एक सलग नाव तयार करणे
            metadata["course_name"] = re.sub(r'\s+', ' ', course_match.group(1)).strip()

        # 3. College Name Extraction
        college_match = re.search(r"Puncode\s*:.*?\]\s*(.*?)(?=\n|$)", header_text, re.IGNORECASE)
        if college_match:
            # शेवटी येणारा स्वल्पविराम आणि जास्तीची जागा काढून टाकणे
            metadata["college_name"] = college_match.group(1).strip().rstrip(',')
        
        if metadata["college_name"] == "Unknown" or not metadata["college_name"]:
            fallback = re.search(r"\[\d{4}\]\s*([A-Z][A-Z\s,]+(?:COLLEGE|INSTITUTE|ARTS|SCIENCE|COMMERCE).*?)(?=\n|$)", header_text)
            if fallback:
                metadata["college_name"] = fallback.group(1).strip().rstrip(',')

    except Exception as e:
        print(f"Metadata extraction error: {e}")
    
    return metadata

# ---------------------------------------------------
# SUBJECT MAPPING EXTRACTION
# ---------------------------------------------------

def extract_subject_mapping(pdf):
    """
    Scans the beginning of the PDF to build a dictionary of Subject Codes and Names.
    This typically looks for the 'Paper List' section located before student data.
    """
    mapping = {}
    metadata_backup = {"pun_code": None, "course_name": None, "college_name": None}
    try:
        # Scan only the first few pages to optimize performance
        pages_to_scan = min(5, len(pdf.pages))
        
        for i in range(pages_to_scan):
            text = pdf.pages[i].extract_text()
            if not text:
                continue
            
            lines = text.split('\n')
            capture = False
            
            for line in lines:
                # --- BACKUP METADATA SCANNING ---
                # 1. Look for Puncode & College
                if "Puncode" in line:
                    pun_m = re.search(r"Puncode\s*:\s*([A-Z]{4}\d+)", line, re.IGNORECASE)
                    if pun_m: metadata_backup["pun_code"] = pun_m.group(1).strip()
                    coll_m = re.search(r"\]\s*(.*?)(?=\n|$)", line)
                    if coll_m: metadata_backup["college_name"] = coll_m.group(1).strip().rstrip(',')

                if "BACHELOR" in line.upper() or "MASTER" in line.upper():
                    # बॅकअप स्कॅनिंगमध्ये सुद्धा पूर्ण नावासाठी अपडेटेड पॅटर्न
                    course_m = re.search(
                        r"((?:BACHELOR|MASTER)\s+OF\s+.*?)(?=\s*\((?:REV|20\d{2})|\s*Pattern|\n|$)", 
                        line, 
                        re.IGNORECASE
                    )
                    if course_m: metadata_backup["course_name"] = course_m.group(1).strip()
                    
                # Begin capturing when the 'Paper List' header is identified
                if "Paper List" in line:
                    capture = True
                    continue
                
                # Skip secondary headers
                if "Semester:" in line:
                    continue
                
                # Terminate mapping extraction when student records begin
                if "PRN:" in line:
                    capture = False
                    break
                
                if capture:
                    # Extracts alphanumeric code (3-10 chars) and the subsequent name
                    match = re.match(r"^\s*([A-Z0-9-]{3,10})\s+(.+)$", line.strip())
                    if match:
                        code, name = match.groups()
                        # Clean special characters from the end of the subject name
                        clean_name = re.sub(r'[:\-\s!]+$', '', name.strip())
                        mapping[code.strip()] = clean_name
    except Exception as e:
        # Controlled error logging for subject mapping failures
        print(f"Error in extract_subject_mapping: {e}")
        
    return mapping,metadata_backup

# ---------------------------------------------------
# MARK VALUE CLEANING UTILITY
# ---------------------------------------------------

def split_prefix_marks(val):
    """
    Separates academic symbols (like *, $, #) from the actual numeric mark value.
    Returns a tuple consisting of (prefix, mark_value).
    """
    try:
        # Standardize result symbols and remove noise
        val = val.replace("FFF", "").replace("$", "").replace("#", "").strip()
        
        # Handle non-numeric or absent markers
        if val in ['---', '-', 'AB', 'AA', 'AAA']: 
            return "-", "-"
        
        # Handle space-separated prefix characters
        if " " in val: 
            return val.split()[0], val.split()[1]
        
        # Handle cases where the prefix is prepended directly to the value
        if val and not val[0].isdigit(): 
            return val[0], val[1:]
    except Exception:
        # Fallback to empty prefix if processing fails
        pass
    return "", val

# ---------------------------------------------------
# INDIVIDUAL MARKS ROW PARSER
# ---------------------------------------------------

def parse_marks_row(line, subject_map):
    """
    Parses a text line representing a single subject's performance record.
    Extracts structured data for internal, external, practical marks, grades, and points.
    """
    try:
        # Ignore non-data lines such as headers or profile tags
        if "CODE" in line.upper() or "NAME:" in line.upper() or "PRN:" in line.upper(): 
            return None
            
        parts = line.split()
        # Verify minimum required columns for a valid record
        if len(parts) < 6: 
            return None

        # Identify Grade column as a positional anchor for other values
        valid_grades = ['O', 'A+', 'A', 'B+', 'B', 'C', 'D', 'F', 'P', 'AB', 'FAIL']
        grade_idx = -1
        grade_val = "-"

        # Scan right-to-left to find the grade indicator
        for i in range(1, 7):
            if i >= len(parts): 
                break
            if parts[-i] in valid_grades:
                grade_idx = len(parts) - i
                grade_val = parts[-i]
                break
                
        if grade_idx == -1: 
            return None

        # Extract values based on their relative position to the Grade
        ern = parts[grade_idx - 1]
        crd = parts[grade_idx - 2]
        p1 = parts[grade_idx - 3]
        p2 = parts[grade_idx - 4]
        
        # Determine Total marks while handling failing symbols
        if p1 in ['FFF', 'FAIL', 'AB', 'AA', '$', '#']:
            total = p2
            marks_end_idx = grade_idx - 4
        elif 'FFF' in p1:
            total = p1.replace('FFF', '')
            marks_end_idx = grade_idx - 3
        else:
            total = p1
            marks_end_idx = grade_idx - 3

        # Extract numerical grade and credit points
        gp = parts[grade_idx + 1] if (grade_idx + 1) < len(parts) else "0"
        cp = parts[grade_idx + 2] if (grade_idx + 2) < len(parts) else "0"

        # Resolve subject name using the code mapping
        code = parts[0].replace(':', '').strip()
        name = subject_map.get(code, "Subject Name Not Found")

        # Consolidate split mark columns (handling symbols like *, ~, etc.)
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
            
        # Ensure standard 3-column format for internal, external, and practical slots
        while len(cleaned_columns) < 3: 
            cleaned_columns.append("---")
        
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
    except Exception as e:
        # Controlled logging for row-level parsing errors
        print(f"Error parsing marks row: {line} | Error: {e}")
        return None

# ---------------------------------------------------
# CORE PARSING ENGINE
# ---------------------------------------------------

def main(pdf_path):
    """
    The main orchestrator for Second Year (SY) Result Parsing.
    Handles file access, text segmentation, and per-student data extraction.
    """
    all_students = []
    # metadata = {}
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            # Phase 1: Initialize global subject mapping
            subject_map, backup_meta = extract_subject_mapping(pdf)
            metadata = extract_header_metadata(pdf)

            # ३. जर मुख्य मेटाडेटा Unknown असेल, तर बॅकअप वापरा
            for key in ["pun_code", "course_name", "college_name"]:
                if metadata.get(key) == "Unknown" and backup_meta.get(key) not in [None, "Unknown"]:
                    metadata[key] = backup_meta[key]
                    print(f"DEBUG: Restored {key} from Backup: {metadata[key]}")

            print(f"[SY PARSER] Final College: {metadata['college_name']} | Course: {metadata['course_name']}")
            # Phase 2: Consolidate text from all pages
            full_text = "\n".join([page.extract_text(x_tolerance=2) or "" for page in pdf.pages])
            
            # Phase 3: Segment document into individual student blocks based on PRN
            student_blocks = re.split(r'(?=PRN:\s*\d+)', full_text)
            
            for block in student_blocks:
                try:
                    # Skip blocks that do not contain valid academic semester data
                    if "SEMESTER" not in block: 
                        continue
                    
                    # If metadata was unknown at header, try to find it inside student block
                    if metadata["college_name"] == "Unknown":
                        local_coll = re.search(r"Puncode\s*:.*?\d+\]\s*(.*?)(?=\n|$)", block, re.IGNORECASE)
                        if local_coll: metadata["college_name"] = local_coll.group(1).strip()
                        print(f"✅ [SY PARSER] College found in block: {metadata['college_name']}")
                            
                    # Initialize the student data structure with defaults
                    student = {
                        'sem1_subjects': [], 'sem2_subjects': [],
                        'sem3_subjects': [], 'sem4_subjects': [],
                        'sem1_summary': '', 'sem2_summary': '',
                        'sem3_summary': '', 'sem4_summary': '',
                        'full_name': 'Unknown', 'seat_no': '-', 'prn': '-', 'mother_name': '-',
                        'result': None, 'fy_total_msg': '', 
                        'total_marks': '-', 
                        'dashboard_sgpa': '-',
                        'course_name': metadata.get('course_name','Unknown') # Added dynamic course 
                    }

                    # Phase 4: Extract profile metadata via Regex
                    prn_m = re.search(r"PRN:\s*(\d+)", block)
                    seat_m = re.search(r"SEAT NO\.:\s*(\d+)", block)
                    name_m = re.search(r"NAME:\s*(.*?)(?=\s+Mother|\s+PRN|$)", block)
                    mother_m = re.search(r"Mother\s*-\s*(\w+)", block)
                    
                    if prn_m: student['prn'] = prn_m.group(1)
                    if seat_m: student['seat_no'] = seat_m.group(1)
                    if name_m: student['full_name'] = name_m.group(1).strip()
                    if mother_m: student['mother_name'] = mother_m.group(1)
                    
                    # Phase 5: Identify Result Status (e.g., PASS/FAIL)
                    res_match = re.search(r"Second Year Result\s*:\s*(.*?)(?=\s+Total|\n)", block, re.IGNORECASE)
                    if res_match:
                        student['result'] = res_match.group(1).strip().upper()
                    
                    # Phase 6: Capture official earned credits string
                    cred_match = re.search(r"(Total Credits Earned\s*:\s*[\d\/]+)", block)
                    if cred_match:
                        student['fy_total_msg'] = cred_match.group(1)

                    # Phase 7: Segment and parse Semester-wise mark rows
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
                                
                                # Capture summary/SGPA line per semester
                                if "SGPA" in line:
                                    student[f'sem{current_sem}_summary'] = re.sub(r'Page\s*\d+', '', line).strip()

                    # Phase 8: Determine Result Status if field was missing in PDF
                    if student['result'] is None:
                        all_grades = []
                        for sem in ['sem1', 'sem2', 'sem3', 'sem4']:
                            all_grades.extend([s['grd'] for s in student[f'{sem}_subjects']])
                        
                        if any(g in ['F', 'FFF', 'FAIL', 'AB', 'Absent'] for g in all_grades):
                            student['result'] = 'FAIL'
                        else:
                            student['result'] = 'PASS'

                    # Phase 9: Logic to extract current Dashboard SGPA
                    current_sgpa = "-"
                    # SGPA is prioritized from Semester 4 down to Semester 1
                    if "PASS" in str(student['result']).upper():
                        for label in ["Fourth", "Third", "Second", "First"]:
                            sgpa_m = re.search(rf"{label} Semester SGPA\s*:\s*([\d\.]+)", block, re.IGNORECASE)
                            if sgpa_m:
                                current_sgpa = sgpa_m.group(1)
                                break
                    
                    student['dashboard_sgpa'] = current_sgpa
                    student['total_marks'] = current_sgpa 

                    # Add valid student records to the final collection
                    if student['prn'] != '-':
                        all_students.append(student)
                except Exception as inner_e:
                    # Gracefully skip corrupted student blocks
                    print(f"Skipping student block due to error: {inner_e}")
                    continue
        
        # Return structured data consistent with parser_nep
        return {
            "success": True, 
            "college_info": metadata, 
            "student_data": all_students
        }

    except Exception as e:
        # Catch and return top-level parser failures
        return {"success": False, "error": f"SY Parser Critical Failure: {str(e)}"}
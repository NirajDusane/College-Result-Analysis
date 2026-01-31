import pdfplumber
import re
import sys


def extract_header_metadata(pdf):
    """
    Extracts complete College Name and exact Department/Course Name 
    from the Gazette style ledger header.
    """
    metadata = {
        "pun_code": None, 
        "course_name": "Unknown",
        "college_name": "Unknown"
    }
    try:
        first_page_text = pdf.pages[0].extract_text(x_tolerance=2)
        if not first_page_text:
            return metadata

        # 1. Improved Course Name Extraction
        # Logic: Captures text after "RESULT OF THE" until "EXAMINATION"
        # Example: RESULT OF THE BACHELOR OF BUSINESS ADMINISTRATION (REV.2019) EXAMINATION
        course_match = re.search(r"RESULT\s+OF\s+THE\s+(.*?)(?=\s+EXAMINATION|$)", first_page_text, re.IGNORECASE)
        if course_match:
            metadata["course_name"] = course_match.group(1).strip()
            print(f"[DEBUG] Exact Dept Found: {metadata['course_name']}")
        else:
            # Fallback if the specific 'RESULT OF' line is missing
            course_fallback = re.search(r"((?:BACHELOR|MASTER)\s+OF\s+.*?)(?=\s*\(|20\d{2}|$)", first_page_text, re.IGNORECASE)
            if course_fallback:
                metadata["course_name"] = course_fallback.group(1).strip()

        # 2. Improved College Name Extraction
        # Target: 1041 PANCHAVATI COLLEGE OF MGNT.AND COMM.SCIENCE,NASHIK PAGE : 1
        # Logic: We skip the first group of digits, then capture everything 
        # but strictly stop ONLY at "PAGE :" or end of line.
        college_match = re.search(r"^\d{3,4}\s+(.*?)(?=\s+PAGE\s*:|$)", first_page_text, re.MULTILINE | re.IGNORECASE)
        
        if college_match:
            metadata["college_name"] = college_match.group(1).strip()
            print(f"[DEBUG] Complete College Name: {metadata['college_name']}")
        else:
            # Final Fallback: if digits are not at start
            fallback = re.search(r"(?:PANCHAVATI|COLLEGE|INSTITUTE).*?(?=\s+PAGE\s*:|$)", first_page_text, re.IGNORECASE)
            if fallback:
                metadata["college_name"] = fallback.group(0).strip()

    except Exception as e:
        print(f"Gazette Metadata extraction error: {e}")
    
    return metadata


def parse_gazette_block(block_text):
    """
    Parses a single student data block extracted from the Gazette-style PDF text.
    Extracts student profiles, marks for regular and GR subjects, SGPA, and final results.
    """
    # Initialize the dictionary to store structured student records
    student_data = {}

    try:
        # ==========================================================
        # 1. STUDENT PROFILE EXTRACTION
        # ==========================================================
        # Regex captures Seat Number, Full Name, Gender (M/F), and PRN
        info_match = re.search(r"(\d{4,})\s+(.+?)\s+([MF])\s+(\d{10,})", block_text)
        
        if info_match:
            student_data['seat_no'] = info_match.group(1).strip()
            raw_name = info_match.group(2).strip()
            sex_char = info_match.group(3).strip()
            student_data['prn'] = info_match.group(4).strip()
            
            # Map gender identifier to full text
            student_data['gender'] = 'Male' if sex_char == 'M' else 'Female'

            # Split name logic: Assumes the last part of the name string is the Mother's Name
            name_parts = raw_name.split()
            if len(name_parts) > 1:
                student_data['mother_name'] = name_parts[-1]
                student_data['full_name'] = " ".join(name_parts[:-1])
            else:
                student_data['full_name'] = raw_name
                student_data['mother_name'] = "-"
        else:
            # Skip blocks that do not match the expected student identifier pattern
            return None

        # ==========================================================
        # 2. SUBJECT-WISE PERFORMANCE EXTRACTION
        # ==========================================================
        subjects = []
        
        # --- A) Processing Regular Subjects (5-digit numeric codes) ---
        # Regex identifies subject codes and isolates the associated marks data
        subject_regex = re.compile(
            r"(\d{5})\s*:\s*(.*?)(?=\s+\d{5}\s*:|\s+GR|$)"
        )
        matches = subject_regex.finditer(block_text)
        
        for match in matches:
            try:
                code = match.group(1)
                raw_marks_text = match.group(2).strip()
                
                parts = raw_marks_text.split()
                
                # Valid records must contain at least Grade and Credit values at the end
                if len(parts) >= 2:
                    credits = parts[-1]
                    grade = parts[-2]
                    marks_part = parts[:-2]
                else:
                    continue

                # Consolidate symbols like '*' or '$' with their corresponding marks
                processed_marks = []
                i = 0
                while i < len(marks_part):
                    curr = marks_part[i]
                    if (curr == '*' or curr == '$') and (i + 1 < len(marks_part)):
                        processed_marks.append(curr + " " + marks_part[i + 1])
                        i += 2
                    else:
                        processed_marks.append(curr)
                        i += 1
                
                # Map segments to Internal, External, and Total score fields
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
            except Exception as e:
                # Log issues with specific subject rows and continue processing
                print(f"Error parsing regular subject row: {e}")
                continue

        # --- B) Processing GR Add-on Subjects (Grade-based) ---
        try:
            # Regex to capture non-conventional subjects like GR6-A
            gr_pattern = re.compile(r"(GR\d-[A-Z])\s*:\s*!?\s*([A-Z\+]+)\s+(\d+)")
            for match in gr_pattern.finditer(block_text):
                subjects.append({
                    "code": match.group(1),
                    "internal": "-",
                    "external": "-",
                    "total": "-",
                    "grade": match.group(2).strip(),
                    "credits": match.group(3).strip()
                })
        except Exception as e:
            print(f"Error parsing GR subject section: {e}")
        
        student_data['subjects'] = subjects

        # ==========================================================
        # 3. ACADEMIC SUMMARY (SGPA & CREDIT TOTALS)
        # ==========================================================
        student_data['sgpa'] = {}

        # Extract semester-wise SGPA from the SGPA summary line
        try:
            sgpa_match = re.search(
                r"SGPA\s*:\s*(.*?)(?:TOTAL|CGPA|$)",
                block_text,
                re.DOTALL
            )
            if sgpa_match:
                sgpa_values = re.findall(r"\((\d)\)\s*([\d\.]+)", sgpa_match.group(1))
                for sem, score in sgpa_values:
                    student_data['sgpa'][sem] = score
        except Exception as e:
            print(f"Error extracting SGPA values: {e}")

        # Extract overall program totals (Credits and Marks)
        student_data['total_credits'] = "-"
        student_data['total_marks'] = "-"
        total_match = re.search(r"TOTAL\s+(\d+)\s+\d+\s+(\d+)", block_text)
        if total_match:
            student_data['total_credits'] = total_match.group(1)
            student_data['total_marks'] = total_match.group(2)

        # Extract First Year specific summary totals
        student_data['fy_credits'] = "-"
        student_data['fy_marks'] = "-"
        fy_match = re.search(r"F\.Y\.TOTAL\s+(\d+)\s+\d+\s+(\d+)", block_text)
        if fy_match:
            student_data['fy_credits'] = fy_match.group(1)
            student_data['fy_marks'] = fy_match.group(2)

        # ==========================================================
        # 4. FINAL RESULTS & RESULT VALIDATION
        # ==========================================================
        student_data['cgpa'] = "-"
        student_data['final_grade'] = "-"
        student_data['result'] = "FAIL"  # Default status for safe handling
        student_data['extra_notes'] = []

        # Parse CGPA and update result status to PASS if value exists
        cgpa_match = re.search(r"CGPA\s*:\s*([\d\.]+)", block_text)
        if cgpa_match:
            student_data['cgpa'] = cgpa_match.group(1)
            student_data['result'] = "PASS"

        # Capture the Final Grade string
        grade_match = re.search(
            r"FINAL GRADE\s*:\s*(.*?)($|\n|The student)",
            block_text
        )
        if grade_match:
            student_data['final_grade'] = grade_match.group(1).strip()

        # Extract specific institutional notes such as balance marks
        if "balance marks" in block_text:
            bal_match = re.search(
                r"(O\.\d+\s+balance marks\s*:\s*\d+)",
                block_text
            )
            if bal_match:
                student_data['extra_notes'].append(bal_match.group(1))

        # Check for mandatory credit completion statement
        if "completed mandetory" in block_text or "completed mandatory" in block_text:
            student_data['extra_notes'].append(
                "The student has completed mandetory add-on credits for this programme."
            )

        # Final check for failure indicators (e.g., A.T.K.T. status)
        fail_match = re.search(
            r"(FAIL\s+A\.T\.K\.T\.|RESULT\s*:\s*FAIL|FAIL\s+\$\s+0\.1)",
            block_text,
            re.IGNORECASE
        )
        
        if fail_match:
            status_text = fail_match.group(1).upper()
            if "A.T.K.T" in status_text:
                student_data['result'] = "FAIL A.T.K.T."
            else:
                student_data['result'] = "FAIL"

        return student_data

    except Exception as e:
        # Catch and report any unexpected errors during block parsing
        print(f"Critical failure in parse_gazette_block: {e}")
        return None

def analyze_gazette_pattern(full_text):
    """
    Handles the segmentation of the PDF text into student blocks based on separator patterns.
    """
    all_students_data = []

    try:
        # Gazette PDFs typically use long dashed lines as student separators
        student_blocks = re.split(r'-{30,}', full_text)
        
        for block in student_blocks:
            # Exclude empty segments and common header blocks
            if block.strip() and "SEAT NO." not in block:
                student_info = parse_gazette_block(block)
                if student_info:
                    all_students_data.append(student_info)
    except Exception as e:
        # Handle failures in splitting or high-level iteration
        print(f"High-level pattern analysis error: {e}")
    
    return {"student_data": all_students_data}

def main(pdf_path):
    """
    Orchestrates the extraction process: opens PDF, handles text extraction, and invokes analysis.
    """
    try:
        metadata = {}
        # Using pdfplumber to maintain spatial relationship of text for regex accuracy
        with pdfplumber.open(pdf_path) as pdf:
            metadata = extract_header_metadata(pdf)
            print(f"[GAZETTE PARSER] College: {metadata['college_name']} | Dept: {metadata['course_name']}")
            
            all_text = "\n".join(
                [
                    p.extract_text(x_tolerance=3, y_tolerance=3) or ""
                    for p in pdf.pages
                ]
            )
        
        # Trigger block-wise analysis of the extracted text
        result = analyze_gazette_pattern(all_text)

        # Final validation and response formatting
        if result.get('student_data'):
            # Attach metadata to result for consistency with other parsers
            return {
                "success": True, 
                "college_info": metadata, 
                "student_data": result['student_data']
            }
        else:
            return {"success": False, "error": "No recognizable student records were identified in the PDF."}
    except Exception as e:
        # Catch file-level access errors or critical extraction crashes
        return {"success": False, "error": f"Internal PDF processing failure: {str(e)}"}
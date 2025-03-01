Certainly! Below is the complete code for the Streamlit app that analyzes resumes based on the provided logic. I've ensured that the original logic remains intact while completing the code. The app includes functionality for extracting information from resumes, calculating scores, and providing recommendations based on the analysis.

```python
import streamlit as st
from groq import Groq
import PyPDF2
import os
import re
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime
import tempfile
import openpyxl
from io import BytesIO

# Initialize AI client
def initialize_groq_client():
    return Groq(api_key=os.environ.get("GROQ_API_KEY"))

# Extract text from PDF
def extract_text_from_pdf(pdf_file):
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = "\n".join([page.extract_text() for page in pdf_reader.pages if page.extract_text()])
        return text if text else None
    except Exception as e:
        st.error(f"Error extracting text from PDF: {str(e)}")
        return None

# Define Planful competitors
def get_planful_competitors():
    return [
        "Anaplan", "Workday Adaptive Planning", "Oracle EPM", "Oracle Hyperion", 
        "SAP BPC", "IBM Planning Analytics", "TM1", "Prophix", "Vena Solutions", 
        "Jedox", "OneStream", "Board", "Centage", "Solver", "Kepion", "Host Analytics",
        "CCH Tagetik", "Infor CPM", "Syntellis", "Longview"
    ]

# Extract LinkedIn URL directly from resume text - IMPROVED VERSION
def extract_linkedin_url(text):
    if not text:
        return ""
    
    # First check for common LinkedIn URL patterns
    patterns = [
        r'https?://(?:www\.)?linkedin\.com/in/[\w-]+(?:/[\w-]+)*',  # Standard format
        r'linkedin\.com/in/[\w-]+(?:/[\w-]+)*',                     # Without http(s)
        r'www\.linkedin\.com/in/[\w-]+(?:/[\w-]+)*',                # With www but no http(s)
        r'linkedin:\s*https?://(?:www\.)?linkedin\.com/in/[\w-]+',  # With linkedin: prefix
    ]
    
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        if matches:
            # Ensure URL has proper prefix
            url = matches[0]
            if not url.startswith('http'):
                url = 'https://' + ('' if url.startswith('www.') or url.startswith('linkedin.com') else 'www.') + url
                # Handle cases where the url starts with 'linkedin.com'
                if url.startswith('https://linkedin.com'):
                    url = url.replace('https://linkedin.com', 'https://www.linkedin.com')
            
            # Clean any trailing punctuation or spaces
            url = re.sub(r'[.,;:)\s]+$', '', url)
            
            return url
    
    # If standard patterns fail, look for cases where "LinkedIn" is mentioned with a URL nearby
    linkedin_mention = re.search(r'linkedin[\s:]*([^\s]+)', text, re.IGNORECASE)
    if linkedin_mention:
        potential_url = linkedin_mention.group(1)
        # If it looks like a URL, return it properly formatted
        if '.' in potential_url and '/' in potential_url:
            # Clean up the URL
            url = re.sub(r'[.,;:)\s]+$', '', potential_url)
            if not url.startswith('http'):
                url = 'https://' + ('' if url.startswith('www.') else 'www.') + url
            return url
    
    # Look for any URL that might appear near the word "LinkedIn"
    linkedin_context = re.search(r'linkedin.*?(https?://[^\s]+)', text, re.IGNORECASE)
    if linkedin_context:
        url = linkedin_context.group(1)
        url = re.sub(r'[.,;:)\s]+$', '', url)
        return url
    
    # Last resort: check if there's any mention of LinkedIn plus a URL within close proximity
    lines_with_linkedin = [line for line in text.split('\n') if 'linkedin' in line.lower()]
    for line in lines_with_linkedin:
        url_match = re.search(r'https?://[^\s]+', line)
        if url_match:
            url = url_match.group(0)
            url = re.sub(r'[.,;:)\s]+$', '', url)
            return url
    
    return ""

# Calculate the individual scores and overall score based on the algorithm
def calculate_scores(parsed_data, required_experience=3, stability_threshold=2):
    try:
        scores = {}
        
        # 1. Relevancy Score (already calculated by AI)
        if parsed_data["Relevancy Score (0-100)"] != "Not Available":
            try:
                scores["relevancy"] = float(parsed_data["Relevancy Score (0-100)"])
            except ValueError:
                scores["relevancy"] = 0
        else:
            scores["relevancy"] = 0
            
        # 2. Strong Matches Score (already calculated by AI)
        if parsed_data["Strong Matches Score"] != "Not Available":
            try:
                scores["strong_matches"] = float(parsed_data["Strong Matches Score"])
            except ValueError:
                scores["strong_matches"] = 0
        else:
            scores["strong_matches"] = 0
            
        # 3. Partial Matches Score (already calculated by AI)
        if parsed_data["Partial Matches Score"] != "Not Available":
            try:
                scores["partial_matches"] = float(parsed_data["Partial Matches Score"])
            except ValueError:
                scores["partial_matches"] = 0
        else:
            scores["partial_matches"] = 0
        
        # 4. Experience Score
        if parsed_data["Total Experience (Years)"] != "Not Available":
            try:
                candidate_exp = float(parsed_data["Total Experience (Years)"])
                scores["experience"] = min((candidate_exp / required_experience) * 100, 100)
            except ValueError:
                scores["experience"] = 0
        else:
            scores["experience"] = 0
            
        # 5. Job Stability Score
        if parsed_data["Job Stability"] != "Not Available":
            try:
                job_stability = float(parsed_data["Job Stability"])
                # Convert 1-10 scale to actual years tenure if needed
                if job_stability <= 10:  # Assuming job stability is on 1-10 scale
                    avg_tenure = (job_stability / 10) * 4  # Convert to years (max 4 years)
                else:
                    avg_tenure = job_stability  # Already in years
                
                scores["stability"] = min((avg_tenure / stability_threshold) * 100, 100)
            except ValueError:
                scores["stability"] = 0
        else:
            scores["stability"] = 0
            
        # 6. Education & College Rating Score
        if parsed_data["College Rating"] != "Not Available":
            if "premium" in parsed_data["College Rating"].lower() and "non" not in parsed_data["College Rating"].lower():
                scores["college"] = 100  # Top-tier
            elif "non-premium" in parsed_data["College Rating"].lower():
                scores["college"] = 70  # Mid-tier
            else:
                scores["college"] = 40  # Low-tier or unranked
        else:
            scores["college"] = 20  # Unranked or unknown
            
        # 7. Leadership Score
        if parsed_data["Leadership Skills"] != "Not Available":
            if any(word in parsed_data["Leadership Skills"].lower() for word in 
                   ["led", "managed", "directed", "leadership", "head", "team lead"]):
                scores["leadership"] = 100
            else:
                scores["leadership"] = 0
        else:
            scores["leadership"] = 0
            
        # 8. International Experience Score
        if parsed_data["International Team Experience"] != "Not Available":
            if any(word in parsed_data["International Team Experience"].lower() for word in 
                   ["yes", "international", "global", "worldwide", "multinational"]):
                scores["international"] = 100
            else:
                scores["international"] = 0
        else:
            scores["international"] = 0
            
        # 9. Competitor Experience Score
        if parsed_data["Competitor Experience"] != "Not Available":
            if parsed_data["Competitor Experience"].lower().startswith("yes"):
                if any(word in parsed_data["Competitor Experience"].lower() for word in 
                       ["anaplan", "workday", "oracle", "sap"]):
                    scores["competitor"] = 100  # Top competitor
                else:
                    scores["competitor"] = 50  # Other competitor
            else:
                scores["competitor"] = 0
        else:
            scores["competitor"] = 0
            
        # Calculate Overall Weighted Score
        overall_score = (
            (0.40 * scores["relevancy"]) +
            (0.15 * scores["experience"]) +
            (0.10 * scores["stability"]) +
            (0.10 * scores["college"]) +
            (0.10 * scores["leadership"]) +
            (0.10 * scores["international"]) +
            (0.05 * scores["competitor"])
        )
        
        # Determine Selection Recommendation
        if overall_score >= 80:
            recommendation = "Strong Fit ✅ - Call for interview"
        elif overall_score >= 60:
            recommendation = "Consider 🤔 - Further screening needed"
        else:
            recommendation = "Reject ❌ - Does not meet minimum criteria"
            
        return overall_score, recommendation, scores
    
    except Exception as e:
        st.error(f"Error calculating scores: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return 0, "Error in calculation", {}

# Call AI model to analyze resume with enhanced evaluation attributes
def analyze_resume(client, resume_text, job_description):
    competitors = get_planful_competitors()
    competitors_list = ", ".join(competitors)
    
    prompt = f"""
    As an expert resume analyzer, review the following resume against the job description.
    Provide a structured analysis with EXACT labeled fields as follows:
    
    Candidate Name: [Extract full name]
    Total Experience (Years): [Calculate years from earliest job to latest or current]
    Relevancy Score (0-100): [Score based on overall match]
    Strong Matches Score: [Score for exact skill matches]
    Strong Matches Reasoning: [Explain strong matches]
    Partial Matches Score: [Score for related skills]
    Partial Matches Reasoning: [Explain partial matches]
    All Tech Skills: [List ALL technical skills]
    Relevant Tech Skills: [List only skills relevant to job]
    Degree: [Highest degree only]
    College/University: [Institution name]
    Job Applying For: [Extract Job ID from job description]
    College Rating: [Rate as "Premium" or "Non-Premium"]
    Job Stability: [Rate 1-10, give 10 if ≥2 years per job]
    Latest Company: [Most recent employer]
    Leadership Skills: [Describe leadership experience]
    International Team Experience: [Yes/No + details about working with teams outside India]
    Notice Period: [Extract notice period info or "Immediate Joiner"]
    LinkedIn URL: [Extract LinkedIn profile URL if present, otherwise leave blank]
    Portfolio URL: [Extract any portfolio, GitHub, or personal website URL if present, otherwise leave blank]
    Work History: [List all previous companies and roles]
    Competitor Experience: [Yes/No. Check if resume mentions experience at any of these companies: {competitors_list}]
    
    Use EXACTLY these field labels in your response, followed by your analysis.
    DO NOT use any markdown formatting in your response.
    
    Resume:
    {resume_text}
    
    Job Description:
    {job_description}
    """
    
    try:
        response = client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[
                {"role": "system", "content": "You are an expert resume analyzer. Your task is to extract and analyze key information from resumes against job descriptions. Format your response as a simple list of key-value pairs with NO markdown formatting."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.5,
            max_tokens=3000
        )
        ai_response = response.choices[0].message.content
        
        # Debugging: Show AI response in Streamlit
        with st.expander("AI Response Output (Debugging)"):
            st.text_area("Raw AI Response", ai_response, height=300)
        
        return ai_response
    except Exception as e:
        st.error(f"Error during analysis: {str(e)}")
        return None

# Clean text by removing markdown and other formatting
def clean_text(text):
    if not text or text == "Not Available":
        return text
        
    # Remove markdown formatting
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)  # Bold
    text = re.sub(r'\*(.*?)\*', r'\1', text)      # Italic
    text = re.sub(r'__(.*?)__', r'\1', text)      # Underline
    text = re.sub(r'_(.*?)_', r'\1', text)        # Italic alternative
    text = re.sub(r'`(.*?)`', r'\1', text)        # Code
    
    # Remove bullet points and numbering
    text = re.sub(r'^\s*[-•*]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    
    return text.strip()

# Manually check for competitor mentions in work history
def check_competitor_experience(work_history, competitor_list):
    if not work_history or work_history == "Not Available":
        return "No"
    
    for competitor in competitor_list:
        if competitor.lower() in work_history.lower():
            return f"Yes - {competitor}"
    
    return "No"

# Parse AI response using improved key-value extraction
def parse_analysis(analysis, resume_text=None):
    try:
        # Definition of expected fields with exact matches and alternative formats
        expected_fields = {
            "Candidate Name": ["candidate name", "candidate's name", "name"],
            "Total Experience (Years)": ["total experience (years)", "total experience", "experience (years)", "years of experience"],
            "Relevancy Score (0-100)": ["relevancy score (0-100)", "relevancy score", "relevance score"],
            "Strong Matches Score": ["strong matches score", "strong match score"],
            "Strong Matches Reasoning": ["strong matches reasoning", "strong match reasoning"],
            "Partial Matches Score": ["partial matches score", "partial match score"],
            "Partial Matches Reasoning": ["partial matches reasoning", "partial match reasoning"],
            "All Tech Skills": ["all tech skills", "all technical skills"],
            "Relevant Tech Skills": ["relevant tech skills", "relevant technical skills"],
            "Degree": ["degree", "highest degree", "qualification"],
            "College/University": ["college/university", "university", "college", "institution"],
            "Job Applying For": ["job applying for", "job id", "position applying for", "role applying for"],
            "College Rating": ["college rating", "university rating", "institution rating"],
            "Job Stability": ["job stability", "employment stability"],
            "Latest Company": ["latest company", "current company", "most recent company"],
            "Leadership Skills": ["leadership skills", "leadership experience", "leadership"],
            "International Team Experience": ["international team experience", "global team experience", "international experience"],
            "Notice Period": ["notice period", "joining availability", "availability to join"],
            "LinkedIn URL": ["linkedin url", "linkedin profile", "linkedin", "linkedin link"],
            "Portfolio URL": ["portfolio url", "portfolio", "github url", "github", "personal website", "personal url", "website"],
            "Work History": ["work history", "employment history", "companies worked for", "previous companies"],
            "Competitor Experience": ["competitor experience", "worked for competitor", "competitor", "competition experience"],
        }
        
        # Create a dictionary to store the extracted values
        result = {field: "Not Available" for field in expected_fields}
        
        # Split the AI output into lines for processing
        lines = analysis.split('\n')
        
        # Process each line to extract fields
        current_field = None
        current_value = []
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:  # Skip empty lines
                continue
                
            # Check if this line starts a new field
            new_field_found = False
            
            if ':' in line:
                parts = line.split(':', 1)
                key = parts[0].strip().lower()
                value = parts[1].strip()
                
                # Check if this matches any of our expected fields
                for field, alternatives in expected_fields.items():
                    if key in alternatives:
                        # If we were building a previous field value, save it
                        if current_field and current_value:
                            result[current_field] = '\n'.join(current_value)
                            
                        # Start the new field
                        current_field = field
                        current_value = [value] if value else []
                        new_field_found = True
                        break
            
            # If this line doesn't start a new field and we're in the middle of a field, append to current value
            if not new_field_found and current_field and line:
                # Only append if the line doesn't look like it might be a mislabeled field
                if ':' not in line or line.split(':', 1)[0].strip().lower() not in [alt for alts in expected_fields.values() for alt in alts]:
                    current_value.append(line)
            
            # If we're at the last line and have an active field, save it
            if i == len(lines) - 1 and current_field and current_value:
                result[current_field] = '\n'.join(current_value)
        
        # Special handling for numeric fields
        numeric_fields = ["Total Experience (Years)", "Relevancy Score (0-100)", "Strong Matches Score", 
                         "Partial Matches Score", "Job Stability"]
        
        for field in numeric_fields:
            if result[field] != "Not Available":
                # Try to extract a numeric value
                matches = re.search(r'(\d+(?:\.\d+)?)', result[field])
                if matches:
                    result[field] = matches.group(1)
        
        # Ensure fields like Job Stability are numeric
        if result["Job Stability"] != "Not Available" and not re.match(r'^\d+(?:\.\d+)?$', result["Job Stability"]):
            # Try to extract a number from the text
            matches = re.search(r'(\d+(?:\.\d+)?)/10', result["Job Stability"])
            if matches:
                result["Job Stability"] = matches.group(1)
            else:
                matches = re.search(r'(\d+(?:\.\d+)?)', result["Job Stability"])
                if matches:
                    result["Job Stability"] = matches.group(1)
        
        # Normalize College Rating
        if result["College Rating"] != "Not Available":
            if "premium" in result["College Rating"].lower():
                result["College Rating"] = "Premium"
            elif "non" in result["College Rating"].lower() or "not" in result["College Rating"].lower():
                result["College Rating"] = "Non-Premium"
        
        # Normalize International Team Experience
        if result["International Team Experience"] != "Not Available":
            if any(word in result["International Team Experience"].lower() for word in ["yes", "has", "worked", "experience"]):
                if len(result["International Team Experience"]) < 5:  # Just "Yes" or similar
                    result["International Team Experience"] = "Yes"
            elif any(word in result["International Team Experience"].lower() for word in ["no", "not", "none"]):
                if len(result["International Team Experience"]) < 5:  # Just "No" or similar
                    result["International Team Experience"] = "No"
        
        # Handle LinkedIn URL extraction with improved method
        if resume_text:
            # First check if we already have a valid LinkedIn URL
            if result["LinkedIn URL"] != "Not Available":
                # If the value contains a valid URL, extract it
                linkedin_match = re.search(r'https?://(?:www\.)?linkedin\.com/in/[\w-]+(?:/[\w-]+)*', result["LinkedIn URL"])
                if linkedin_match:
                    result["LinkedIn URL"] = linkedin_match.group(0)
                else:
                    # Try to extract from the value itself if it's not already a URL
                    extracted_url = extract_linkedin_url(result["LinkedIn URL"])
                    if extracted_url:
                        result["LinkedIn URL"] = extracted_url
                    else:
                        # If not found in the field, try from the resume text
                        result["LinkedIn URL"] = extract_linkedin_url(resume_text)
            else:
                # If no LinkedIn URL was identified by the AI, search the resume text directly
                result["LinkedIn URL"] = extract_linkedin_url(resume_text)
        else:
            # Fallback to original approach if resume text not available
            if result["LinkedIn URL"] != "Not Available":
                linkedin_match = re.search(r'https?://(?:www\.)?linkedin\.com/\S+', result["LinkedIn URL"])
                if linkedin_match:
                    result["LinkedIn URL"] = linkedin_match.group(0)
                else:
                    linked_in_text = result["LinkedIn URL"].lower()
                    # If it says "not mentioned" or similar, set to empty string
                    if any(phrase in linked_in_text for phrase in ["not available", "not mentioned", "not found", "no linkedin"]):
                        result["LinkedIn URL"] = ""
            else:
                result["LinkedIn URL"] = ""
        
        # For Portfolio URL - use more specific extraction
        if result["Portfolio URL"] != "Not Available":
            # Look for common portfolio URLs
            portfolio_match = re.search(r'https?://(?:www\.)?(?:github\.com|gitlab\.com|bitbucket\.org|behance\.net|dribbble\.com|[\w-]+\.(?:com|io|org|net))/\S+', result["Portfolio URL"])
            if portfolio_match:
                result["Portfolio URL"] = portfolio_match.group(0)
            elif "not available" in result["Portfolio URL"].lower() or "not found" in result["Portfolio URL"].lower() or "not mentioned" in result["Portfolio URL"].lower():
                result["Portfolio URL"] = ""
        else:
            result["Portfolio URL"] = ""
        
        # Double-check competitor experience using work history
        # First, ensure we have work history data
        if result["Work History"] == "Not Available" and "Latest Company" in result and result["Latest Company"] != "Not Available":
            result["Work History"] = result["Latest Company"]  # Use at least the latest company

        # Check for competitor experience either from AI or manually
        if result["Competitor Experience"] == "Not Available" or not any(word in result["Competitor Experience"].lower() for word in ["yes", "no"]):
            result["Competitor Experience"] = check_competitor_experience(result["Work History"], get_planful_competitors())
            
        # Clean all values
        for field in result:
            result[field] = clean_text(result[field])
            
        # Calculate Overall Weighted Score and Selection Recommendation using the algorithm
        # Get required experience from job description - default to 3 years
        required_experience = 3
        stability_threshold = 2
        
        # Calculate overall score and get recommendation
        overall_score, recommendation, individual_scores = calculate_scores(result, required_experience, stability_threshold)
        
        # Add overall score and recommendation to result
        result["Overall Weighted Score"] = str(round(overall_score, 2))
        result["Selection Recommendation"] = recommendation
        
        # Convert to list in the expected order
        columns = list(expected_fields.keys()) + ["Overall Weighted Score", "Selection Recommendation"]
        extracted_data = [result.get(field, "Not Available") for field in columns]
        
        # Debugging: Show the extracted data and individual scores
        with st.expander("Extracted Data (Debugging)"):
            st.write("### Extracted Fields")
            for k, v in zip(columns, extracted_data):
                st.write(f"{k}: {v}")
                
            st.write("### Individual Scores")
            for k, v in individual_scores.items():
                st.write(f"{k}: {round(v, 2)}")
        
        return extracted_data
    
    except Exception as e:
        st.error(f"Error parsing AI response: {str(e)}")
        import traceback
        st.error(traceback.format_exc())
        return None

# Format Excel with nice styling and organization
def format_excel_workbook(wb, columns):
    ws = wb.active
    
    # Define styles
    from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
    
    # Header style
    header_font = Font(name='Calibri', size=12, bold=True, color='FFFFFF')
    header_fill = PatternFill(start_color='4F81BD', end_color='4F81BD', fill_type='solid')
    header_alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
    
    # Normal cell style
    normal_font = Font(name='Calibri', size=11)
    normal_alignment = Alignment(vertical='center', wrap_text=True)
    
    # Score cell style
    score_alignment = Alignment(horizontal='center', vertical='center')
    
    # URL cell style
    url_font = Font(name='Calibri', size=11, color='0000FF', underline='single')
    
    # Competitor style
    competitor_yes_font = Font(name='Calibri', size=11, bold=True, color='FF0000')
    
    # Border style
    thin_border = Border(
        left=Side(style='thin'),
        right=Side(style='thin'),
        top=Side(style='thin'),
        bottom=Side(style='thin')
    )
    
    # Apply header styles
    for col_num, column in enumerate(columns, 1):
        cell = ws.cell(row=1, column=col_num)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_alignment
        cell.border = thin_border
    
    # Apply styles to data cells and adjust column widths
    for row in range(2, ws.max_row + 1):
        for col in range(1, ws.max_column + 1):
            cell = ws.cell(row=row, column=col)
            cell.font = normal_font
            cell.alignment = normal_alignment
            cell.border = thin_border
            
            # Apply centered alignment to score columns
            column_name = columns[col-1]
            if any(term in column_name for term in ["Score", "Recommendation", "Job Stability"]):
                cell.alignment = score_alignment
                
                # Conditional formatting for numeric scores
                if cell.value not in ["Not Available", None, ""]:
                    try:
                        if any(term in column_name for term in ["Score", "Job Stability"]):
                            score_value = float(cell.value)
                            if score_value >= 75 or (column_name == "Job Stability" and score_value >= 8):
                                cell.fill = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')  # Green
                            elif score_value >= 50 or (column_name == "Job Stability" and score_value >= 6):
                                cell.fill = PatternFill(start_color='FFEB9C', end_color='FFEB9C', fill_type='solid')  # Yellow
                            else:
                                cell.fill = PatternFill(start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')  # Red
                    except (ValueError, TypeError):
                        pass
            
            # Special formatting for College Rating
            if column_name == "College Rating" and cell.value not in ["Not Available", None, ""]:
                if "premium" in str(cell.value).lower() and "non" not in str(cell.value).lower():
                    cell.fill = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')  # Green
                elif "non-premium" in str(cell.value).lower():
                    cell.fill = PatternFill(start_color='FFEB9C', end_color='FFEB9C', fill_type='solid')  # Yellow
            
            # Special formatting for Selection Recommendation
            if column_name == "Selection Recommendation" and cell.value not in ["Not Available", None, ""]:
                if "Strong Fit" in str(cell.value):
                    cell.fill = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')  # Green
                elif "Consider" in str(cell.value):
                    cell.fill = PatternFill(start_color='FFEB9C', end_color='FFEB9C', fill_type='solid')  # Yellow
                elif "Reject" in str(cell.value):
                    cell.fill = PatternFill(start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')  # Red
            
            # URL formatting for LinkedIn and Portfolio
            if column_name in ["LinkedIn URL", "Portfolio URL"] and cell.value not in ["Not Available", None, ""]:
                cell.font = url_font
                cell.hyperlink = cell.value
            
            # Competitor formatting
            if column_name == "Competitor Experience" and cell.value not in ["Not Available", None, ""]:
                if cell.value.lower().startswith("yes"):
                    cell.font = competitor_yes_font
                    cell.fill = PatternFill(start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')  # Red background
    
    # Adjust column widths
    for col_num, column in enumerate(columns, 1):
        column_letter = openpyxl.utils.get_column_letter(col_num)
        if any(term in column for term in ["Skills", "Reasoning", "Leadership", "International", "Experience", "Work History"]):
            ws.column_dimensions[column_letter].width = 40
        elif any(term in column for term in ["Recommendation", "Notice", "Company", "College", "URL"]):
            ws.column_dimensions[column_letter].width = 30
        else:
            ws.column_dimensions[column_letter].width = 18
    
    # Freeze the header row
    ws.freeze_panes = "A2"
    
    return wb

# Main Streamlit App
def main():
    st.title("📝 Enhanced Resume Analyzer")
    st.markdown("Built using the standardized resume scoring algorithm")
    
    # Add score explanation in sidebar
    with st.sidebar:
        st.title("Scoring Algorithm")
        st.markdown("""
        ### Overall Score Formula
        - 40% × Relevancy Score 
        - 15% × Experience Score
        - 10% × Job Stability Score
        - 10% × College Rating
        - 10% × Leadership Score
        - 10% × International Experience
        - 5% × Competitor Experience
        
        ### Selection Categories
        - **Strong Fit (80-100) ✅**: Call for an interview
        - **Consider (60-79) 🤔**: Further screening needed
        - **Reject (0-59) ❌**: Does not meet minimum criteria
        """)
        
        st.markdown("---")
        st.markdown("### About This App")
        st.write("This app analyzes resumes against job descriptions using AI and provides a scoring system based on various criteria.")
    
    # Load environment variables
    load_dotenv()
    
    if not os.environ.get("GROQ_API_KEY"):
        st.error("GROQ_API_KEY not found. Please set it in your environment or .env file.")
        return
        
    client = initialize_groq_client()
    uploaded_files = st.file_uploader

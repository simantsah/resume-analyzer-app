import streamlit as st
from groq import Groq
import PyPDF2
import os
import re
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, date
import tempfile
import json
import openpyxl
from io import BytesIO

# Initialize AI client
def initialize_groq_client():
    return Groq(api_key=os.environ.get("GROQ_API_KEY"))

# List of Planful competitors
def get_planful_competitors():
    return [
        "Workday", "Oracle", "SAP", "Anaplan", "Prophix", "Vena Solutions", 
        "Adaptive Insights", "Jedox", "Board", "Unit4", "OneStream", 
        "IBM Planning Analytics", "Infor", "CCH Tagetik", "Host Analytics", 
        "Centage", "Solver", "Longview", "insightsoftware", "Sage Intacct"
    ]

# List of premier institutes
def get_premier_institutes():
    return [
        "Harvard", "Stanford", "MIT", "IIT", "IIM", "Caltech", "Princeton", 
        "Yale", "Columbia", "University of Chicago", "University of Pennsylvania",
        "Cornell", "Northwestern", "Berkeley", "Carnegie Mellon", "Oxford", 
        "Cambridge", "ETH Zurich", "NUS", "Tsinghua", "INSEAD", "London Business School",
        "LSE", "Imperial College", "UCLA", "NYU", "BITS Pilani", "Delhi University", 
        "ISB", "XLRI", "NIT"
    ]

# Extract text from PDF
def extract_text_from_pdf(pdf_file):
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = "\n".join([page.extract_text() for page in pdf_reader.pages if page.extract_text()])
        return text if text else None
    except Exception as e:
        st.error(f"Error extracting text from PDF: {str(e)}")
        return None

# Call AI model to analyze resume with enhanced evaluation attributes
def analyze_resume(client, resume_text, job_description):
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
    College Rating: [Rate as "Premier Institute" or "Non-Premier Institute"]
    Job Stability: [Rate 1-10, give 10 if ≥2 years per job]
    Latest Company: [Most recent employer]
    Leadership Skills Reasoning: [Describe leadership experience in detail]
    Leadership Skills: [Yes or No based on if candidate has leadership experience]
    International Team Experience: [Yes/No + details about working with teams outside India]
    Notice Period: [Extract notice period info or "Immediate Joiner"]
    Overall Weighted Score: [Calculate final score 0-100]
    Selection Recommendation: [Exactly "Recommend" or "Not Recommend"]
    
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

# Check if candidate is from competitor company
def check_competitor_company(company_name):
    if not company_name or company_name == "Not Available":
        return "No"
        
    competitors = get_planful_competitors()
    for competitor in competitors:
        if competitor.lower() in company_name.lower():
            return "Yes"
    return "No"

# Check if college is premier
def check_premier_institute(college_name):
    if not college_name or college_name == "Not Available":
        return "Non-Premier Institute"
        
    premier_institutes = get_premier_institutes()
    for institute in premier_institutes:
        if institute.lower() in college_name.lower():
            return "Premier Institute"
    return "Non-Premier Institute"

# Parse AI response using improved key-value extraction
def parse_analysis(analysis):
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
            "Leadership Skills Reasoning": ["leadership skills reasoning", "leadership reasoning", "leadership experience"],
            "Leadership Skills": ["leadership skills", "leadership"],
            "International Team Experience": ["international team experience", "global team experience", "international experience"],
            "Notice Period": ["notice period", "joining availability", "availability to join"],
            "Overall Weighted Score": ["overall weighted score", "overall score", "final score"],
            "Selection Recommendation": ["selection recommendation", "hiring recommendation", "recommendation"]
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
                         "Partial Matches Score", "Job Stability", "Overall Weighted Score"]
        
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
        
        # Normalize College Rating to use only specified values
        result["College Rating"] = check_premier_institute(result["College/University"])
        
        # Normalize Leadership Skills
        if result["Leadership Skills"] != "Not Available":
            if any(word in result["Leadership Skills"].lower() for word in ["yes", "has", "demonstrated", "showed", "exhibited"]):
                result["Leadership Skills"] = "Yes"
            else:
                result["Leadership Skills"] = "No"
        
        # Normalize International Team Experience
        if result["International Team Experience"] != "Not Available":
            if any(word in result["International Team Experience"].lower() for word in ["yes", "has", "worked", "experience"]):
                if len(result["International Team Experience"]) < 5:  # Just "Yes" or similar
                    result["International Team Experience"] = "Yes"
            elif any(word in result["International Team Experience"].lower() for word in ["no", "not", "none"]):
                if len(result["International Team Experience"]) < 5:  # Just "No" or similar
                    result["International Team Experience"] = "No"
        
        # Normalize Selection Recommendation to only have the required values
        if result["Selection Recommendation"] != "Not Available":
            if any(word in result["Selection Recommendation"].lower() for word in ["recommend", "yes", "hire", "select", "shortlist"]):
                if "not" not in result["Selection Recommendation"].lower() and "don't" not in result["Selection Recommendation"].lower():
                    result["Selection Recommendation"] = "Recommend"
                else:
                    result["Selection Recommendation"] = "Not Recommend"
            else:
                result["Selection Recommendation"] = "Not Recommend"
        
        # Check if from competitor company
        is_competitor = check_competitor_company(result["Latest Company"])
        result["From Competitor"] = is_competitor
        
        # Clean all values
        for field in result:
            result[field] = clean_text(result[field])
        
        # Convert to list in the expected order
        ordered_fields = list(expected_fields.keys()) + ["From Competitor"]
        extracted_data = [result.get(field, "Not Available") for field in ordered_fields]
        
        # Debugging: Show the extracted data
        with st.expander("Extracted Data (Debugging)"):
            for k, v in zip(ordered_fields, extracted_data):
                st.write(f"{k}: {v}")
        
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
            
            # Apply centered alignment to score columns and yes/no columns
            column_name = columns[col-1]
            if any(term in column_name for term in ["Score", "Recommendation", "Job Stability", "Leadership Skills", "From Competitor"]):
                cell.alignment = score_alignment
                
                # Conditional formatting for numeric scores
                if cell.value not in ["Not Available", None]:
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
            if column_name == "College Rating" and cell.value not in ["Not Available", None]:
                if "premier" in str(cell.value).lower() and "non" not in str(cell.value).lower():
                    cell.fill = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')  # Green
                elif "non-premier" in str(cell.value).lower():
                    cell.fill = PatternFill(start_color='FFEB9C', end_color='FFEB9C', fill_type='solid')  # Yellow
            
            # Special formatting for Selection Recommendation
            if column_name == "Selection Recommendation" and cell.value not in ["Not Available", None]:
                if "recommend" in str(cell.value).lower() and "not" not in str(cell.value).lower():
                    cell.fill = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')  # Green
                else:
                    cell.fill = PatternFill(start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')  # Red
            
            # Special formatting for Leadership Skills and From Competitor
            if column_name in ["Leadership Skills", "From Competitor"] and cell.value not in ["Not Available", None]:
                if cell.value == "Yes":
                    cell.fill = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')  # Green
                elif cell.value == "No":
                    cell.fill = PatternFill(start_color='FFEB9C', end_color='FFEB9C', fill_type='solid')  # Yellow
    
    # Adjust column widths
    for col_num, column in enumerate(columns, 1):
        column_letter = openpyxl.utils.get_column_letter(col_num)
        if any(term in column for term in ["Reasoning", "International", "Experience"]):
            ws.column_dimensions[column_letter].width = 40
        elif any(term in column for term in ["Recommendation", "Notice", "Company", "College", "Skills"]):
            ws.column_dimensions[column_letter].width = 25
        else:
            ws.column_dimensions[column_letter].width = 18
    
    # Freeze the header row
    ws.freeze_panes = "A2"
    
    return wb

# Main Streamlit App
def main():
    st.title("📝 Enhanced Resume Analyzer")
    st.write("Upload your resumes and paste the job description to get a comprehensive analysis")

    # Load environment variables
    load_dotenv()
    
    if not os.environ.get("GROQ_API_KEY"):
        st.error("GROQ_API_KEY not found. Please set it in your environment or .env file.")
        return
        
    client = initialize_groq_client()
    uploaded_files = st.file_uploader("Upload resumes (PDF)", type=['pdf'], accept_multiple_files=True)
    job_description = st.text_area("Paste the job description here", height=200)
    
    results = []
    
    if uploaded_files and job_description:
        # Add a button to analyze all resumes at once
        if st.button("Analyze All Resumes"):
            progress_bar = st.progress(0)
            total_files = len(uploaded_files)
            
            for i, uploaded_file in enumerate(uploaded_files):
                st.subheader(f"Resume: {uploaded_file.name}")
                with st.spinner(f"Analyzing {uploaded_file.name}..."):
                    resume_text = extract_text_from_pdf(uploaded_file)
                    
                    if resume_text:
                        analysis = analyze_resume(client, resume_text, job_description)
                        if analysis:
                            parsed_data = parse_analysis(analysis)
                            if parsed_data:
                                results.append(parsed_data)
                                st.success(f"Successfully analyzed {uploaded_file.name}")
                            else:
                                st.warning(f"Could not extract structured data for {uploaded_file.name}")
                    else:
                        st.error(f"Could not extract text from {uploaded_file.name}")
                        
                # Update progress bar
                progress_bar.progress((i + 1) / total_files)
            
            # Complete the progress
            progress_bar.progress(1.0)
    
    if results:
        st.subheader("Analysis Results")
        
        columns = [
            # Basic attributes
            "Candidate Name", 
            "Total Experience (Years)", 
            "Relevancy Score (0-100)", 
            "Strong Matches Score",
            "Strong Matches Reasoning", 
            "Partial Matches Score",
            "Partial Matches Reasoning",
            "All Tech Skills",
            "Relevant Tech Skills", 
            "Degree", 
            "College/University",
            "Job Applying For",
            "College Rating",  # Changed to only use Premier Institute or Non-Premier Institute
            "Job Stability",
            "Latest Company",
            "From Competitor",  # New column
            "Leadership Skills",  # Changed to Yes/No
            "Leadership Skills Reasoning",  # New column with details
            "International Team Experience",
            "Notice Period",
            
            # Final Evaluation
            "Overall Weighted Score",
            "Selection Recommendation"  # Changed to only use Recommend or Not Recommend
        ]
        
        df = pd.DataFrame(results, columns=columns)
        
        # Display a simplified version of the dataframe for the UI
        display_columns = [
            "Candidate Name", "Total Experience (Years)", "Relevancy Score (0-100)", 
            "Job Applying For", "College Rating", "From Competitor", "Job Stability", 
            "Latest Company", "Leadership Skills", "International Team Experience", 
            "Notice Period", "Overall Weighted Score", "Selection Recommendation"
        ]
        st.dataframe(df[display_columns])
        
        # Prepare full results for download
        with st.spinner("Preparing Excel file..."):
            # Create a temporary file for download
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmpfile:
                # Save DataFrame to Excel
                df.to_excel(tmpfile.name, index=False, sheet_name='Resume Analysis', engine='openpyxl')
                
                # Format the Excel file with better styling
                wb = openpyxl.load_workbook(tmpfile.name)
                wb = format_excel_workbook(wb, columns)
                wb.save(tmpfile.name)
                tmpfile_path = tmpfile.name
            
            st.success("Excel file created successfully with all requested evaluation metrics!")
            
            # Offer the file for download
            with open(tmpfile_path, "rb") as file:
                file_data = file.read()
                st.download_button(
                    label="📥 Download Comprehensive Excel Report",
                    data=file_data,
                    file_name=f"enhanced_resume_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            # Clean up the temporary file
            os.unlink(tmpfile_path)

if __name__ == "__main__":
    main()

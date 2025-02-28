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

# Extract text from PDF
def extract_text_from_pdf(pdf_file):
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = "\n".join([page.extract_text() for page in pdf_reader.pages if page.extract_text()])
        return text if text else None
    except Exception as e:
        st.error(f"Error extracting text from PDF: {str(e)}")
        return None

# Call AI model to analyze resume with all requested attributes
def analyze_resume(client, resume_text, job_description):
    prompt = f"""
    As an expert resume analyzer, review the following resume against the job description.
    Provide a structured analysis including:
    
    PART 1: Basic Analysis
    - Candidate Name
    - Total Experience (Years): Calculate this from the earliest job date to either the latest job end date or current date if the candidate is currently employed. Format as a number.
    - Relevancy Score (0-100)
    - Strong Matches Score: Score based on exact skill matches with the job description
    - Strong Matches Reasoning: Explain why these skills are considered strong matches
    - Partial Matches Score: Score based on related but not exact matches with the job description
    - Partial Matches Reasoning: Explain why these skills are considered partial matches
    - All Tech Skills: A comprehensive list of ALL technical skills mentioned in the resume
    - Relevant Tech Skills: Only the technical skills that align with the job description
    - Degree: List the highest qualification only (e.g., Undergraduate, Graduate, PhD, etc.)
    - College/University
    - Job Applying For: Extract the Job ID from the job description. Look for the word "Job ID" or "Job ID".
    - College Rating: Rate the college as Premium or Non-Premium.
    - Job Stability: Rate the stability of the candidate's job history on a scale of ten. If the person has spent at least 2 years in each job, give a full 10. Otherwise, rate based on how frequently they switch jobs.
    - Latest Company: Identify the latest company the candidate is working for.
    - Leadership Skills: Check for leadership skills and provide a rating or description.
    - International Team Experience: Check if the candidate has worked with teams outside India. Look for mentions of people from different countries they have worked with.
    - Notice Period: Check if the candidate has mentioned a notice period or is an immediate joiner.
    
    PART 2: Final Evaluation
    - Overall Weighted Score (0-100): Calculate a weighted score based on the candidate's overall fit for the position
    - Selection Recommendation: Recommend if score is ≥75% ("Recommend" or "Do Not Recommend")
    
    Format your response with labels exactly as shown above, followed by a colon and the value.
    For example:
    Candidate Name: John Doe
    Total Experience (Years): 5
    ...and so on.
    
    IMPORTANT: Do not use Markdown formatting (like **, *, _, etc.) in your response.
    Use plain text only.

    Resume:
    {resume_text}
    
    Job Description:
    {job_description}
    """
    
    try:
        response = client.chat.completions.create(
            model="deepseek-r1-distill-qwen-32b",
            messages=[
                {"role": "system", "content": "You are an expert resume analyzer and career coach. Provide analysis in a consistent format with clear labels. Do not use Markdown formatting in your response."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
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

# Parse AI response using flexible key-value extraction
def parse_analysis(analysis):
    try:
        # Use a more reliable key-value extraction approach
        result = {}
        
        # Define the keys we're looking for
        keys = [
            # Basic attributes
            "Candidate Name", 
            "Total Experience", "Total Experience (Years)",
            "Relevancy Score", "Relevancy Score (0-100)",
            "Strong Matches Score",
            "Strong Matches Reasoning",
            "Partial Matches Score",
            "Partial Matches Reasoning",
            "All Tech Skills",
            "Relevant Tech Skills",
            "Degree",
            "College/University",
            "Job Applying For",
            "College Rating",
            "Job Stability",
            "Latest Company",
            "Leadership Skills",
            "International Team Experience",
            "Notice Period",
            
            # Final Evaluation
            "Overall Weighted Score",
            "Selection Recommendation"
        ]
        
        # Process the text line by line
        current_key = None
        current_value = []
        
        lines = analysis.split('\n')
        for i, line in enumerate(lines):
            # Check if this line starts a new key
            if ':' in line:
                # If we were building a previous value, save it
                if current_key:
                    result[current_key] = '\n'.join(current_value)
                
                # Start a new key-value pair
                parts = line.split(':', 1)
                key = parts[0].strip()
                value = parts[1].strip() if len(parts) > 1 else ""
                
                # Find matching key from our list
                matched_key = None
                for k in keys:
                    if key.lower() == k.lower() or key.lower().startswith(k.lower()):
                        matched_key = k
                        break
                
                if matched_key:
                    current_key = matched_key
                    current_value = [value] if value else []
                else:
                    current_key = None
                    current_value = []
            # If no colon but we have an active key, this might be continuation of a value
            elif current_key and line.strip():
                current_value.append(line.strip())
            
            # If we're at the last line and have an active key, save it
            if i == len(lines) - 1 and current_key:
                result[current_key] = '\n'.join(current_value)
        
        # Normalize specific fields
        if "Total Experience" in result and "Total Experience (Years)" not in result:
            value = result["Total Experience"]
            # Extract just the number if possible
            match = re.search(r'(\d+(?:\.\d+)?)', value)
            result["Total Experience (Years)"] = match.group(1) if match else value
        
        if "Relevancy Score" in result and "Relevancy Score (0-100)" not in result:
            value = result["Relevancy Score"]
            # Extract just the number if possible
            match = re.search(r'(\d+(?:\.\d+)?)', value)
            result["Relevancy Score (0-100)"] = match.group(1) if match else value
        
        # Ensure all required fields have at least a default value
        for key in [
            "Job Applying For", 
            "College Rating", 
            "Job Stability", 
            "Latest Company", 
            "Leadership Skills", 
            "International Team Experience", 
            "Notice Period"
        ]:
            if key not in result:
                result[key] = "Not Available"
        
        # Prepare the output in the expected order
        expected_keys = [
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
            "College Rating",
            "Job Stability",
            "Latest Company",
            "Leadership Skills",
            "International Team Experience",
            "Notice Period",
            
            # Final Evaluation
            "Overall Weighted Score",
            "Selection Recommendation"
        ]
        
        extracted_data = [result.get(k, "Not Available") for k in expected_keys]
        
        # Clean all extracted data
        extracted_data = [clean_text(item) for item in extracted_data]
        
        # Debugging: Show the extracted data
        with st.expander("Extracted Data (Debugging)"):
            for k, v in zip(expected_keys, extracted_data):
                st.write(f"{k}: {v}")
        
        return extracted_data
    
    except Exception as e:
        st.error(f"Error parsing AI response: {str(e)}")
        st.error(f"Exception details: {str(e)}")
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
    
    # Section header style
    section_font = Font(name='Calibri', size=11, bold=True)
    section_fill = PatternFill(start_color='DCE6F1', end_color='DCE6F1', fill_type='solid')
    
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
            
            # Apply centered alignment to score columns
            column_name = columns[col-1]
            if "Score" in column_name and "Reasoning" not in column_name or "Recommendation" in column_name or "Job Stability" in column_name:
                cell.alignment = score_alignment
                
                # Conditional formatting for scores
                if ("Score" in column_name or "Job Stability" in column_name) and cell.value not in ["Not Available", None]:
                    try:
                        score_value = float(cell.value)
                        if score_value >= 8:
                            cell.fill = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')  # Green
                        elif score_value >= 6:
                            cell.fill = PatternFill(start_color='FFEB9C', end_color='FFEB9C', fill_type='solid')  # Yellow
                        else:
                            cell.fill = PatternFill(start_color='FFC7CE', end_color='FFC7CE', fill_type='solid')  # Red
                    except (ValueError, TypeError):
                        pass
                
                # Conditional formatting for College Rating
                if column_name == "College Rating" and cell.value not in ["Not Available", None]:
                    if "premium" in str(cell.value).lower():
                        cell.fill = PatternFill(start_color='C6EFCE', end_color='C6EFCE', fill_type='solid')  # Green
                    else:
                        cell.fill = PatternFill(start_color='FFEB9C', end_color='FFEB9C', fill_type='solid')  # Yellow
    
    # Adjust column widths
    for col_num, column in enumerate(columns, 1):
        column_letter = openpyxl.utils.get_column_letter(col_num)
        if "Skills" in column or "Reasoning" in column or "Leadership Skills" in column or "International Team Experience" in column:
            ws.column_dimensions[column_letter].width = 40
        elif "Recommendation" in column or "Notice Period" in column:
            ws.column_dimensions[column_letter].width = 20
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
            "College Rating",
            "Job Stability",
            "Latest Company",
            "Leadership Skills",
            "International Team Experience",
            "Notice Period",
            
            # Final Evaluation
            "Overall Weighted Score",
            "Selection Recommendation"
        ]
        
        df = pd.DataFrame(results, columns=columns)
        
        # Display a simplified version of the dataframe for the UI
        display_columns = [
            "Candidate Name", "Total Experience (Years)", "Relevancy Score (0-100)", 
            "Job Applying For", "College Rating", "Job Stability", "Latest Company",
            "Leadership Skills", "International Team Experience", "Notice Period",
            "Overall Weighted Score", "Selection Recommendation"
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


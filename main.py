import streamlit as st
from groq import Groq
import PyPDF2
import os
import re
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime
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

# Call AI model to analyze resume
def analyze_resume(client, resume_text, job_description):
    prompt = f"""
    As an expert resume analyzer, review the following resume against the job description.
    Provide a structured analysis including:
    - Candidate Name
    - Total Experience (Years)
    - Relevancy Score (0-100)
    - Strong Matches Score
    - Partial Matches Score
    - Missing Skills Score
    - Relevant Tech Skills
    - Tech Stack
    - Tech Stack Experience
    - Degree
    - College/University

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
            max_tokens=2000
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
            "Candidate Name", 
            "Total Experience", "Total Experience (Years)",
            "Relevancy Score", "Relevancy Score (0-100)",
            "Strong Matches Score",
            "Partial Matches Score",
            "Missing Skills Score",
            "Relevant Tech Skills",
            "Tech Stack",
            "Tech Stack Experience",
            "Degree",
            "College/University"
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
                    if key.lower() == k.lower() or k.lower() in key.lower():
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
        
        # Prepare the output in the expected order
        expected_keys = [
            "Candidate Name", 
            "Total Experience (Years)", 
            "Relevancy Score (0-100)", 
            "Strong Matches Score", 
            "Partial Matches Score", 
            "Missing Skills Score", 
            "Relevant Tech Skills", 
            "Tech Stack", 
            "Tech Stack Experience", 
            "Degree", 
            "College/University"
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

# Main Streamlit App
def main():
    st.title("📝 Resume Analyzer")
    st.write("Upload your resumes and paste the job description to get a structured analysis")

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
            for uploaded_file in uploaded_files:
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
    
    if results:
        st.subheader("Analysis Results")
        
        columns = [
            "Candidate Name", "Total Experience (Years)", "Relevancy Score (0-100)", 
            "Strong Matches Score", "Partial Matches Score", "Missing Skills Score", 
            "Relevant Tech Skills", "Tech Stack", "Tech Stack Experience", "Degree", 
            "College/University"
        ]
        
        df = pd.DataFrame(results, columns=columns)
        
        # Display the dataframe
        st.dataframe(df)
        
        # Use StringIO approach to ensure Excel file contains all text properly
        with st.spinner("Preparing Excel file..."):
            # Create a temporary file for download
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmpfile:
                # Save DataFrame to Excel
                df.to_excel(tmpfile.name, index=False, sheet_name='Resume Analysis', engine='openpyxl')
                
                # Now let's make sure each cell in the Excel file has the proper value
                # Open the workbook and save it again with explicit string values
                wb = openpyxl.load_workbook(tmpfile.name)
                ws = wb.active
                
                # Dictionary to store adjusted column widths
                col_widths = {}
                
                # Start from row 2 (skip header)
                for row in range(2, ws.max_row + 1):
                    for col in range(1, ws.max_column + 1):
                        cell = ws.cell(row=row, column=col)
                        val = df.iloc[row-2, col-1]
                        # Convert to string to avoid any conversion issues
                        cell.value = str(val) if val != "Not Available" else "Not Available"
                        
                        # Track maximum column width needed
                        if col not in col_widths:
                            col_widths[col] = len(str(columns[col-1]))
                        col_widths[col] = max(col_widths[col], min(100, len(str(val))))
                
                # Adjust column widths for better readability
                for col, width in col_widths.items():
                    # Set minimum width of 15 and maximum of 50
                    adjusted_width = max(15, min(50, width + 2))
                    ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = adjusted_width
                
                # Save the workbook
                wb.save(tmpfile.name)
                tmpfile_path = tmpfile.name
            
            st.success("Excel file created successfully!")
            
            # Offer the file for download
            with open(tmpfile_path, "rb") as file:
                file_data = file.read()
                st.download_button(
                    label="📥 Download Excel Report",
                    data=file_data,
                    file_name=f"resume_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

            # Clean up the temporary file
            os.unlink(tmpfile_path)

if __name__ == "__main__":
    main()

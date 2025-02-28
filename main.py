import streamlit as st
from groq import Groq
import PyPDF2
import os
import time
import logging
from dotenv import load_dotenv
import re
import hashlib
from datetime import datetime

# Ensure gspread is installed before running the script
try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
except ModuleNotFoundError:
    os.system("pip install gspread oauth2client")
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials

try:
    load_dotenv()
except:
    pass

# Google Sheets API Setup
SHEET_URL = "https://docs.google.com/spreadsheets/d/1ptmDeXbe6MzapC0cPQIrKBF3XoNkvk9JnZ5nMpG1GY0/edit?gid=0#gid=0"
CREDENTIALS_FILE = "credentials.json"  # Place your Google Sheets credentials JSON file in the working directory

def connect_to_gsheets():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name(CREDENTIALS_FILE, scope)
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        st.error(f"Error connecting to Google Sheets: {str(e)}")
        return None

def get_gsheet():
    client = connect_to_gsheets()
    if client:
        return client.open_by_url(SHEET_URL).sheet1  # Select the first sheet
    return None

def extract_text_from_pdf(pdf_file):
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = "".join([page.extract_text() for page in pdf_reader.pages if page.extract_text()])
        return text
    except Exception as e:
        st.error(f"Error extracting text from PDF: {str(e)}")
        return None

def extract_name(text):
    match = re.search(r'(?i)\b(name|full name)[:\s]+([A-Za-z ]{2,})', text)
    return match.group(2) if match else "Name not found"

def extract_experience(text):
    dates = re.findall(r'\b(\d{4})\b', text)
    if dates:
        years = [int(year) for year in dates if 1950 < int(year) <= datetime.now().year]
        if years:
            return max(years) - min(years)
    return "Could not determine"

def generate_resume_hash(resume_text):
    return hashlib.sha256(resume_text.encode()).hexdigest()

def analyze_resume(client, resume_text, job_description):
    prompt = f"""
    As an expert resume analyzer, review the following resume against the job description.
    Provide a detailed analysis including:
    1. Candidate Name (Extracted from resume)
    2. Total Experience (Find the least date of joining to the latest date of joining in years)
    3. Relevancy Score as per Job Description (0-100)
    4. Strong Matches (Assign a numeric point value)
    5. Partial Matches (Assign a numeric point value)
    6. Missing Skills (Assign a numeric point value)
    7. Relevant Tech Skills (Compare the JD and the resume to find out the tech stack and relevancy)
    8. Tech Stack (List all tech stack known to the candidate)
    9. Tech Stack Experience (For each tech stack, rate the candidate as No Experience, Beginner, Intermediate, Advanced, or Expert)
    
    Resume:
    {resume_text}
    
    Job Description:
    {job_description}
    
    Provide the analysis in a clear, structured format.
    """
    
    try:
        response = client.chat.completions.create(
            model="deepseek-r1-distill-qwen-32b",
            messages=[
                {"role": "system", "content": "You are an expert resume analyzer and career coach."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Error during analysis: {str(e)}")
        return None

def update_google_sheets(candidate_name, total_experience, analysis, resume_hash):
    sheet = get_gsheet()
    if sheet is None:
        st.error("Could not connect to Google Sheets.")
        return

    existing_records = sheet.get_all_values()

    # Check if resume already exists in the sheet (by hash)
    for row in existing_records:
        if len(row) > 0 and row[0] == resume_hash:
            st.success("Data already exists in Google Sheets! ✅")
            return

    # Append new entry
    sheet.append_row([resume_hash, candidate_name, total_experience, analysis])
    st.success("Data successfully saved to Google Sheets! ✅")

def main():
    st.title("📝 Resume Analyzer")
    st.write("Upload your resumes and paste the job description to get a detailed analysis")

    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

    uploaded_files = st.file_uploader("Upload resumes (PDF)", type=['pdf'], accept_multiple_files=True)
    job_description = st.text_area("Paste the job description here", height=200, help="Paste the complete job description including requirements and qualifications")

    if uploaded_files and job_description:
        for uploaded_file in uploaded_files:
            st.subheader(f"Resume: {uploaded_file.name}")
            resume_text = extract_text_from_pdf(uploaded_file)
            if resume_text:
                candidate_name = extract_name(resume_text)
                total_experience = extract_experience(resume_text)
                resume_hash = generate_resume_hash(resume_text)

                # Check if analysis already exists in Google Sheets
                sheet = get_gsheet()
                cached_analysis = None
                if sheet:
                    existing_records = sheet.get_all_values()
                    for row in existing_records:
                        if len(row) > 0 and row[0] == resume_hash:
                            cached_analysis = row[3]
                            break

                if cached_analysis:
                    analysis = cached_analysis
                    st.success("Loaded from Google Sheets! ✅")
                else:
                    with st.spinner(f"Analyzing {uploaded_file.name}..."):
                        time.sleep(1)
                        analysis = analyze_resume(client, resume_text, job_description)
                        if analysis:
                            update_google_sheets(candidate_name, total_experience, analysis, resume_hash)

                st.text_area("Extracted Text", resume_text, height=200, key=uploaded_file.name)
                st.write(f"**Candidate Name:** {candidate_name}")
                st.write(f"**Total Experience:** {total_experience} years")

                st.markdown(f"""
                <div class="analysis-box-result"><h2>Analysis</h2>
                {analysis}
                </div>
                """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()

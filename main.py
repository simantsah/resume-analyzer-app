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
from streamlit_gsheets import GSheetsConnection

try:
    load_dotenv()
except:
    pass

# Google Sheets API Setup using Streamlit Connection
conn = st.connection("gsheets", type=GSheetsConnection)

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
    try:
        existing_records = conn.read()
        
        # Check if resume already exists in the sheet (by hash)
        if not existing_records.empty and resume_hash in existing_records.values:
            st.success("Data already exists in Google Sheets! ✅")
            return

        # Append new entry
        new_entry = [[resume_hash, candidate_name, total_experience, analysis]]
        conn.update(worksheet="ResumeAnalysis", data=new_entry, append=True)
        st.success("Data successfully saved to Google Sheets! ✅")
    except Exception as e:
        st.error(f"Error updating Google Sheets: {str(e)}")

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
                existing_records = conn.read()
                cached_analysis = None
                if not existing_records.empty and resume_hash in existing_records.values:
                    cached_analysis = existing_records[existing_records[0] == resume_hash].values[0][3]

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

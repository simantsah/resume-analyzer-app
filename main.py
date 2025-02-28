import streamlit as st
from groq import Groq
import PyPDF2
import os
import re
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime

def initialize_groq_client():
    return Groq(api_key=os.environ.get("GROQ_API_KEY"))

def extract_text_from_pdf(pdf_file):
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = "".join([page.extract_text() for page in pdf_reader.pages if page.extract_text()])
        return text
    except Exception as e:
        st.error(f"Error extracting text from PDF: {str(e)}")
        return None

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
    
    Resume:
    {resume_text}
    
    Job Description:
    {job_description}
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
        ai_response = response.choices[0].message.content
        st.text_area("AI Response Output", ai_response, height=300)
        return ai_response
    except Exception as e:
        st.error(f"Error during analysis: {str(e)}")
        return None

def parse_analysis(analysis):
    try:
        st.write("Debugging AI Output:", analysis)
        pattern = re.compile(
            r"Candidate Name:\s*(.*?)\n?" 
            r".*?Total Experience.*?(\d+)?" 
            r".*?Relevancy Score.*?(\d+)?" 
            r".*?Strong Matches Score.*?(\d+)?" 
            r".*?Partial Matches Score.*?(\d+)?" 
            r".*?Missing Skills Score.*?(\d+)?" 
            r".*?Relevant Tech Skills:\s*(.*?)\n?" 
            r".*?Tech Stack:\s*(.*?)\n?" 
            r".*?Tech Stack Experience:\s*(.*?)\n?" 
            r".*?Degree:\s*(.*?)\n?" 
            r".*?College/University:\s*(.*?)\n?",
            re.DOTALL
        )
        
        match = pattern.search(analysis)
        if match:
            extracted_data = [match.group(i).strip() if match.group(i) else "Not Available" for i in range(1, 12)]
            return extracted_data
        else:
            st.error("⚠️ AI response format not recognized. Please check AI output above.")
            return None
    except Exception as e:
        st.error(f"Error parsing AI response: {str(e)}")
        return None

def main():
    st.title("📝 Resume Analyzer")
    st.write("Upload your resumes and paste the job description to get a structured analysis")

    client = initialize_groq_client()
    uploaded_files = st.file_uploader("Upload resumes (PDF)", type=['pdf'], accept_multiple_files=True)
    job_description = st.text_area("Paste the job description here", height=200)
    
    results = []
    
    if uploaded_files and job_description:
        for uploaded_file in uploaded_files:
            st.subheader(f"Resume: {uploaded_file.name}")
            resume_text = extract_text_from_pdf(uploaded_file)
            
            if resume_text:
                if st.button(f"Analyze {uploaded_file.name}"):
                    with st.spinner(f"Analyzing {uploaded_file.name}..."):
                        analysis = analyze_resume(client, resume_text, job_description)
                        if analysis:
                            parsed_data = parse_analysis(analysis)
                            if parsed_data:
                                results.append(parsed_data)
                            else:
                                st.warning(f"Could not extract structured data for {uploaded_file.name}")
    
    if results:
        df = pd.DataFrame(results, columns=[
            "Candidate Name", "Total Experience (Years)", "Relevancy Score (0-100)", 
            "Strong Matches Score", "Partial Matches Score", "Missing Skills Score", 
            "Relevant Tech Skills", "Tech Stack", "Tech Stack Experience", "Degree", 
            "College/University"])

        excel_file = "resume_analysis.xlsx"
        df.to_excel(excel_file, index=False)
        
        st.download_button(
            label="📥 Download Excel Report",
            data=open(excel_file, "rb"),
            file_name=excel_file,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

if __name__ == "__main__":
    main()

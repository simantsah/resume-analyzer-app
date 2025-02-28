import streamlit as st
from groq import Groq
import PyPDF2
import os
import re
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime, date
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

# Extract total experience based on earliest and latest job dates
def calculate_total_experience(resume_text):
    """Extracts years of experience from resume based on earliest and latest dates."""
    dates = re.findall(r'\b(19|20)\d{2}\b', resume_text)  # Extracts years (1900-2099)
    dates = sorted(set(map(int, dates)))  # Remove duplicates and sort
    
    if not dates:
        return "Not Available"
    
    min_year = min(dates)
    max_year = max(dates)

    if 'Present' in resume_text or 'Current' in resume_text:
        max_year = datetime.today().year  # If 'Present' is mentioned, use current year

    total_experience = max_year - min_year
    return max(0, total_experience)  # Ensure non-negative values

# AI Resume Analysis
def analyze_resume(client, resume_text, job_description):
    total_experience = calculate_total_experience(resume_text)

    prompt = f"""
    As an expert resume analyzer, review the following resume against the job description.
    Provide a structured analysis including:
    
    - Candidate Name
    - Total Experience (Years): {total_experience}
    - Relevancy Score (0-100)
    - Strong Matches Score
    - Strong Matches Reasoning
    - Partial Matches Score
    - Partial Matches Reasoning
    - All Tech Skills (All technical skills mentioned in the resume)
    - Relevant Tech Stack (Only skills aligning with JD)
    - Degree: Highest qualification (Graduate, Undergraduate, PhD)
    - College/University
    
    - Years of Experience Score (1-10): Assign 10 if YoE aligns with JD, otherwise assign 5
    - Technical Skills Score (1-10)
    - Industry Knowledge Score (1-10)
    - Job Role Alignment Score (1-10)
    - Leadership & Teamwork Score (1-10)
    - Stability & Career Progression Score (1-10)
    
    - Overall Weighted Score (0-100): Based on the above attributes.
    - Selection Recommendation: Recommend if score is ≥75% ("Recommend" or "Do Not Recommend")

    Format your response with labels exactly as shown above, followed by a colon and the value.

    Resume:
    {resume_text}

    Job Description:
    {job_description}
    """

    try:
        response = client.chat.completions.create(
            model="deepseek-r1-distill-qwen-32b",
            messages=[
                {"role": "system", "content": "You are an expert resume analyzer. Provide responses in a structured format with labels exactly as shown."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=3000
        )
        ai_response = response.choices[0].message.content
        
        with st.expander("AI Response Output (Debugging)"):
            st.text_area("Raw AI Response", ai_response, height=300)
        
        return ai_response
    except Exception as e:
        st.error(f"Error during analysis: {str(e)}")
        return None

# Parse AI response
def parse_analysis(analysis):
    """Extract structured data from AI response."""
    try:
        data = {}
        for line in analysis.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                data[key.strip()] = value.strip()

        extracted_data = [
            data.get("Candidate Name", "Not Available"),
            data.get("Total Experience (Years)", "Not Available"),
            data.get("Relevancy Score", "Not Available"),
            data.get("Strong Matches Score", "Not Available"),
            data.get("Strong Matches Reasoning", "Not Available"),
            data.get("Partial Matches Score", "Not Available"),
            data.get("Partial Matches Reasoning", "Not Available"),
            data.get("All Tech Skills", "Not Available"),
            data.get("Relevant Tech Stack", "Not Available"),
            data.get("Degree", "Not Available"),
            data.get("College/University", "Not Available"),
            data.get("Years of Experience Score", "Not Available"),
            data.get("Technical Skills Score", "Not Available"),
            data.get("Industry Knowledge Score", "Not Available"),
            data.get("Job Role Alignment Score", "Not Available"),
            data.get("Leadership & Teamwork Score", "Not Available"),
            data.get("Stability & Career Progression Score", "Not Available"),
            data.get("Overall Weighted Score", "Not Available"),
            data.get("Selection Recommendation", "Not Available"),
        ]
        return extracted_data
    except Exception as e:
        st.error(f"Error parsing AI response: {str(e)}")
        return None

# Main Streamlit App
def main():
    st.title("📝 Enhanced Resume Analyzer")
    st.write("Upload resumes and paste the job description to get a structured analysis.")

    load_dotenv()
    client = initialize_groq_client()
    uploaded_files = st.file_uploader("Upload resumes (PDF)", type=['pdf'], accept_multiple_files=True)
    job_description = st.text_area("Paste the job description here", height=200)
    
    results = []

    if uploaded_files and job_description:
        if st.button("Analyze All Resumes"):
            for uploaded_file in uploaded_files:
                st.subheader(f"Resume: {uploaded_file.name}")
                resume_text = extract_text_from_pdf(uploaded_file)
                if resume_text:
                    analysis = analyze_resume(client, resume_text, job_description)
                    if analysis:
                        parsed_data = parse_analysis(analysis)
                        if parsed_data:
                            results.append(parsed_data)
                            st.success(f"Successfully analyzed {uploaded_file.name}")

    if results:
        columns = [
            "Candidate Name", "Total Experience (Years)", "Relevancy Score (0-100)",
            "Strong Matches Score", "Strong Matches Reasoning", "Partial Matches Score",
            "Partial Matches Reasoning", "All Tech Skills", "Relevant Tech Stack",
            "Degree", "College/University", "Years of Experience Score",
            "Technical Skills Score", "Industry Knowledge Score",
            "Job Role Alignment Score", "Leadership & Teamwork Score",
            "Stability & Career Progression Score", "Overall Weighted Score", "Selection Recommendation"
        ]

        df = pd.DataFrame(results, columns=columns)
        st.dataframe(df)

        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmpfile:
            df.to_excel(tmpfile.name, index=False, engine='openpyxl')
            st.download_button(
                label="📥 Download Excel Report",
                data=open(tmpfile.name, "rb").read(),
                file_name=f"resume_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

if __name__ == "__main__":
    main()

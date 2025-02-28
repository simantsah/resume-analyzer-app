import streamlit as st
from groq import Groq
import PyPDF2
import os
import re
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime
import tempfile

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
        
        # Debugging: Show AI response in Streamlit
        st.text_area("AI Response Output (Debugging)", ai_response, height=300)
        
        return ai_response
    except Exception as e:
        st.error(f"Error during analysis: {str(e)}")
        return None

# Parse AI response using flexible extraction
def parse_analysis(analysis):
    try:
        st.write("Debugging AI Output:", analysis)

        # More flexible regex pattern to match various response formats
        pattern = re.compile(
            r"Candidate Name:\s*(.*?)\n?"
            r".*?Total Experience.*?:\s*(\d+)?\s*years?\n?"
            r".*?Relevancy Score.*?:\s*(\d+)?\n?"
            r".*?Strong Matches Score.*?:\s*(\d+)?\n?"
            r".*?Partial Matches Score.*?:\s*(\d+)?\n?"
            r".*?Missing Skills Score.*?:\s*(\d+)?\n?"
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
        
        # If regex fails, use fallback parsing
        st.warning("Regex parsing failed. Attempting fallback extraction.")
        return fallback_parse_analysis(analysis)
    
    except Exception as e:
        st.error(f"Error parsing AI response: {str(e)}")
        return None

# Fallback parsing: Extract key-value pairs manually
def fallback_parse_analysis(analysis):
    """Fallback method for extracting data from AI response when regex fails."""
    try:
        data = {}
        for line in analysis.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                data[key.strip()] = value.strip()

        extracted_data = [
            data.get("Candidate Name", "Not Available"),
            data.get("Total Experience", "Not Available"),
            data.get("Relevancy Score", "Not Available"),
            data.get("Strong Matches Score", "Not Available"),
            data.get("Partial Matches Score", "Not Available"),
            data.get("Missing Skills Score", "Not Available"),
            data.get("Relevant Tech Skills", "Not Available"),
            data.get("Tech Stack", "Not Available"),
            data.get("Tech Stack Experience", "Not Available"),
            data.get("Degree", "Not Available"),
            data.get("College/University", "Not Available"),
        ]
        return extracted_data
    except Exception as e:
        st.error(f"Error in fallback parsing: {str(e)}")
        return None

# Main Streamlit App
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
                analyze_button = st.button(f"Analyze {uploaded_file.name}")
                if analyze_button:
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

        # Create a temporary file for download
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmpfile:
            df.to_excel(tmpfile.name, index=False)
            tmpfile_path = tmpfile.name

        st.success("Excel file created successfully!")
        
        # Offer the file for download
        with open(tmpfile_path, "rb") as file:
            st.download_button(
                label="📥 Download Excel Report",
                data=file,
                file_name="resume_analysis.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        # Clean up the temporary file
        os.unlink(tmpfile_path)

if __name__ == "__main__":
    main()

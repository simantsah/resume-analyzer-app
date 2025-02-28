import streamlit as st
from groq import Groq
import PyPDF2
import os
import time
import logging
import pandas as pd
from dotenv import load_dotenv
import uuid
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
import re

try:
    load_dotenv()
except:
    pass

# Set up the DynamoDB client using environment variables
try:
    aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
    aws_secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
    aws_region = os.environ.get('AWS_REGION', 'ap-south-1')

    dynamodb = boto3.resource('dynamodb',
                              region_name=aws_region,
                              aws_access_key_id=aws_access_key_id,
                              aws_secret_access_key=aws_secret_access_key)

    def upload_item_to_dynamodb(table_name, item):
        table = dynamodb.Table(table_name)
        try:
            response = table.put_item(Item=item)
            print(f"Item uploaded successfully: {response}")
        except ClientError as e:
            print(f"Error uploading item: {e.response['Error']['Message']}")
except:
    pass

st.set_page_config(
    page_title="Resume Analyzer",
    page_icon="📝",
    layout="wide"
)

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

def extract_college_and_degree(text):
    college_match = re.search(r'(?i)(?:university|college|institute of technology|school of engineering)[:\s]*([A-Za-z &.,-]{5,})', text)
    degree_match = re.search(r'(?i)\b(Bachelor|Master|PhD|Associate|Diploma)\b', text)
    
    college = college_match.group(1).strip() if college_match else "College not found"
    degree = degree_match.group(1) if degree_match else "Degree not found"
    
    return degree, college

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
        return response.choices[0].message.content
    except Exception as e:
        st.error(f"Error during analysis: {str(e)}")
        return None

def main():
    st.title("📝 Resume Analyzer")
    st.write("Upload your resumes and paste the job description to get a structured analysis")

    client = initialize_groq_client()
    uploaded_files = st.file_uploader("Upload resumes (PDF)", type=['pdf'], accept_multiple_files=True)
    job_description = st.text_area("Paste the job description here", height=200, help="Paste the complete job description including requirements and qualifications")
    
    results = []
    
    if uploaded_files and job_description:
        for uploaded_file in uploaded_files:
            st.subheader(f"Resume: {uploaded_file.name}")
            resume_text = extract_text_from_pdf(uploaded_file)
            if resume_text:
                candidate_name = extract_name(resume_text)
                total_experience = extract_experience(resume_text)
                degree, college = extract_college_and_degree(resume_text)
                
                st.write(f"**Candidate Name:** {candidate_name}")
                st.write(f"**Total Experience:** {total_experience} years")
                st.write(f"**Degree:** {degree}")
                st.write(f"**College/University:** {college}")
                
                if st.button(f"Analyze {uploaded_file.name}"):
                    with st.spinner(f"Analyzing {uploaded_file.name}..."):
                        analysis = analyze_resume(client, resume_text, job_description)
                        if analysis:
                            results.append([candidate_name, total_experience, degree, college, analysis])
    
    if results:
        df = pd.DataFrame(results, columns=["Candidate Name", "Total Experience", "Degree", "College/University", "Analysis"])
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

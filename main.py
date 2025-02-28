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
        lines = analysis.split('\n')
        for line in lines:
            if ':' in line:
                # Split on first colon
                parts = line.split(':', 1)
                key = parts[0].strip()
                value = parts[1].strip() if len(parts) > 1 else ""
                
                # Clean the value of markdown formatting
                value = clean_text(value)
                
                # Find matching key from our list
                matched_key = None
                for k in keys:
                    if key.lower() == k.lower() or k.lower() in key.lower():
                        matched_key = k
                        break
                
                if matched_key:
                    # Normalize keys to match our expected format
                    if matched_key == "Total Experience" or matched_key == "Total Experience (Years)":
                        # Extract just the number
                        value_words = value.split()
                        if value_words and value_words[0].isdigit():
                            result["Total Experience (Years)"] = value_words[0]
                        else:
                            result["Total Experience (Years)"] = value
                    elif matched_key == "Relevancy Score" or matched_key == "Relevancy Score (0-100)":
                        # Extract just the number
                        value_words = value.split()
                        if value_words and value_words[0].replace('.', '', 1).isdigit():
                            result["Relevancy Score (0-100)"] = value_words[0]
                        else:
                            result["Relevancy Score (0-100)"] = value
                    else:
                        result[matched_key] = value
        
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
        
        df = pd.DataFrame(results, columns=[
            "Candidate Name", "Total Experience (Years)", "Relevancy Score (0-100)", 
            "Strong Matches Score", "Partial Matches Score", "Missing Skills Score", 
            "Relevant Tech Skills", "Tech Stack", "Tech Stack Experience", "Degree", 
            "College/University"])
        
        # Display the dataframe
        st.dataframe(df)

        # Create a temporary file for download
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmpfile:
            # Using the standard pandas to_excel method without xlsxwriter
            df.to_excel(tmpfile.name, index=False, sheet_name='Resume Analysis')
            tmpfile_path = tmpfile.name

        st.success("Excel file created successfully!")
        
        # Offer the file for download
        with open(tmpfile_path, "rb") as file:
            st.download_button(
                label="📥 Download Excel Report",
                data=file,
                file_name=f"resume_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

        # Clean up the temporary file
        os.unlink(tmpfile_path)

if __name__ == "__main__":
    main()

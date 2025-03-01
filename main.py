import streamlit as st
from groq import Groq
import PyPDF2
import os
import re
from dotenv import load_dotenv
import io
from PIL import Image
import pytesseract
from pdf2image import convert_from_bytes

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

# Extract text from PDF using pdf2image and OCR
def extract_text_from_pdf_ocr(pdf_file):
    try:
        # Convert PDF to image
        images = convert_from_bytes(pdf_file.read())
        
        # Extract text from each image using OCR
        text = ""
        for img in images:
            img_text = pytesseract.image_to_string(img, lang='eng')
            text += img_text + "\n"
            
        return text if text else None
    except Exception as e:
        st.error(f"Error extracting text from PDF using OCR: {str(e)}")
        return None

# Extract text from image using OCR
def extract_text_from_image(image_file):
    try:
        image = Image.open(image_file)
        text = pytesseract.image_to_string(image, lang='eng')
        return text if text else None
    except Exception as e:
        st.error(f"Error extracting text from image: {str(e)}")
        return None

# Call AI model to analyze document and extract information
def analyze_document(client, document_text, document_type):
    # Use conditionals instead of f-strings with escaped characters for these sections
    if document_type.lower() == 'aadhar':
        number_field = "Aadhar Number: [extracted number]"
        address_field = "Address: [extracted address]"
        gender_field = "Gender: [extracted gender]"
    else:  # PAN
        number_field = "PAN Number: [extracted number]"
        address_field = "Father's Name: [extracted father's name if available]"
        gender_field = ""
    
    prompt = f"""
    As a document information extractor, analyze the following {document_type} card text and extract these specific fields:
    
    If the document is an Aadhar Card, extract:
    - Full Name
    - Aadhar Number (12 digits)
    - Address (complete address including state and pin code)
    - Date of Birth (in DD/MM/YYYY format)
    - Gender
    
    If the document is a PAN Card, extract:
    - Full Name
    - PAN Number (10 character alphanumeric)
    - Date of Birth (in DD/MM/YYYY format)
    - Father's Name (if available)
    
    Format your response EXACTLY as follows, with each field on a new line:
    Full Name: [extracted name]
    {number_field}
    {address_field}
    Date of Birth: [extracted DOB]
    {gender_field}
    
    If you cannot find a specific field, respond with "Not Found" for that field.
    Do not include any additional information or explanations in your response.
    
    Document Text:
    {document_text}
    """
    
    try:
        response = client.chat.completions.create(
            model="mixtral-8x7b-32768",  # Using Mixtral for better extraction capabilities
            messages=[
                {"role": "system", "content": "You are a document information extraction system. Your task is to accurately extract specific fields from identity documents like Aadhar and PAN cards. Be precise and follow the requested format exactly."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,  # Low temperature for more deterministic extraction
            max_tokens=1000
        )
        ai_response = response.choices[0].message.content
        
        # Debugging: Show AI response in Streamlit
        with st.expander("Raw AI Response Output (Debugging)"):
            st.text_area("Raw AI Response", ai_response, height=200)
        
        return ai_response
    except Exception as e:
        st.error(f"Error during analysis: {str(e)}")
        return None

# Parse the AI response to extract the key-value pairs
def parse_analysis(analysis, document_type):
    if not analysis:
        return {}
    
    # Define expected fields based on document type
    if document_type.lower() == 'aadhar':
        expected_fields = ["Full Name", "Aadhar Number", "Address", "Date of Birth", "Gender"]
    else:  # PAN
        expected_fields = ["Full Name", "PAN Number", "Father's Name", "Date of Birth"]
    
    result = {field: "Not Found" for field in expected_fields}
    
    # Extract values using regex
    lines = analysis.strip().split('\n')
    for line in lines:
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            
            if key in result and value and value != "Not Found":
                result[key] = value
    
    return result

# Detect document type (Aadhar or PAN) using AI
def detect_document_type(client, document_text):
    prompt = f"""
    Analyze the following document text and determine if it's an Aadhar Card or a PAN Card. 
    
    Characteristics of an Aadhar Card:
    - Contains a 12-digit Aadhar number
    - Has the UIDAI logo or mentions UIDAI
    - Contains a complete address
    - Usually has "Government of India" text
    
    Characteristics of a PAN Card:
    - Contains a 10-character PAN number (alphanumeric)
    - Usually has "Income Tax Department" or "Permanent Account Number" text
    - Often mentions "Government of India" or "भारत सरकार"
    - Contains "Date of Birth" but no address
    
    Document Text:
    {document_text}
    
    Respond with ONLY "Aadhar" or "PAN" (case sensitive, exactly as written).
    """
    
    try:
        response = client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[
                {"role": "system", "content": "You are a document classifier that can identify Indian identity documents."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=10
        )
        doc_type = response.choices[0].message.content.strip()
        
        # Validate response
        if doc_type not in ["Aadhar", "PAN"]:
            # Default to Aadhar if uncertain
            doc_type = "Aadhar"
        
        return doc_type
    except Exception as e:
        st.error(f"Error detecting document type: {str(e)}")
        return "Unknown"

# Main Streamlit App
def main():
    st.title("📄 Aadhar & PAN Card Information Extractor")
    st.write("Upload an Aadhar card or PAN card image/PDF to extract information")

    # Load environment variables
    load_dotenv()
    
    if not os.environ.get("GROQ_API_KEY"):
        st.error("GROQ_API_KEY not found. Please set it in your environment or .env file.")
        st.info("You can get a Groq API key at https://console.groq.com/")
        return
        
    client = initialize_groq_client()
    
    # Create tabs for different document types
    tab1, tab2 = st.tabs(["Auto-Detect Document", "Specify Document Type"])
    
    with tab1:
        st.subheader("Upload your document")
        uploaded_file = st.file_uploader("Upload Aadhar or PAN card (PDF or Image)", 
                                        type=['pdf', 'png', 'jpg', 'jpeg'], 
                                        key="auto_detect")
        
        if uploaded_file:
            with st.spinner("Processing document..."):
                file_extension = uploaded_file.name.split('.')[-1].lower()
                
                # Extract text based on file type
                if file_extension == 'pdf':
                    document_text = extract_text_from_pdf(uploaded_file)
                    
                    # If standard PDF extraction failed, try OCR
                    if not document_text or len(document_text) < 50:
                        st.info("Using OCR to extract text from PDF...")
                        uploaded_file.seek(0)  # Reset file pointer
                        document_text = extract_text_from_pdf_ocr(uploaded_file)
                else:  # Image file
                    document_text = extract_text_from_image(uploaded_file)
                
                if document_text:
                    # Show extracted raw text
                    with st.expander("Show Extracted Raw Text"):
                        st.text_area("Extracted Text", document_text, height=200)
                    
                    # Detect document type
                    document_type = detect_document_type(client, document_text)
                    st.info(f"Detected document type: {document_type} Card")
                    
                    # Extract information
                    analysis = analyze_document(client, document_text, document_type)
                    
                    if analysis:
                        extracted_info = parse_analysis(analysis, document_type)
                        
                        # Display extracted information in a nice format
                        st.subheader("📋 Extracted Information")
                        
                        # Create a nice looking card for the info
                        info_html = "<div style='background-color:#f0f2f6;padding:20px;border-radius:10px;'>"
                        for field, value in extracted_info.items():
                            info_html += f"<p><strong>{field}:</strong> {value}</p>"
                        info_html += "</div>"
                        
                        st.markdown(info_html, unsafe_allow_html=True)
                    else:
                        st.error("Failed to analyze the document.")
                else:
                    st.error("Could not extract text from the uploaded file. Please try another file.")
    
    with tab2:
        st.subheader("Upload your document with specific type")
        doc_type = st.radio("Select Document Type", ["Aadhar", "PAN"])
        uploaded_file = st.file_uploader("Upload document (PDF or Image)", 
                                        type=['pdf', 'png', 'jpg', 'jpeg'], 
                                        key="specific_type")
        
        if uploaded_file:
            with st.spinner(f"Processing {doc_type} card..."):
                file_extension = uploaded_file.name.split('.')[-1].lower()
                
                # Extract text based on file type
                if file_extension == 'pdf':
                    document_text = extract_text_from_pdf(uploaded_file)
                    
                    # If standard PDF extraction failed, try OCR
                    if not document_text or len(document_text) < 50:
                        st.info("Using OCR to extract text from PDF...")
                        uploaded_file.seek(0)  # Reset file pointer
                        document_text = extract_text_from_pdf_ocr(uploaded_file)
                else:  # Image file
                    document_text = extract_text_from_image(uploaded_file)
                
                if document_text:
                    # Show extracted raw text
                    with st.expander("Show Extracted Raw Text"):
                        st.text_area("Extracted Text", document_text, height=200)
                    
                    # Extract information
                    analysis = analyze_document(client, document_text, doc_type)
                    
                    if analysis:
                        extracted_info = parse_analysis(analysis, doc_type)
                        
                        # Display extracted information in a nice format
                        st.subheader("📋 Extracted Information")
                        
                        # Create a nice looking card for the info
                        info_html = "<div style='background-color:#f0f2f6;padding:20px;border-radius:10px;'>"
                        for field, value in extracted_info.items():
                            info_html += f"<p><strong>{field}:</strong> {value}</p>"
                        info_html += "</div>"
                        
                        st.markdown(info_html, unsafe_allow_html=True)
                    else:
                        st.error("Failed to analyze the document.")
                else:
                    st.error("Could not extract text from the uploaded file. Please try another file.")

    # Add information about the app
    st.markdown("---")
    st.subheader("ℹ️ About this app")
    st.write("""
    This application extracts information from Aadhar and PAN cards using OCR and AI technology.
    The extracted information is presented directly in the app.
    
    **Note:** All processing is done securely, and no data is stored by this application.
    
    **Requirements:**
    - Python packages: streamlit, groq, python-dotenv, pytesseract, pdf2image, Pillow, PyPDF2
    - Tesseract OCR must be installed on the system
    - A valid Groq API key must be set in the .env file or environment variables
    """)

if __name__ == "__main__":
    main()

import streamlit as st
from groq import Groq
import PyPDF2
import os
import re
from dotenv import load_dotenv
import io
from PIL import Image
from google.cloud import vision
from google.oauth2 import service_account
import tempfile

# Initialize AI client
def initialize_groq_client():
    return Groq(api_key=os.environ.get("GROQ_API_KEY"))

# Initialize Google Cloud Vision client
def initialize_vision_client():
    # Check if credentials file exists or use service account info from env
    if os.path.exists("google_credentials.json"):
        credentials = service_account.Credentials.from_service_account_file("google_credentials.json")
    elif os.environ.get("GOOGLE_CREDENTIALS"):
        # Load credentials from environment variable
        import json
        service_account_info = json.loads(os.environ.get("GOOGLE_CREDENTIALS"))
        credentials = service_account.Credentials.from_service_account_info(service_account_info)
    else:
        st.error("Google Cloud credentials not found. Set up google_credentials.json or GOOGLE_CREDENTIALS env variable.")
        return None
    
    return vision.ImageAnnotatorClient(credentials=credentials)

# Extract text from PDF using PyPDF2 (for text-based PDFs)
def extract_text_from_pdf(pdf_file):
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = "\n".join([page.extract_text() for page in pdf_reader.pages if page.extract_text()])
        return text if text else None
    except Exception as e:
        st.error(f"Error extracting text from PDF: {str(e)}")
        return None

# Extract text from PDF using Google Cloud Vision (for scanned PDFs)
def extract_text_from_pdf_ocr(pdf_file, vision_client):
    try:
        from pdf2image import convert_from_bytes
        
        # Create a temporary file to store the PDF content
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
            temp_pdf.write(pdf_file.read())
            temp_pdf_path = temp_pdf.name
        
        try:
            # Convert PDF to images
            images = convert_from_bytes(open(temp_pdf_path, 'rb').read())
            
            # Extract text from each image using Cloud Vision
            full_text = ""
            for img in images:
                with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_img:
                    img.save(temp_img, format='JPEG')
                    temp_img_path = temp_img.name
                
                # Use Cloud Vision to extract text
                with open(temp_img_path, 'rb') as image_file:
                    content = image_file.read()
                
                image = vision.Image(content=content)
                response = vision_client.text_detection(image=image)
                page_text = response.text_annotations[0].description if response.text_annotations else ""
                full_text += page_text + "\n"
                
                # Clean up the temporary image file
                os.unlink(temp_img_path)
                
            # Clean up the temporary PDF file
            os.unlink(temp_pdf_path)
            
            return full_text if full_text else None
            
        except Exception as inner_e:
            st.error(f"Error processing PDF images: {str(inner_e)}")
            # Clean up the temporary PDF file
            os.unlink(temp_pdf_path)
            return None
            
    except Exception as e:
        st.error(f"Error extracting text from PDF using OCR: {str(e)}")
        return None

# Extract text from image using Google Cloud Vision
def extract_text_from_image(image_file, vision_client):
    try:
        # Convert the uploaded file to bytes
        image_content = image_file.read()
        
        # Create image object
        image = vision.Image(content=image_content)
        
        # Perform text detection
        response = vision_client.text_detection(image=image)
        
        # Extract text from response
        if response.text_annotations:
            text = response.text_annotations[0].description
            return text
        else:
            return None
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
    
    # Initialize clients
    groq_client = initialize_groq_client()
    vision_client = initialize_vision_client()
    
    if not vision_client:
        st.warning("Google Cloud Vision client could not be initialized. Some OCR features may be limited.")
        st.info("To use Google Cloud Vision, set up authentication credentials - see documentation below.")
    
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
                        st.info("Using Cloud OCR to extract text from PDF...")
                        uploaded_file.seek(0)  # Reset file pointer
                        if vision_client:
                            document_text = extract_text_from_pdf_ocr(uploaded_file, vision_client)
                        else:
                            st.error("Cloud OCR not available. Please set up Google Cloud Vision credentials.")
                            return
                else:  # Image file
                    if vision_client:
                        document_text = extract_text_from_image(uploaded_file, vision_client)
                    else:
                        st.error("Cloud OCR not available. Please set up Google Cloud Vision credentials.")
                        return
                
                if document_text:
                    # Show extracted raw text
                    with st.expander("Show Extracted Raw Text"):
                        st.text_area("Extracted Text", document_text, height=200)
                    
                    # Detect document type
                    document_type = detect_document_type(groq_client, document_text)
                    st.info(f"Detected document type: {document_type} Card")
                    
                    # Extract information
                    analysis = analyze_document(groq_client, document_text, document_type)
                    
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
                        st.info("Using Cloud OCR to extract text from PDF...")
                        uploaded_file.seek(0)  # Reset file pointer
                        if vision_client:
                            document_text = extract_text_from_pdf_ocr(uploaded_file, vision_client)
                        else:
                            st.error("Cloud OCR not available. Please set up Google Cloud Vision credentials.")
                            return
                else:  # Image file
                    if vision_client:
                        document_text = extract_text_from_image(uploaded_file, vision_client)
                    else:
                        st.error("Cloud OCR not available. Please set up Google Cloud Vision credentials.")
                        return
                
                if document_text:
                    # Show extracted raw text
                    with st.expander("Show Extracted Raw Text"):
                        st.text_area("Extracted Text", document_text, height=200)
                    
                    # Extract information
                    analysis = analyze_document(groq_client, document_text, doc_type)
                    
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
    This application extracts information from Aadhar and PAN cards using Google Cloud Vision OCR and AI technology.
    The extracted information is presented directly in the app.
    
    **Note:** All processing is done securely, and no data is stored by this application.
    
    **Requirements:**
    - Python packages: streamlit, groq, python-dotenv, Pillow, PyPDF2, google-cloud-vision, pdf2image
    - A valid Groq API key must be set in the .env file or environment variables
    - Google Cloud Vision API credentials (either as a JSON file or in environment variables)
    """)
    
    # Add setup instructions for Google Cloud Vision
    with st.expander("Google Cloud Vision Setup Instructions"):
        st.markdown("""
        ### Setting up Google Cloud Vision API
        
        1. **Create a Google Cloud account** if you don't already have one
        2. **Create a new project** in the Google Cloud Console
        3. **Enable the Vision API** for your project
        4. **Create a service account** with "Vision AI Client" role
        5. **Download the JSON credentials file** for your service account
        6. **Place the credentials file** in the same directory as this app with the name `google_credentials.json`
        
        Alternatively, you can set the credentials as an environment variable:
        
        ```bash
        # For Linux/macOS
        export GOOGLE_CREDENTIALS='{"type":"service_account", ... copy entire JSON content here ...}'
        
        # For Windows (Command Prompt)
        set GOOGLE_CREDENTIALS={"type":"service_account", ... copy entire JSON content here ...}
        
        # For Windows (PowerShell)
        $env:GOOGLE_CREDENTIALS='{"type":"service_account", ... copy entire JSON content here ...}'
        ```
        
        For more details, visit the [Google Cloud Vision API documentation](https://cloud.google.com/vision/docs/setup).
        """)

if __name__ == "__main__":
    main()

import streamlit as st
from groq import Groq
import PyPDF2
import os
import re
from dotenv import load_dotenv
import io
from PIL import Image
import requests
import tempfile
import json
from pdf2image import convert_from_bytes

# Initialize AI client
def initialize_groq_client():
    return Groq(api_key=os.environ.get("GROQ_API_KEY"))

# Extract text from PDF using PyPDF2 (for text-based PDFs)
def extract_text_from_pdf(pdf_file):
    try:
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = "\n".join([page.extract_text() for page in pdf_reader.pages if page.extract_text()])
        return text if text else None
    except Exception as e:
        st.error(f"Error extracting text from PDF: {str(e)}")
        return None

# Extract text using pytesseract (no API key required)
def extract_text_using_pytesseract(image_file):
    try:
        # Import pytesseract
        import pytesseract
        from PIL import Image
        
        # Open the image file
        image = Image.open(image_file)
        
        # Extract text using pytesseract
        text = pytesseract.image_to_string(image, lang='eng')
        
        return text if text else None
    except ImportError:
        st.error("pytesseract is not installed. Using built-in text extraction.")
        return extract_text_fallback(image_file)
    except Exception as e:
        st.error(f"Error using pytesseract OCR: {str(e)}")
        return extract_text_fallback(image_file)

# Fallback text extraction using PIL's built-in capabilities
def extract_text_fallback(image_file):
    try:
        # Use Streamlit's built-in image recognition capabilities
        st.info("Using built-in image processing. Results may be limited.")
        
        # Display the image
        image = Image.open(image_file)
        st.image(image, caption="Uploaded Document", use_column_width=True)
        
        # Since we can't extract text without OCR, provide a manual input option
        st.warning("Automated text extraction is unavailable. Please enter the text from the document manually.")
        manual_text = st.text_area("Enter document text manually:", height=150, key="fallback_manual_text")
        
        if manual_text:
            return manual_text
        else:
            st.error("Manual text input required for analysis.")
            return None
    except Exception as e:
        st.error(f"Error processing image: {str(e)}")
        return None

# Extract text from PDF using pytesseract
def extract_text_from_pdf_ocr(pdf_file):
    try:
        # Create a temporary file to store the PDF content
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
            temp_pdf.write(pdf_file.read())
            temp_pdf_path = temp_pdf.name
        
        try:
            # Convert PDF to images
            images = convert_from_bytes(open(temp_pdf_path, 'rb').read())
            
            # Extract text from each image using pytesseract
            full_text = ""
            for i, img in enumerate(images):
                with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_img:
                    img.save(temp_img, format='JPEG')
                    img_path = temp_img.name
                
                # Open the image and use pytesseract
                with open(img_path, 'rb') as image_file:
                    img_text = extract_text_using_pytesseract(image_file)
                    if img_text:
                        full_text += img_text + "\n"
                
                # Clean up the temporary image file
                os.unlink(img_path)
            
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
            st.text_area("Raw AI Response", ai_response, height=200, key="raw_ai_response")
        
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
        
        # Provide option for manual key entry
        manual_key = st.text_input("Enter your Groq API key:", type="password", key="manual_groq_key")
        if manual_key:
            os.environ["GROQ_API_KEY"] = manual_key
            st.success("API key set for this session!")
        else:
            return
    
    # Initialize Groq client
    groq_client = initialize_groq_client()
    
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
                    document_text = extract_text_using_pytesseract(uploaded_file)
                
                if document_text:
                    # Show extracted raw text
                    with st.expander("Show Extracted Raw Text"):
                        st.text_area("Extracted Text", document_text, height=200, key="tab1_extracted_text")
                    
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
                    st.error("Could not extract text from the uploaded file.")
                    
                    # Offer manual text input as fallback
                    st.info("As a fallback, you can manually enter the text from your document.")
                    manual_text = st.text_area("Enter document text manually:", height=150, key="tab1_manual_text")
                    
                    if manual_text and st.button("Process Manual Text", key="tab1_process_button"):
                        # Detect document type
                        document_type = detect_document_type(groq_client, manual_text)
                        st.info(f"Detected document type: {document_type} Card")
                        
                        # Extract information
                        analysis = analyze_document(groq_client, manual_text, document_type)
                        
                        if analysis:
                            extracted_info = parse_analysis(analysis, document_type)
                            
                            # Display extracted information in a nice format
                            st.subheader("📋 Extracted Information")
                            
                            info_html = "<div style='background-color:#f0f2f6;padding:20px;border-radius:10px;'>"
                            for field, value in extracted_info.items():
                                info_html += f"<p><strong>{field}:</strong> {value}</p>"
                            info_html += "</div>"
                            
                            st.markdown(info_html, unsafe_allow_html=True)
                        else:
                            st.error("Failed to analyze the manual text.")
    
    with tab2:
        st.subheader("Upload your document with specific type")
        doc_type = st.radio("Select Document Type", ["Aadhar", "PAN"], key="document_type_radio")
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
                    document_text = extract_text_using_pytesseract(uploaded_file)
                
                if document_text:
                    # Show extracted raw text
                    with st.expander("Show Extracted Raw Text"):
                        st.text_area("Extracted Text", document_text, height=200, key="tab2_extracted_text")
                    
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
                    st.error("Could not extract text from the uploaded file.")
                    
                    # Offer manual text input as fallback
                    st.info("As a fallback, you can manually enter the text from your document.")
                    manual_text = st.text_area("Enter document text manually:", height=150, key="tab2_manual_text")
                    
                    if manual_text and st.button("Process Manual Text", key="tab2_process_button"):
                        # Extract information
                        analysis = analyze_document(groq_client, manual_text, doc_type)
                        
                        if analysis:
                            extracted_info = parse_analysis(analysis, doc_type)
                            
                            # Display extracted information in a nice format
                            st.subheader("📋 Extracted Information")
                            
                            info_html = "<div style='background-color:#f0f2f6;padding:20px;border-radius:10px;'>"
                            for field, value in extracted_info.items():
                                info_html += f"<p><strong>{field}:</strong> {value}</p>"
                            info_html += "</div>"
                            
                            st.markdown(info_html, unsafe_allow_html=True)
                        else:
                            st.error("Failed to analyze the manual text.")

    # Add information about the app
    st.markdown("---")
    st.subheader("ℹ️ About this app")
    st.write("""
    This application extracts information from Aadhar and PAN cards using OCR and AI technology.
    The extracted information is presented directly in the app.
    
    **Note:** All processing is done securely, and no data is stored by this application.
    
    **Requirements:**
    - Python packages: streamlit, groq, python-dotenv, Pillow, PyPDF2, pdf2image
    - A valid Groq API key must be set in the .env file, environment variables, or entered manually
    - For optimal OCR performance:
      - Tesseract OCR (pip install pytesseract) and Tesseract installed on your system
      - Or you can use the manual text input option as a fallback
    """)
    
    # Add setup instructions for Tesseract
    with st.expander("Tesseract OCR Setup Instructions"):
        st.markdown("""
        ### Setting up Tesseract OCR
        
        Tesseract is a free and open-source OCR engine that you can install locally:
        
        1. **Install Tesseract OCR on your system**:
        
           - **Windows**: Download and install from [https://github.com/UB-Mannheim/tesseract/wiki](https://github.com/UB-Mannheim/tesseract/wiki)
           - **macOS**: `brew install tesseract`
           - **Linux**: `sudo apt install tesseract-ocr`
        
        2. **Install the Python wrapper**:
        
           ```bash
           pip install pytesseract
           ```
        
        3. **Make sure Tesseract is in your PATH**
        
           For Windows, you might need to point to the Tesseract executable:
           
           ```python
           import pytesseract
           pytesseract.pytesseract.tesseract_cmd = r'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'
           ```
           
           You can add this line to your code if needed.
        """)
    
    # Add manual input instructions
    with st.expander("Using Manual Text Input"):
        st.markdown("""
        ### Using Manual Text Input
        
        If automated OCR isn't working well, you can use the manual text input feature:
        
        1. Upload your document (this allows the app to try automated extraction first)
        2. If extraction fails, you'll see a text area where you can manually type or paste the text
        3. Click "Process Manual Text" to analyze the text you entered
        4. The app will then extract and display the information
        
        This is a good fallback option when dealing with:
        - Low-quality images
        - Complex document layouts
        - Cases where OCR is having difficulty
        """)

if __name__ == "__main__":
    main()

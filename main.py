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

# Enhanced OCR using pytesseract with improved preprocessing
def extract_text_using_pytesseract(image_file):
    try:
        # Import necessary libraries
        import pytesseract
        from PIL import Image, ImageEnhance, ImageFilter
        import numpy as np
        import cv2
        
        # Open the image file
        image = Image.open(image_file)
        
        # Display original image
        st.image(image, caption="Original Document", use_container_width=True)
        
        # Convert to OpenCV format for preprocessing
        img_cv = np.array(image)
        
        # Convert to grayscale
        if len(img_cv.shape) == 3:  # Color image
            gray = cv2.cvtColor(img_cv, cv2.COLOR_RGB2GRAY)
        else:
            gray = img_cv
            
        # Apply threshold to get black and white image
        _, binary = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        # Apply some noise reduction
        denoised = cv2.fastNlMeansDenoising(binary, None, 10, 7, 21)
        
        # Convert back to PIL Image and enhance contrast
        enhanced_img = Image.fromarray(denoised)
        enhancer = ImageEnhance.Contrast(enhanced_img)
        enhanced_img = enhancer.enhance(2)
        
        # Display enhanced image
        st.image(enhanced_img, caption="Enhanced Image for OCR", use_container_width=True)
        
        # Use multiple OCR configurations to improve extraction
        custom_config = r'--oem 3 --psm 6 -l eng'
        text1 = pytesseract.image_to_string(enhanced_img, config=custom_config)
        
        custom_config2 = r'--oem 3 --psm 3 -l eng'
        text2 = pytesseract.image_to_string(enhanced_img, config=custom_config2)
        
        # Combine texts from different OCR configurations
        text = text1 + "\n" + text2
        
        return text if text else None
    except ImportError:
        st.warning("pytesseract or CV2 is not installed. Using alternative text extraction.")
        return extract_text_fallback(image_file)
    except Exception as e:
        st.error(f"Error using pytesseract OCR: {str(e)}")
        return extract_text_fallback(image_file)

# Fallback text extraction using PIL's built-in capabilities
def extract_text_fallback(image_file):
    try:
        # Display the image
        image = Image.open(image_file)
        st.image(image, caption="Uploaded Document", use_container_width=True)
        
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

# Extract text from PDF using pytesseract with enhanced processing
def extract_text_from_pdf_ocr(pdf_file):
    try:
        # Create a temporary file to store the PDF content
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
            temp_pdf.write(pdf_file.read())
            temp_pdf_path = temp_pdf.name
        
        try:
            # Convert PDF to images with higher DPI for better quality
            images = convert_from_bytes(open(temp_pdf_path, 'rb').read(), dpi=300)
            
            # Extract text from each image using pytesseract
            full_text = ""
            for i, img in enumerate(images):
                with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as temp_img:
                    img.save(temp_img, format='JPEG', quality=95)
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

# Call AI model to analyze document and extract information with improved prompting
def analyze_document(client, document_text, document_type):
    prompt = f"""
    As a document information extractor, carefully analyze the following {document_type} card text and extract these specific fields.
    
    IMPORTANT: Pay special attention to extracting Full Name, Date of Birth, and Father's Name (for PAN) or Address (for Aadhar).
    Look for patterns like:
    - Names are typically in all caps or title case
    - DOB format is usually DD/MM/YYYY or DD-MM-YYYY
    - Names often have designations like "S/O" (Son of), "D/O" (Daughter of), or "W/O" (Wife of) preceding Father's name
    - Father's name might appear after phrases like "S/O", "Father's name", "नाम", etc.
    
    If the document is an Aadhar Card, extract:
    - Full Name: Look for the most prominent name on the card
    - Aadhar Number: 12 digits, often with spaces like XXXX XXXX XXXX
    - Address: Complete address including state and pin code
    - Date of Birth: Format DD/MM/YYYY
    - Gender: Male/Female/Other
    
    If the document is a PAN Card, extract:
    - Full Name: Look for the most prominent name in capital letters
    - PAN Number: 10 character alphanumeric code (like ABCDE1234F)
    - Date of Birth: Format DD/MM/YYYY 
    - Father's Name: Usually listed after the primary name
    
    Format your response EXACTLY as follows, with each field on a new line:
    Full Name: [extracted name]
    {document_type} Number: [extracted number]
    {"Address: [extracted address]" if document_type.lower() == 'aadhar' else "Father's Name: [extracted father's name]"}
    Date of Birth: [extracted DOB]
    {"Gender: [extracted gender]" if document_type.lower() == 'aadhar' else ""}
    
    If you cannot find a specific field with high confidence, respond with "Not Found" for that field.
    
    Document Text:
    {document_text}
    """
    
    try:
        response = client.chat.completions.create(
            model="mixtral-8x7b-32768",  # Using Mixtral for better extraction capabilities
            messages=[
                {"role": "system", "content": "You are a document information extraction expert specialized in Indian identity documents. Your primary goal is to accurately extract personal information from text, especially names, dates of birth, and relationships. Even if the text is messy from OCR, you're skilled at identifying patterns that indicate personal information."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,  # Very low temperature for more deterministic extraction
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

# Enhanced parsing function with better regex patterns
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
            parts = line.split(':', 1)
            if len(parts) == 2:
                key, value = parts
                key = key.strip()
                value = value.strip()
                
                # Special handling for father's name which might be missed or misformatted
                if "father" in key.lower() and document_type.lower() == 'pan':
                    result["Father's Name"] = value if value and value != "Not Found" else "Not Found"
                # Special handling for other fields
                elif key in result and value and value != "Not Found":
                    result[key] = value
    
    # If certain critical fields were not found, try to extract them using regex patterns
    if document_text and (result["Full Name"] == "Not Found" or 
                         result["Date of Birth"] == "Not Found" or 
                         (document_type.lower() == 'pan' and result["Father's Name"] == "Not Found")):
        
        # Try to find name patterns
        if result["Full Name"] == "Not Found":
            name_patterns = [
                r'Name\s*:\s*([A-Z][a-zA-Z\s\.]+)',
                r'NAME\s*:\s*([A-Z][a-zA-Z\s\.]+)',
                r'([A-Z]{2,}\s+[A-Z]{2,}(?:\s+[A-Z]{2,})?)'
            ]
            for pattern in name_patterns:
                matches = re.search(pattern, document_text)
                if matches:
                    result["Full Name"] = matches.group(1).strip()
                    break
        
        # Try to find DOB patterns
        if result["Date of Birth"] == "Not Found":
            dob_patterns = [
                r'(?:DOB|Date of Birth|बर्थ|DOB|Birth)[\s:]*(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
                r'(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})'
            ]
            for pattern in dob_patterns:
                matches = re.search(pattern, document_text)
                if matches:
                    result["Date of Birth"] = matches.group(1).strip()
                    break
        
        # Try to find father's name patterns for PAN
        if document_type.lower() == 'pan' and result["Father's Name"] == "Not Found":
            father_patterns = [
                r'(?:Father|S/O|D/O|W/O|Son of|Daughter of|Wife of)[\'s]*\s*(?:Name\s*)?[:]*\s*([A-Z][a-zA-Z\s\.]+)',
                r'(?:पिता|फादर).*?[:]*\s*([A-Z][a-zA-Z\s\.]+)'
            ]
            for pattern in father_patterns:
                matches = re.search(pattern, document_text, re.IGNORECASE)
                if matches:
                    result["Father's Name"] = matches.group(1).strip()
                    break
    
    return result

# Detect document type with improved patterns
def detect_document_type(client, document_text):
    prompt = f"""
    Analyze the following document text and determine if it's an Aadhar Card or a PAN Card. 
    
    Characteristics of an Aadhar Card:
    - Contains a 12-digit Aadhar number (possibly with spaces like XXXX XXXX XXXX)
    - Has the UIDAI logo or mentions UIDAI
    - Contains a complete address including state and pincode
    - Usually has "Government of India" or "भारत सरकार" text
    - Often has the phrase "Unique Identification Authority of India"
    
    Characteristics of a PAN Card:
    - Contains a 10-character PAN number (alphanumeric with format like ABCDE1234F)
    - Usually has "Income Tax Department" or "Permanent Account Number" text
    - Often mentions "Government of India" or "भारत सरकार"
    - Contains "Date of Birth" but usually no address
    - May contain "PAN" or "Permanent Account Number" text
    
    Document Text:
    {document_text}
    
    Respond with ONLY "Aadhar" or "PAN" (case sensitive, exactly as written).
    """
    
    try:
        response = client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[
                {"role": "system", "content": "You are a document classifier specialized in identifying Indian identity documents."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=10
        )
        doc_type = response.choices[0].message.content.strip()
        
        # Validate response
        if doc_type not in ["Aadhar", "PAN"]:
            # Try to detect based on patterns
            if re.search(r'\b\d{4}\s?\d{4}\s?\d{4}\b', document_text) or "uidai" in document_text.lower():
                doc_type = "Aadhar"
            elif re.search(r'\b[A-Z]{5}\d{4}[A-Z]\b', document_text):
                doc_type = "PAN"
            else:
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
        
        # Add global variable to store document text for parsing
        document_text = None
        
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
    - For enhanced OCR: pytesseract, opencv-python
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
        
        2. **Install the Python wrapper and OpenCV for image processing**:
        
           ```bash
           pip install pytesseract opencv-python
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

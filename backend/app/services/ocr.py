
import io
import os
import json
import traceback
from typing import Optional
from google.cloud import vision
from pdf2image import convert_from_path

# Explicit Poppler path for Windows (avoids PATH resolution issues when server
# starts before PATH changes take effect in the current session)
POPPLER_PATH = r"C:\Users\dnyan\poppler\poppler-24.08.0\Library\bin"


try:
    from google.genai import Client as GeminiClient
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️  google-genai not installed")

import ssl
import certifi

# Fix for Windows SSL context
os.environ['SSL_CERT_FILE'] = certifi.where()

from app.core.config import settings

from app.models.schemas import BillData, BillItem

class GoogleVisionOCR:
    """Extract text from images using Google Cloud Vision"""
    
    def __init__(self):
        # Ensure credentials are set
        if not settings.GOOGLE_APPLICATION_CREDENTIALS:
             print(f"⚠️  Warning: GOOGLE_APPLICATION_CREDENTIALS not set")
             self.client = None
             return

        try:
             # Using the path from settings directly might work if the env var is set for the process
             # But the library usually looks for the env var GOOGLE_APPLICATION_CREDENTIALS
             # So we must ensure os.environ has it.
             if settings.GOOGLE_APPLICATION_CREDENTIALS:
                 os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.GOOGLE_APPLICATION_CREDENTIALS
            
             self.client = vision.ImageAnnotatorClient()
        except Exception as e:
            print(f"⚠️  Warning: Could not initialize Vision API: {e}")
            self.client = None
    
    def extract_text_from_image(self, image_path: str) -> str:
        """Extract raw text from image"""
        if not self.client:
            raise Exception("Vision API client not initialized. Check GOOGLE_APPLICATION_CREDENTIALS")
        
        with io.open(image_path, 'rb') as image_file:
            content = image_file.read()
        
        image = vision.Image(content=content)
        response = self.client.document_text_detection(image=image)
        
        if response.error.message:
            raise Exception(f"Vision API error: {response.error.message}")
        
        text = response.full_text_annotation.text
        return text if text else ""
    
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF"""
        try:
            # Pass poppler_path explicitly for Windows compatibility
            poppler_path = POPPLER_PATH if os.path.isdir(POPPLER_PATH) else None
            images = convert_from_path(pdf_path, first_page=1, last_page=5, poppler_path=poppler_path)
        except Exception as e:
            raise Exception(f"PDF conversion failed: {e}. Make sure poppler is installed.")
        
        all_text = []
        
        for i, image in enumerate(images):
            temp_path = f"temp_page_{i}.png"
            try:
                image.save(temp_path, 'PNG')
                text = self.extract_text_from_image(temp_path)
                if text:
                    all_text.append(f"--- Page {i+1} ---\n{text}")
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        
        return "\n\n".join(all_text)


def _repair_truncated_json(text: str) -> str:
    """
    Best-effort repair of a JSON string that was cut off mid-output.
    Closes any unclosed string literals, arrays, and objects so that
    json.loads() has a fighting chance.
    """
    # Remove trailing comma before closing (common truncation artifact)
    text = text.rstrip().rstrip(",")

    # Count open vs closed brackets
    stack = []
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()

    # Close any unclosed string
    if in_string:
        text += '"'

    # Close any unclosed containers in reverse order
    text += "".join(reversed(stack))
    return text


class GeminiStructurer:
    """Use Gemini 2.0 Flash to structure OCR text into bill data"""
    
    # gemini-2.5-flash is the free-tier model
    MODEL = "gemini-2.5-flash"

    def __init__(self):

        self.client = None
        if settings.GOOGLE_API_KEY and GEMINI_AVAILABLE:
            try:
                # Temporarily unset GOOGLE_APPLICATION_CREDENTIALS to force API key usage if there's a conflict
                creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
                if creds_path:
                    del os.environ["GOOGLE_APPLICATION_CREDENTIALS"]

                try:
                    self.client = GeminiClient(api_key=settings.GOOGLE_API_KEY)
                    print("✓ Gemini client initialized")
                finally:
                    # Restore credentials for Vision API
                    if creds_path:
                        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
                        
            except Exception as e:
                print(f"⚠️  Failed to initialize Gemini: {e}")
                traceback.print_exc()
        else:
             print(f"⚠️  Warning: Gemini client not initialized (Key: {bool(settings.GOOGLE_API_KEY)}, Lib: {GEMINI_AVAILABLE})")

    
    def structure_bill_text(self, raw_text: str) -> BillData:
        """Convert raw OCR text into structured bill data"""
        
        if not self.client:
            raise Exception("Gemini client not initialized. Check GOOGLE_API_KEY")
        
        prompt = f"""You are analyzing raw text extracted from a medical bill using OCR. The text may have errors or formatting issues.

RAW OCR TEXT:
{raw_text}

Extract and structure this information into JSON format:

1. Hospital name (clean up OCR errors)
2. Hospital address
3. Patient name
4. Bill number
5. Bill date (format: YYYY-MM-DD, be flexible with date formats)
6. Admission date (format: YYYY-MM-DD if available)
7. Discharge date (format: YYYY-MM-DD if available)
8. Total amount (numeric only, no currency symbols)
9. Advance paid (numeric)
10. Balance amount (numeric)
11. Pre-auth / Insurance Approval Amount (numeric, look for 'Authorization', 'Approved', 'Pre-auth')
12. ALL itemized charges with:
    - description (clean, readable)
    - quantity (numeric)
    - unit_price (numeric if available)
    - total_price (numeric)
    - category: one of [Medicine, Procedure, Consultation, Room, Consumable, Test, ICU, Emergency, Other]

CRITICAL INSTRUCTIONS:
- Handle OCR errors intelligently (0↔O, 1↔I, 5↔S, etc.)
- Convert Indian number formats: 1,50,000 → 150000
- Extract ALL line items, not just major ones
- Use null for truly missing values
- Clean up hospital names (remove extra spaces, fix case)
- Categorize items based on medical terminology
- Return ONLY valid JSON, no markdown formatting, no explanations

Return this EXACT JSON structure:
{{
  "hospital_name": "...",
  "hospital_address": "...",
  "patient_name": "...",
  "bill_number": "...",
  "bill_date": "YYYY-MM-DD",
  "admission_date": "YYYY-MM-DD",
  "discharge_date": "YYYY-MM-DD",
  "total_amount": 0.0,
  "advance_paid": 0.0,
  "balance_amount": 0.0,
  "pre_auth_amount": 0.0,
  "items": [
    {{
      "description": "...",
      "quantity": 1.0,
      "unit_price": 0.0,
      "total_price": 0.0,
      "category": "..."
    }}
  ]
}}"""

        try:
            from google.genai import types as genai_types
            response = self.client.models.generate_content(
                model=self.MODEL,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    max_output_tokens=8192,
                    temperature=0.1,   # low = deterministic, fewer hallucinations
                )
            )

            response_text = response.text.strip()

            # Strip markdown code fences if present
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            response_text = response_text.strip()

            # ── Parse JSON with truncation repair ───────────────────────────────
            try:
                extracted_data = json.loads(response_text)
            except json.JSONDecodeError:
                print("   ⚠️  JSON appears truncated — attempting repair...")
                response_text = _repair_truncated_json(response_text)
                try:
                    extracted_data = json.loads(response_text)
                    print("   ✓ JSON repaired successfully")
                except json.JSONDecodeError as e2:
                    raise Exception(
                        f"Gemini returned invalid JSON (repair failed): {e2}\n"
                        f"Response: {response_text[:500]}"
                    )

            # Convert to BillData
            items = [
                BillItem(
                    description=item.get('description', ''),
                    quantity=float(item.get('quantity', 1.0)) if item.get('quantity') else 1.0,
                    unit_price=float(item.get('unit_price', 0)) if item.get('unit_price') else None,
                    total_price=float(item.get('total_price', 0)),
                    category=item.get('category')
                )
                for item in extracted_data.get('items', [])
            ]

            total_amount = float(extracted_data.get('total_amount', 0) or 0)
            # If Gemini returned 0 but we have itemized charges, sum them as fallback
            if total_amount == 0 and items:
                total_amount = sum(i.total_price for i in items)
                print(f"   ⚠️  total_amount was 0, using items sum: ₹{total_amount:,.0f}")

            bill_data = BillData(
                hospital_name=extracted_data.get('hospital_name', 'Unknown Hospital'),
                hospital_address=extracted_data.get('hospital_address'),
                patient_name=extracted_data.get('patient_name'),
                bill_number=extracted_data.get('bill_number'),
                bill_date=extracted_data.get('bill_date'),
                admission_date=extracted_data.get('admission_date'),
                discharge_date=extracted_data.get('discharge_date'),
                total_amount=total_amount,
                advance_paid=float(extracted_data.get('advance_paid', 0)) if extracted_data.get('advance_paid') else 0.0,
                balance_amount=float(extracted_data.get('balance_amount', 0)) if extracted_data.get('balance_amount') else None,
                pre_auth_amount=float(extracted_data.get('pre_auth_amount', 0)) if extracted_data.get('pre_auth_amount') else None,
                items=items
            )

            return bill_data

        except Exception as e:
            if 'Gemini returned invalid JSON' in str(e) or 'Gemini processing failed' in str(e):
                raise
            raise Exception(f"Gemini processing failed: {e}")


class HybridOCR:
    """Combines Google Vision OCR + Gemini structuring"""
    
    def __init__(self):
        self.vision_ocr = GoogleVisionOCR()
        self.gemini_structurer = GeminiStructurer()
    
    def extract_from_image(self, image_path: str) -> BillData:
        """Extract structured bill from image"""
        print("📄 Step 1/2: Extracting text with Google Vision OCR...")
        raw_text = self.vision_ocr.extract_text_from_image(image_path)
        print(f"   ✓ Extracted {len(raw_text)} characters")
        
        if not raw_text or len(raw_text) < 50:
            raise Exception("OCR extracted very little text. Image may be unclear or empty.")
        
        print("🤖 Step 2/2: Structuring with Gemini 2.0 Flash...")
        bill_data = self.gemini_structurer.structure_bill_text(raw_text)
        print("   ✓ Successfully structured bill data")
        
        return bill_data
    
    def extract_from_pdf(self, pdf_path: str) -> BillData:
        """Extract structured bill from PDF"""
        print("📄 Step 1/2: Extracting text from PDF with Google Vision OCR...")
        raw_text = self.vision_ocr.extract_text_from_pdf(pdf_path)
        print(f"   ✓ Extracted {len(raw_text)} characters from PDF")
        
        if not raw_text or len(raw_text) < 50:
            raise Exception("OCR extracted very little text from PDF. File may be corrupted or empty.")
        
        print("🤖 Step 2/2: Structuring with Gemini 2.0 Flash...")
        bill_data = self.gemini_structurer.structure_bill_text(raw_text)
        print("   ✓ Successfully structured bill data")
        
        return bill_data

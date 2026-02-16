"""
Medical Bill Analyzer - Complete Backend with Semantic Matching
Google Cloud Vision OCR + Gemini 2.0 Flash + Semantic Embeddings for Rate Matching
"""

from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from contextlib import asynccontextmanager
import json
import os
import io
import uvicorn
from pathlib import Path
from geopy.distance import geodesic
from fuzzywuzzy import fuzz
try:
    from google.genai import Client as GeminiClient
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️  google-genai not installed")
from google.cloud import vision
from pdf2image import convert_from_path
import shutil
import traceback
import math

# Semantic matching imports
from sentence_transformers import SentenceTransformer
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity


# Load environment variables
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True))
print("Loaded .env")


# ============================================================================
# CONFIGURATION
# ============================================================================


# ============================================================================
# CONFIGURATION
# ============================================================================

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
HOSPITALS_JSON = os.getenv("HOSPITALS_JSON_PATH", "e:\Medicon\cghs_hospitals_basic.json")
RATES_JSON = os.getenv("RATES_JSON_PATH", "e:\Medicon\cghs_rates.json")

# Initialize Gemini client
gemini_client = None
if GOOGLE_API_KEY and GEMINI_AVAILABLE:
    try:
        gemini_client = GeminiClient(api_key=GOOGLE_API_KEY)
        print("✓ Gemini client initialized")
    except Exception as e:
        print(f"⚠️  Failed to initialize Gemini: {e}")


# ============================================================================
# DATA MODELS
# ============================================================================

class NABHStatus(str, Enum):
    NABH = "NABH/ NABL"
    NON_NABH = "Non-NABH"
    NOT_CGHS = "Not CGHS-empanelled"

class Hospital(BaseModel):
    sr_no: Optional[float] = None
    hospital_name: str
    address: str
    nabh_status: str
    contact_no: str
    distance_km: Optional[float] = None

class HospitalSearchRequest(BaseModel):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    radius_km: float = 5.0
    nabh_only: bool = False
    name_query: Optional[str] = None

class HospitalSearchResponse(BaseModel):
    hospitals: List[Hospital]
    total_count: int
    nabh_count: int
    non_nabh_count: int

class BillItem(BaseModel):
    description: str
    quantity: Optional[float] = 1.0
    unit_price: Optional[float] = None
    total_price: float
    category: Optional[str] = None

class BillData(BaseModel):
    hospital_name: str
    hospital_address: Optional[str] = None
    patient_name: Optional[str] = None
    bill_number: Optional[str] = None
    bill_date: Optional[str] = None
    admission_date: Optional[str] = None
    discharge_date: Optional[str] = None
    items: List[BillItem] = Field(default_factory=list)
    total_amount: float
    advance_paid: Optional[float] = 0.0
    balance_amount: Optional[float] = None

class ViolationType(str, Enum):
    PACKAGE_RATE_VIOLATION = "package_rate_violation"
    BALANCE_BILLING = "balance_billing"
    BIS_VIOLATION = "bis_violation"
    SUSPICIOUS_PATTERN = "suspicious_pattern"
    INFORMATIONAL = "informational"

class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    COMPLIANT = "compliant"
    INFO = "info"

class Violation(BaseModel):
    type: ViolationType
    severity: Severity
    description: str
    item: Optional[str] = None
    charged_amount: Optional[float] = None
    expected_amount: Optional[float] = None
    deviation_percentage: Optional[float] = None
    legal_reference: Optional[str] = None
    is_enforceable: bool = True

class PriceComparison(BaseModel):
    item: str
    charged_amount: float
    cghs_rate: Optional[float] = None
    cghs_procedure_matched: Optional[str] = None
    match_confidence: Optional[float] = None
    applicable_rate_type: str
    deviation_percentage: float
    is_abnormal: bool
    
    @field_validator('charged_amount', 'cghs_rate', 'deviation_percentage', 'match_confidence', mode='before')
    @classmethod
    def replace_nan(cls, v):
        """Replace NaN with None"""
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return v

class InsuranceRisk(BaseModel):
    risk_level: Severity
    issues: List[str]
    recommendations: List[str]

class BillAnalysisResult(BaseModel):
    hospital_name: str
    nabh_status: str
    is_cghs_empanelled: bool
    violations: List[Violation] = Field(default_factory=list)
    price_comparisons: List[PriceComparison] = Field(default_factory=list)
    overall_risk: Severity
    summary: str
    total_violations: int = 0
    high_severity_count: int = 0
    medium_severity_count: int = 0
    recommendations: List[str] = Field(default_factory=list)
    can_file_cghs_complaint: bool = False

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def clean_float(value):
    """Convert NaN/Inf to None for JSON compatibility"""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
    return value

def clean_dict_for_json(obj):
    """Recursively clean NaN/Inf values from dict/list"""
    if isinstance(obj, dict):
        return {k: clean_dict_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_dict_for_json(item) for item in obj]
    elif isinstance(obj, float):
        return clean_float(obj)
    else:
        return obj

# ============================================================================
# GOOGLE CLOUD VISION OCR
# ============================================================================

class GoogleVisionOCR:
    """Extract text from images using Google Cloud Vision"""
    
    def __init__(self):
        try:
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
            images = convert_from_path(pdf_path, first_page=1, last_page=5)
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

# ============================================================================
# GEMINI STRUCTURER
# ============================================================================

class GeminiStructurer:
    """Use Gemini 2.0 Flash to structure OCR text into bill data"""
    
    def __init__(self):
        global gemini_client
        self.client = gemini_client
        if not self.client:
            print(f"⚠️  Warning: Gemini client not initialized")
    
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
11. ALL itemized charges with:
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
            response = self.client.models.generate_content(
                model='gemini-2.0-flash-exp',
                contents=prompt
            )
            
            response_text = response.text.strip()
            
            # Clean response
            if response_text.startswith('```json'):
                response_text = response_text[7:]
            if response_text.startswith('```'):
                response_text = response_text[3:]
            if response_text.endswith('```'):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            # Parse JSON
            extracted_data = json.loads(response_text)
            
            # Convert to BillData
            bill_data = BillData(
                hospital_name=extracted_data.get('hospital_name', 'Unknown Hospital'),
                hospital_address=extracted_data.get('hospital_address'),
                patient_name=extracted_data.get('patient_name'),
                bill_number=extracted_data.get('bill_number'),
                bill_date=extracted_data.get('bill_date'),
                admission_date=extracted_data.get('admission_date'),
                discharge_date=extracted_data.get('discharge_date'),
                total_amount=float(extracted_data.get('total_amount', 0)),
                advance_paid=float(extracted_data.get('advance_paid', 0)) if extracted_data.get('advance_paid') else 0.0,
                balance_amount=float(extracted_data.get('balance_amount', 0)) if extracted_data.get('balance_amount') else None,
                items=[
                    BillItem(
                        description=item.get('description', ''),
                        quantity=float(item.get('quantity', 1.0)) if item.get('quantity') else 1.0,
                        unit_price=float(item.get('unit_price', 0)) if item.get('unit_price') else None,
                        total_price=float(item.get('total_price', 0)),
                        category=item.get('category')
                    )
                    for item in extracted_data.get('items', [])
                ]
            )
            
            return bill_data
            
        except json.JSONDecodeError as e:
            raise Exception(f"Gemini returned invalid JSON: {e}\nResponse: {response_text[:500]}")
        except Exception as e:
            raise Exception(f"Gemini processing failed: {e}")

# ============================================================================
# HYBRID OCR SERVICE
# ============================================================================

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

# ============================================================================
# HOSPITAL DISCOVERY SERVICE
# ============================================================================

class HospitalDiscoveryService:
    def __init__(self, hospitals_json_path: str):
        with open(hospitals_json_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        
        # Normalize NABH status
        self.hospitals_db = []
        for h in raw_data:
            status = h.get('nabh_status', '').strip()
            
            # Standardize variations
            if 'NABH' in status.upper():
                h['nabh_status'] = 'NABH/ NABL'
            else:
                h['nabh_status'] = 'Non-NABH'
            
            self.hospitals_db.append(h)
        
        nabh_count = sum(1 for h in self.hospitals_db if h['nabh_status'] == 'NABH/ NABL')
        print(f"   ✓ Loaded {len(self.hospitals_db)} CGHS hospitals")
        print(f"   ℹ️  NABH hospitals: {nabh_count}")
    
    def find_nearby_hospitals(self, search_request: HospitalSearchRequest) -> HospitalSearchResponse:
        """Find hospitals (simplified without geolocation)"""
        
        filtered_hospitals = []
        
        for hospital_data in self.hospitals_db:
            # NABH filter
            if search_request.nabh_only:
                status = hospital_data.get('nabh_status', '').upper()
                if 'NABH' not in status:
                    continue
            
            # Name search filter
            if search_request.name_query:
                if search_request.name_query.lower() not in hospital_data.get('hospital_name', '').lower():
                    continue
            
            try:
                hospital = Hospital(**hospital_data)
                filtered_hospitals.append(hospital)
            except Exception as e:
                print(f"   ⚠️  Skipped hospital due to validation error: {e}")
        
        nabh_count = sum(1 for h in filtered_hospitals if 'NABH' in h.nabh_status.upper())
        non_nabh_count = len(filtered_hospitals) - nabh_count
        
        return HospitalSearchResponse(
            hospitals=filtered_hospitals[:100],
            total_count=len(filtered_hospitals),
            nabh_count=nabh_count,
            non_nabh_count=non_nabh_count
        )
    
    def get_hospital_by_name(self, hospital_name: str) -> Optional[Hospital]:
        """Get hospital details by fuzzy name matching"""
        if not hospital_name or hospital_name.strip() == "":
            return None
        
        best_match = None
        best_score = 0
        
        hospital_name_clean = hospital_name.strip().lower()
        
        for hospital_data in self.hospitals_db:
            db_name = hospital_data.get('hospital_name', '').lower()
            
            if hospital_name_clean == db_name:
                return Hospital(**hospital_data)
            
            score = fuzz.ratio(hospital_name_clean, db_name)
            if score > best_score:
                best_score = score
                best_match = hospital_data
        
        if best_score >= 75:
            return Hospital(**best_match)
        
        return None

# ============================================================================
# SEMANTIC CGHS RATE VALIDATOR (NEW - INTELLIGENT MATCHING)
# ============================================================================

class SemanticRateValidator:
    """
    Intelligent rate matching using semantic embeddings
    Understands meaning, not just word similarity
    """
    
    def __init__(self, rates_json_path: str):
        # Load rates
        with open(rates_json_path, 'r', encoding='utf-8') as f:
            raw_rates = json.load(f)
        
        # Clean NaN values
        self.rates_db = []
        for rate in raw_rates:
            cleaned_rate = {}
            for key, value in rate.items():
                if isinstance(value, float) and math.isnan(value):
                    cleaned_rate[key] = None
                else:
                    cleaned_rate[key] = value
            self.rates_db.append(cleaned_rate)
        
        print(f"   ✓ Loaded {len(self.rates_db)} CGHS rate entries")
        
        # Manual overrides for 100% accurate common items
        self.manual_overrides = {
            'consultation': {'procedure': 'Consultation OPD', 'non_nabh': 350, 'nabh': 350, 'confidence': 100},
            'opd': {'procedure': 'Consultation OPD', 'non_nabh': 350, 'nabh': 350, 'confidence': 100},
            'doctor visit': {'procedure': 'Consultation OPD', 'non_nabh': 350, 'nabh': 350, 'confidence': 100},
            'professional fee': {'procedure': 'Consultation OPD', 'non_nabh': 350, 'nabh': 350, 'confidence': 100},
            'room rent': {'procedure': 'General Ward (per day)', 'non_nabh': 1500, 'nabh': 1500, 'confidence': 100},
            'general ward': {'procedure': 'General Ward (per day)', 'non_nabh': 1500, 'nabh': 1500, 'confidence': 100},
            'bed charges': {'procedure': 'General Ward (per day)', 'non_nabh': 1500, 'nabh': 1500, 'confidence': 100},
            'icu': {'procedure': 'ICU including room rent', 'non_nabh': 4590, 'nabh': 5400, 'confidence': 100},
            'intensive care': {'procedure': 'ICU including room rent', 'non_nabh': 4590, 'nabh': 5400, 'confidence': 100},
        }
        
        # Load semantic model
        print("   🧠 Loading semantic matching model...")
        try:
            self.model = SentenceTransformer('all-MiniLM-L6-v2')
            
            # Pre-compute embeddings for all CGHS procedures
            self.procedures = [r.get('procedure', '') for r in self.rates_db if r.get('procedure')]
            print(f"   📊 Computing embeddings for {len(self.procedures)} procedures...")
            self.procedure_embeddings = self.model.encode(self.procedures, show_progress_bar=False)
            print("   ✓ Semantic matching ready")
            
            self.semantic_available = True
        except Exception as e:
            print(f"   ⚠️  Semantic model loading failed: {e}")
            print("   ℹ️  Falling back to fuzzy matching")
            self.semantic_available = False
    
    def find_cghs_rate_with_confidence(self, item_description: str, nabh_status: str) -> tuple:
        """
        Find CGHS rate using semantic similarity
        Returns: (rate, matched_procedure, confidence_percentage)
        """
        if not item_description:
            return (None, None, 0)
        
        item_lower = item_description.lower().strip()
        
        # Check manual overrides first (100% confidence)
        for key, override in self.manual_overrides.items():
            if key in item_lower:
                rate = override['nabh'] if nabh_status == "NABH/ NABL" else override['non_nabh']
                return (rate, override['procedure'], override['confidence'])
        
        # Use semantic matching if available
        if self.semantic_available:
            return self._semantic_match(item_description, nabh_status)
        else:
            return self._fuzzy_match(item_description, nabh_status)
    
    def _semantic_match(self, item_description: str, nabh_status: str, threshold=0.5):
        """Semantic matching using embeddings"""
        try:
            # Compute embedding for input item
            item_embedding = self.model.encode([item_description], show_progress_bar=False)
            
            # Calculate cosine similarity with all procedures
            similarities = cosine_similarity(item_embedding, self.procedure_embeddings)[0]
            
            # Find best match
            best_idx = np.argmax(similarities)
            best_score = similarities[best_idx]
            
            # Only return if above threshold (0.5 = 50% similarity)
            if best_score >= threshold:
                matched_procedure = self.rates_db[best_idx]
                rate = matched_procedure.get('nabh_rate') if nabh_status == "NABH/ NABL" else matched_procedure.get('non_nabh_rate')
                
                # Skip if rate is None or NaN
                if rate is None or (isinstance(rate, float) and math.isnan(rate)):
                    return (None, None, 0)
                
                confidence = min(99, best_score * 100)  # Convert to percentage, cap at 99
                procedure_name = matched_procedure.get('procedure', 'Unknown')
                
                return (rate, procedure_name, confidence)
            
            return (None, None, best_score * 100)
        
        except Exception as e:
            print(f"   ⚠️  Semantic matching error: {e}")
            return self._fuzzy_match(item_description, nabh_status)
    
    def _fuzzy_match(self, item_description: str, nabh_status: str):
        """Fallback fuzzy matching"""
        item_lower = item_description.lower().strip()
        
        best_match = None
        best_score = 0
        
        for rate_entry in self.rates_db:
            procedure = rate_entry.get('procedure', '')
            if not procedure:
                continue
            
            procedure_lower = procedure.lower()
            
            # Exact match
            if item_lower == procedure_lower:
                best_match = rate_entry
                best_score = 100
                break
            
            # Contains check
            if item_lower in procedure_lower:
                score = 90
                if score > best_score:
                    best_score = score
                    best_match = rate_entry
                continue
            
            if procedure_lower in item_lower:
                score = 85
                if score > best_score:
                    best_score = score
                    best_match = rate_entry
                continue
            
            # Fuzzy matching
            score = fuzz.token_sort_ratio(item_lower, procedure_lower)
            
            if score > best_score and score >= 70:
                best_score = score
                best_match = rate_entry
        
        if best_match and best_score >= 70:
            rate = best_match.get('nabh_rate') if nabh_status == "NABH/ NABL" else best_match.get('non_nabh_rate')
            
            if rate is None or (isinstance(rate, float) and math.isnan(rate)):
                return (None, None, 0)
            
            procedure_name = best_match.get('procedure', 'Unknown')
            return (rate, procedure_name, best_score)
        
        return (None, None, 0)
    
    def check_rate_violations(self, bill_data: BillData, nabh_status: str, is_cghs: bool) -> List[Violation]:
        """Check if charges exceed CGHS rates"""
        violations = []
        
        for item in bill_data.items:
            cghs_rate, matched_proc, confidence = self.find_cghs_rate_with_confidence(item.description, nabh_status)
            
            if not cghs_rate:
                continue
            
            if isinstance(cghs_rate, float) and math.isnan(cghs_rate):
                continue
            
            if not item.total_price or (isinstance(item.total_price, float) and math.isnan(item.total_price)):
                continue
            
            if item.total_price > cghs_rate:
                try:
                    deviation = ((item.total_price - cghs_rate) / cghs_rate) * 100
                    
                    if math.isnan(deviation) or math.isinf(deviation):
                        continue
                    
                    if is_cghs:
                        # CGHS hospital - require high confidence (75%)
                        if confidence >= 75:
                            violations.append(Violation(
                                type=ViolationType.PACKAGE_RATE_VIOLATION,
                                severity=Severity.HIGH if deviation > 20 else Severity.MEDIUM,
                                description=f"Exceeds CGHS {nabh_status} rate by {deviation:.1f}% (matched: '{matched_proc}', confidence: {confidence:.0f}%)",
                                item=item.description,
                                charged_amount=item.total_price,
                                expected_amount=cghs_rate,
                                deviation_percentage=deviation,
                                legal_reference="CGHS Package Rate Guidelines (MANDATORY)",
                                is_enforceable=True
                            ))
                    else:
                        # Non-CGHS hospital - require very high confidence (85%)
                        if deviation > 100 and confidence >= 85:
                            violations.append(Violation(
                                type=ViolationType.INFORMATIONAL,
                                severity=Severity.INFO,
                                description=f"{deviation:.0f}% above CGHS reference (matched: '{matched_proc}', {confidence:.0f}% confidence)",
                                item=item.description,
                                charged_amount=item.total_price,
                                expected_amount=cghs_rate,
                                deviation_percentage=deviation,
                                legal_reference="⚠️ INFORMATIONAL - Hospital not CGHS-empanelled",
                                is_enforceable=False
                            ))
                except Exception as e:
                    continue
        
        return violations
    
    def compare_with_cghs_rate(self, item: BillItem, nabh_status: str) -> Optional[PriceComparison]:
        """Compare item price with CGHS rate"""
        cghs_rate, matched_procedure, confidence = self.find_cghs_rate_with_confidence(item.description, nabh_status)
        
        # Skip if no match or low confidence
        if not cghs_rate or confidence < 50:
            return None
        
        if isinstance(cghs_rate, float) and math.isnan(cghs_rate):
            return None
        
        if not item.total_price or (isinstance(item.total_price, float) and math.isnan(item.total_price)):
            return None
        
        try:
            deviation = ((item.total_price - cghs_rate) / cghs_rate) * 100
            
            if math.isnan(deviation) or math.isinf(deviation):
                return None
            
            is_abnormal = abs(deviation) > 50
        except:
            return None
        
        return PriceComparison(
            item=item.description,
            charged_amount=item.total_price,
            cghs_rate=cghs_rate,
            cghs_procedure_matched=matched_procedure,
            match_confidence=confidence,
            applicable_rate_type=nabh_status,
            deviation_percentage=deviation,
            is_abnormal=is_abnormal
        )

# ============================================================================
# BILL ANALYZER
# ============================================================================

class BillAnalyzer:
    def __init__(self, rates_json_path: str):
        self.rate_validator = SemanticRateValidator(rates_json_path)
    
    def analyze_bill(self, bill_data: BillData, nabh_status: str, is_cghs_hospital: bool) -> BillAnalysisResult:
        """Analyze bill - different logic for CGHS vs non-CGHS hospitals"""
        
        if is_cghs_hospital:
            return self._analyze_cghs_hospital(bill_data, nabh_status)
        else:
            return self._analyze_non_cghs_hospital(bill_data)
    
    def _analyze_cghs_hospital(self, bill_data: BillData, nabh_status: str) -> BillAnalysisResult:
        """Case A: CGHS-empanelled hospital - strict compliance required"""
        violations = []
        price_comparisons = []
        
        # 1. Rate violations (LEGALLY BINDING)
        rate_violations = self.rate_validator.check_rate_violations(bill_data, nabh_status, is_cghs=True)
        violations.extend(rate_violations)
        
        # 2. BIS compliance
        if not bill_data.bill_number:
            violations.append(Violation(
                type=ViolationType.BIS_VIOLATION,
                severity=Severity.MEDIUM,
                description="Missing bill number (violates BIS IS 19493:2024)",
                legal_reference="BIS IS 19493:2024 - Billing Standards",
                is_enforceable=True
            ))
        
        if not bill_data.bill_date:
            violations.append(Violation(
                type=ViolationType.BIS_VIOLATION,
                severity=Severity.MEDIUM,
                description="Missing bill date (violates BIS IS 19493:2024)",
                legal_reference="BIS IS 19493:2024 - Billing Standards",
                is_enforceable=True
            ))
        
        if len(bill_data.items) == 0:
            violations.append(Violation(
                type=ViolationType.BIS_VIOLATION,
                severity=Severity.HIGH,
                description="No itemized charges provided (violates BIS billing transparency standards)",
                legal_reference="BIS IS 19493:2024 - Itemization Requirement",
                is_enforceable=True
            ))
        
        # 3. Generate price comparisons
        for item in bill_data.items:
            comparison = self.rate_validator.compare_with_cghs_rate(item, nabh_status)
            if comparison:
                price_comparisons.append(comparison)
        
        # Calculate risk
        high_count = sum(1 for v in violations if v.severity == Severity.HIGH)
        medium_count = sum(1 for v in violations if v.severity == Severity.MEDIUM)
        
        if high_count > 0:
            overall_risk = Severity.HIGH
        elif medium_count > 0:
            overall_risk = Severity.MEDIUM
        else:
            overall_risk = Severity.COMPLIANT
        
        # Calculate total overcharge
        total_overcharge = sum(
            v.charged_amount - v.expected_amount 
            for v in violations 
            if v.type == ViolationType.PACKAGE_RATE_VIOLATION and v.charged_amount and v.expected_amount
        )
        
        # Summary
        if len(violations) == 0:
            summary = f"✅ This CGHS-empanelled {nabh_status} hospital's billing appears compliant with CGHS package rates and regulations."
        else:
            summary = f"⚠️ This is a CGHS-empanelled {nabh_status} hospital.\n\nDetected {len(violations)} violations of CGHS package rates (legally binding).\n\nTotal overcharge: ₹{total_overcharge:,.2f}\n\nYou have the right to file a complaint with CGHS authorities."
        
        # Recommendations
        recommendations = []
        if high_count > 0:
            recommendations.append("File a complaint with CGHS authorities immediately")
            recommendations.append("Request itemized bill if not provided")
            recommendations.append("Demand refund for overcharged amounts")
        if medium_count > 0:
            recommendations.append("Request complete bill with all required details")
        if len(violations) == 0:
            recommendations.append("Bill appears compliant - proceed with payment/insurance claim")
        
        return BillAnalysisResult(
            hospital_name=bill_data.hospital_name,
            nabh_status=nabh_status,
            is_cghs_empanelled=True,
            violations=violations,
            price_comparisons=price_comparisons,
            overall_risk=overall_risk,
            summary=summary,
            total_violations=len(violations),
            high_severity_count=high_count,
            medium_severity_count=medium_count,
            recommendations=recommendations,
            can_file_cghs_complaint=True
        )
    
    def _analyze_non_cghs_hospital(self, bill_data: BillData) -> BillAnalysisResult:
        """Case B: Non-CGHS hospital - reference comparison only"""
        violations = []
        price_comparisons = []
        
        # 1. Compare with CGHS rates (INFORMATIONAL ONLY)
        rate_violations = self.rate_validator.check_rate_violations(
            bill_data, 
            "Non-NABH",
            is_cghs=False
        )
        violations.extend(rate_violations)
        
        # 2. Generate price comparisons
        for item in bill_data.items:
            comparison = self.rate_validator.compare_with_cghs_rate(item, "Non-NABH")
            if comparison:
                price_comparisons.append(comparison)
        
        # 3. BIS compliance (still applicable)
        if len(bill_data.items) == 0:
            violations.append(Violation(
                type=ViolationType.BIS_VIOLATION,
                severity=Severity.MEDIUM,
                description="No itemized charges provided (violates general billing transparency standards)",
                legal_reference="BIS IS 19493:2024 / Consumer Protection Act",
                is_enforceable=True
            ))
        
        # Calculate average deviation
        avg_deviation = 0
        if price_comparisons:
            avg_deviation = sum(pc.deviation_percentage for pc in price_comparisons) / len(price_comparisons)
        
        # Risk assessment
        info_count = sum(1 for v in violations if v.severity == Severity.INFO)
        
        if avg_deviation > 150:
            overall_risk = Severity.MEDIUM
        elif avg_deviation > 100:
            overall_risk = Severity.LOW
        else:
            overall_risk = Severity.COMPLIANT
        
        # Summary
        summary = f"""⚠️ IMPORTANT: This hospital is NOT in the CGHS empanelment list.

This hospital is NOT legally bound by CGHS rates. The analysis below is for REFERENCE ONLY.

Price Analysis:
- Average charge is {avg_deviation:.0f}% {'higher' if avg_deviation > 0 else 'lower'} than CGHS reference rates
- {len([pc for pc in price_comparisons if pc.is_abnormal])} items significantly above reference rates

This comparison is useful for:
✓ Insurance claim negotiations  
✓ Understanding market pricing
✓ Deciding whether to seek treatment at CGHS hospitals for future procedures

⚠️ You CANNOT file a CGHS complaint against this hospital.
"""
        
        # Recommendations
        recommendations = [
            "Consider seeking treatment at CGHS-empanelled hospitals for regulated pricing",
            "Use this analysis to negotiate with your insurance company",
            "Verify if hospital follows Consumer Protection Act billing standards",
            "Check if you can claim reimbursement under any government health scheme"
        ]
        
        if avg_deviation > 100:
            recommendations.insert(0, "Charges are significantly higher than CGHS reference rates - consider price negotiation")
        
        return BillAnalysisResult(
            hospital_name=bill_data.hospital_name,
            nabh_status="Not CGHS-empanelled",
            is_cghs_empanelled=False,
            violations=violations,
            price_comparisons=price_comparisons,
            overall_risk=overall_risk,
            summary=summary,
            total_violations=info_count,
            high_severity_count=0,
            medium_severity_count=0,
            recommendations=recommendations,
            can_file_cghs_complaint=False
        )

# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

hospital_service = None
bill_analyzer = None
hybrid_ocr = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup"""
    global hospital_service, bill_analyzer, hybrid_ocr
    
    print("\n" + "=" * 70)
    print("🏥 Medical Bill Analyzer - Initializing Services")
    print("=" * 70)
    
    # Initialize data services
    if Path(HOSPITALS_JSON).exists() and Path(RATES_JSON).exists():
        try:
            hospital_service = HospitalDiscoveryService(HOSPITALS_JSON)
            bill_analyzer = BillAnalyzer(RATES_JSON)
            print("✓ Hospital and rate services initialized")
        except Exception as e:
            print(f"❌ Failed to initialize data services: {e}")
            traceback.print_exc()
    else:
        print(f"❌ Missing data files: {HOSPITALS_JSON} or {RATES_JSON}")
    
    # Initialize OCR services
    if GOOGLE_API_KEY and GOOGLE_APPLICATION_CREDENTIALS:
        try:
            hybrid_ocr = HybridOCR()
            print("✓ Hybrid OCR initialized (Google Vision + Gemini)")
        except Exception as e:
            print(f"❌ OCR initialization failed: {e}")
            traceback.print_exc()
    else:
        missing = []
        if not GOOGLE_API_KEY:
            missing.append("GOOGLE_API_KEY")
        if not GOOGLE_APPLICATION_CREDENTIALS:
            missing.append("GOOGLE_APPLICATION_CREDENTIALS")
        print(f"❌ OCR disabled. Missing: {', '.join(missing)}")
    
    print("=" * 70)
    print()
    
    yield
    
    print("\n🛑 Shutting down...")

app = FastAPI(
    title="Medical Bill Analyzer API",
    description="CGHS Bill Analysis with Semantic Matching (Google Vision + Gemini + AI Embeddings)",
    version="3.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# API ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    return {
        "message": "Medical Bill Analyzer API",
        "version": "3.0.0",
        "status": "running",
        "features": [
            "Hospital Discovery",
            "Bill OCR (Google Vision + Gemini)",
            "CGHS Rate Validation",
            "Semantic Matching (AI Embeddings)",
            "NABH vs Non-NABH Support",
            "CGHS vs Non-CGHS Hospital Distinction"
        ],
        "docs": "/docs"
    }

@app.get("/api/v1/hospitals/list")
async def list_hospitals(
    nabh_only: bool = False,
    name_query: Optional[str] = None,
    limit: int = 100
):
    """List CGHS-empanelled hospitals"""
    if not hospital_service:
        raise HTTPException(status_code=503, detail="Hospital service not initialized")
    
    request = HospitalSearchRequest(
        nabh_only=nabh_only,
        name_query=name_query
    )
    
    result = hospital_service.find_nearby_hospitals(request)
    result.hospitals = result.hospitals[:limit]
    
    return result

@app.get("/api/v1/hospitals/search")
async def search_hospital_by_name(name: str):
    """Search for a specific hospital by name"""
    if not hospital_service:
        raise HTTPException(status_code=503, detail="Hospital service not initialized")
    
    hospital = hospital_service.get_hospital_by_name(name)
    
    if hospital:
        return {
            "found": True,
            "hospital": hospital.model_dump(),
            "is_cghs_empanelled": True
        }
    else:
        return {
            "found": False,
            "message": f"No CGHS hospital found matching '{name}'",
            "is_cghs_empanelled": False,
            "suggestion": "Hospital may not be CGHS-empanelled. Analysis will use reference rates."
        }

@app.post("/api/v1/bills/upload-and-analyze")
async def upload_and_analyze_bill(file: UploadFile = File(...)):
    """
    Upload bill image/PDF and get comprehensive analysis with semantic matching
    """
    if not hybrid_ocr:
        raise HTTPException(
            status_code=503,
            detail="OCR service not initialized. Check GOOGLE_API_KEY and GOOGLE_APPLICATION_CREDENTIALS."
        )
    
    if not hospital_service or not bill_analyzer:
        raise HTTPException(
            status_code=503,
            detail="Analysis services not initialized. Check hospitals.json and rates.json."
        )
    
    allowed_ext = ['.jpg', '.jpeg', '.png', '.webp', '.pdf']
    file_ext = os.path.splitext(file.filename)[1].lower()
    
    if file_ext not in allowed_ext:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{file_ext}'. Allowed: {', '.join(allowed_ext)}"
        )
    
    temp_file = f"temp_upload_{os.urandom(8).hex()}{file_ext}"
    
    try:
        print(f"\n📤 Processing upload: {file.filename}")
        with open(temp_file, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        print(f"   ✓ Saved to {temp_file}")
        
        # Extract bill data
        try:
            if file_ext == '.pdf':
                bill_data = hybrid_ocr.extract_from_pdf(temp_file)
            else:
                bill_data = hybrid_ocr.extract_from_image(temp_file)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"OCR extraction failed: {str(e)}")
        
        print(f"   ✓ Extracted bill: {bill_data.hospital_name}")
        print(f"   ✓ Total amount: ₹{bill_data.total_amount:,.2f}")
        print(f"   ✓ Items: {len(bill_data.items)}")
        
        # Find hospital
        hospital = hospital_service.get_hospital_by_name(bill_data.hospital_name)
        
        is_cghs = hospital is not None
        nabh_status = hospital.nabh_status if hospital else "Not CGHS-empanelled"
        
        print(f"   {'✓' if is_cghs else '⚠️ '} Hospital match: {hospital.hospital_name if hospital else 'Not found in CGHS database'}")
        print(f"   ℹ️  Status: {nabh_status}")
        
        # Analyze bill
        analysis = bill_analyzer.analyze_bill(
            bill_data=bill_data,
            nabh_status=nabh_status,
            is_cghs_hospital=is_cghs
        )
        
        print(f"   ✓ Analysis complete")
        print(f"   ✓ Risk level: {analysis.overall_risk}")
        print(f"   ✓ Violations: {analysis.total_violations}")
        
        # Clean result for JSON
        result = {
            "success": True,
            "extracted_bill_data": bill_data.model_dump(),
            "hospital_match": {
                "found": is_cghs,
                "hospital": hospital.model_dump() if hospital else None,
                "nabh_status": nabh_status,
                "is_cghs_empanelled": is_cghs
            },
            "analysis": analysis.model_dump()
        }
        
        result = clean_dict_for_json(result)
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
    
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
            print(f"   ✓ Cleaned up {temp_file}")

@app.post("/api/v1/bills/extract-only")
async def extract_bill_only(file: UploadFile = File(...)):
    """Extract bill data from image/PDF without analysis"""
    if not hybrid_ocr:
        raise HTTPException(status_code=503, detail="OCR service not initialized")
    
    allowed_ext = ['.jpg', '.jpeg', '.png', '.webp', '.pdf']
    file_ext = os.path.splitext(file.filename)[1].lower()
    
    if file_ext not in allowed_ext:
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    temp_file = f"temp_upload_{os.urandom(8).hex()}{file_ext}"
    
    try:
        with open(temp_file, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        if file_ext == '.pdf':
            bill_data = hybrid_ocr.extract_from_pdf(temp_file)
        else:
            bill_data = hybrid_ocr.extract_from_image(temp_file)
        
        return {
            "success": True,
            "bill_data": bill_data.model_dump()
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)

@app.get("/api/v1/health")
async def health_check():
    """Check API health and service status"""
    
    ocr_vision_ok = False
    ocr_gemini_ok = False
    semantic_matching_ok = False
    
    if hybrid_ocr:
        try:
            ocr_vision_ok = hybrid_ocr.vision_ocr.client is not None
        except:
            ocr_vision_ok = False
        
        try:
            ocr_gemini_ok = hybrid_ocr.gemini_structurer.client is not None
        except:
            ocr_gemini_ok = False
    
    if bill_analyzer:
        try:
            semantic_matching_ok = bill_analyzer.rate_validator.semantic_available
        except:
            semantic_matching_ok = False
    
    return {
        "status": "healthy",
        "services": {
            "hospital_discovery": hospital_service is not None,
            "bill_analyzer": bill_analyzer is not None,
            "ocr_vision": ocr_vision_ok,
            "ocr_gemini": ocr_gemini_ok,
            "semantic_matching": semantic_matching_ok
        },
        "data_loaded": {
            "hospitals": len(hospital_service.hospitals_db) if hospital_service else 0,
            "rates": len(bill_analyzer.rate_validator.rates_db) if bill_analyzer else 0
        }
    }

@app.get("/api/v1/stats")
async def get_statistics():
    """Get statistics about loaded data"""
    if not hospital_service or not bill_analyzer:
        raise HTTPException(status_code=503, detail="Services not initialized")
    
    nabh_count = sum(
        1 for h in hospital_service.hospitals_db 
        if 'NABH' in h.get('nabh_status', '').upper()
    )
    
    return {
        "hospitals": {
            "total": len(hospital_service.hospitals_db),
            "nabh": nabh_count,
            "non_nabh": len(hospital_service.hospitals_db) - nabh_count
        },
        "procedures": {
            "total": len(bill_analyzer.rate_validator.rates_db)
        },
        "matching_method": "semantic_embeddings" if bill_analyzer.rate_validator.semantic_available else "fuzzy_matching"
    }

# ============================================================================
# RUN SERVER
# ============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("🏥 Medical Bill Analyzer API Server v3.0")
    print("=" * 70)
    print("\n📋 Prerequisites:")
    print("   1. hospitals.json - CGHS hospitals database")
    print("   2. rates.json - CGHS package rates database")
    print("   3. GOOGLE_API_KEY - Gemini API key")
    print("   4. GOOGLE_APPLICATION_CREDENTIALS - Google Cloud service account")
    print("\n🌐 Starting server...")
    print("=" * 70)
    print()
    
    uvicorn.run(
        "medical_analyzer:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
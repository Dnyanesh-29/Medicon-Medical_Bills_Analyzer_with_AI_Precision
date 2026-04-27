import os
import shutil
import traceback
from contextlib import asynccontextmanager
from typing import Optional, Dict

from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

from app.core.config import settings
from app.models.schemas import HospitalSearchRequest, BillData
from app.services.hospital import HospitalDiscoveryService
from app.services.validator import SemanticRateValidator
from app.services.analyzer import BillAnalyzer
from app.services.ocr import HybridOCR
from app.utils import clean_dict_for_json

# Global services
hospital_service: Optional[HospitalDiscoveryService] = None
bill_analyzer: Optional[BillAnalyzer] = None
hybrid_ocr: Optional[HybridOCR] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup"""
    global hospital_service, bill_analyzer, hybrid_ocr
    
    print("\n" + "=" * 70)
    print(" Medical Bill Analyzer - Initializing Services")
    print("=" * 70)
    
    # Initialize data services
    if settings.is_data_configured:
        try:
            hospital_service = HospitalDiscoveryService(settings.HOSPITALS_JSON_PATH)
            bill_analyzer = BillAnalyzer(settings.RATES_JSON_PATH)
            print("  Hospital and rate services initialized")
        except Exception as e:
            print(f" Failed to initialize data services: {e}")
            traceback.print_exc()
    else:
        print(f" Missing data files configuration. Check .env or config.py")
        print(f"Hospitals: {settings.HOSPITALS_JSON_PATH}")
        print(f"Rates: {settings.RATES_JSON_PATH}")
    
    # Initialize OCR services
    if settings.is_ocr_configured:
        try:
            hybrid_ocr = HybridOCR()
            print("  Hybrid OCR initialized (Google Vision + Gemini)")
        except Exception as e:
            print(f" OCR initialization failed: {e}")
            traceback.print_exc()
    else:
        print(f" OCR disabled. Missing API keys in .env")
    
    print("=" * 70)
    print()
    
    yield
    
    print("\n Shutting down...")

app = FastAPI(
    title="Medical Bill Analyzer API",
    description="CGHS Bill Analysis with Semantic Matching (Google Vision + Gemini + AI Embeddings)",
    version="3.1.0",
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
        "version": "3.1.0",
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
            detail="OCR service not initialized. Check GOOGLE_API_KEY and GOOGLE_APPLICATION_CREDENTIALS in .env."
        )
    
    if not hospital_service or not bill_analyzer:
        raise HTTPException(
            status_code=503,
            detail="Analysis services not initialized. Check hospitals/rates JSON paths in .env."
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
        print(f"\n Processing upload: {file.filename}")
        with open(temp_file, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        print(f"   Saved to {temp_file}")
        
        # Extract bill data
        try:
            if file_ext == '.pdf':
                bill_data = hybrid_ocr.extract_from_pdf(temp_file)
            else:
                bill_data = hybrid_ocr.extract_from_image(temp_file)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"OCR extraction failed: {str(e)}")
        
        print(f"   Extracted bill: {bill_data.hospital_name}")
        print(f"   Total amount: {bill_data.total_amount:,.2f}")
        print(f"   Items: {len(bill_data.items)}")
        
        # Find hospital
        hospital = hospital_service.get_hospital_by_name(bill_data.hospital_name)
        
        # Calculate match confidence — use token_set_ratio so a short name like
        # "Sahyadri Hospital" correctly matches the long DB entry
        # "SAHYADRI HOSPITALS LIMITED'S SAHYADRI SPECIALITY HOSPITAL"
        hospital_match_confidence = 0
        if hospital:
            from fuzzywuzzy import fuzz
            hospital_match_confidence = max(
                fuzz.token_set_ratio(
                    bill_data.hospital_name.lower(),
                    hospital.hospital_name.lower()
                ),
                fuzz.partial_ratio(
                    bill_data.hospital_name.lower(),
                    hospital.hospital_name.lower()
                ),
            )
        
        # Stricter check: only consider it CGHS if confidence is high enough.
        # token_set_ratio handles short-name vs long-name well, so 75 is safe.
        is_cghs = hospital is not None and hospital_match_confidence >= 75
        
        if not is_cghs:
             hospital = None # Reset if confidence is too low

        nabh_status = hospital.nabh_status if hospital else "Not CGHS-empanelled"
        
        print(f"   Hospital match: {hospital.hospital_name if hospital else 'Not found in CGHS database'}")
        print(f"   Status: {nabh_status}")
        
        # Analyze bill
        analysis = bill_analyzer.analyze_bill(
            bill_data=bill_data,
            nabh_status=nabh_status,
            is_cghs_hospital=is_cghs
        )
        
        print(f"   Analysis complete")
        print(f"   Risk level: {analysis.overall_risk}")
        print(f"   Violations: {analysis.total_violations}")
        
        # ── Serialize response ────────────────────────────────────────────
        # jsonable_encoder handles: Pydantic models, str-enums, numpy scalars,
        # datetime, Decimal — anything Python's json module would choke on.
        result = {
            "success": True,
            "extracted_bill_data": bill_data,
            "hospital_match": {
                "found": is_cghs,
                "hospital": hospital,
                "match_confidence": hospital_match_confidence,
                "nabh_status": nabh_status,
                "is_cghs_empanelled": is_cghs,
                "warning": "Low confidence match - verify hospital name"
                    if is_cghs and hospital_match_confidence < 90 else None
            },
            "analysis": analysis,
        }

        try:
            encoded = jsonable_encoder(result)
        except Exception as enc_err:
            print(f"   Serialization error: {enc_err}")
            traceback.print_exc()
            raise HTTPException(
                status_code=500,
                detail=f"Response serialization failed: {enc_err}"
            )

        return JSONResponse(content=encoded)
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"   Error: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
    
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
            print(f"   Cleaned up {temp_file}")

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
        if h.get('nabh_status', '') == 'NABH/ NABL'
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

from pydantic import BaseModel
from typing import List, Any
import json
from fastapi.responses import StreamingResponse

class ChatMessage(BaseModel):
    role: str
    content: str
    
class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    context: Dict[str, Any]

@app.post("/api/v1/chat")
async def chat_endpoint(request: ChatRequest):
    """Chat with the AI using bill context"""
    try:
        from google.genai import Client
        from google.genai import types
        
        client = Client(api_key=os.environ.get("GOOGLE_API_KEY"))
        
        system_prompt = (
            "You are an AI assistant helping a user understand their medical bill analysis.\n\n"
            "Your role:\n"
            "- Be concise, professional, and directly answer the question in 1-2 short sentences.\n"
            "- Explain medical and billing terms simply.\n"
            "- Do not hallucinate or guess missing data.\n\n"
            "Context (Bill Data):\n"
            f"{json.dumps(request.context)}\n\n"
            "Formatting Rules (CRITICAL):\n"
            "1. ALWAYS format your response in PLAIN TEXT. Do NOT use Markdown formatting (no asterisks for bold, no hash tags).\n"
            "2. Use simple dashes (-) or numbers for lists.\n"
            "3. Leave a blank line (double newline) between paragraphs and lists for readability.\n"
            "4. KEEP IT SHORT. Do not summarize the entire bill unless explicitly asked. If the user asks 'Was I overcharged?', just tell them the total overcharge amount and name the top 2-3 items responsible.\n"
            "5. Never start your response with the word 'Answer:' or 'Details:'. Just give the response naturally.\n\n"
            "Only respond based on the provided context."
        )
        
        contents = []
        for msg in request.messages:
            # map roles appropriately for Gemini
            role = "user" if msg.role == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=msg.content)]))
            
        def event_stream():
            try:
                response_stream = client.models.generate_content_stream(
                    model="gemini-2.5-flash",
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.7,
                    )
                )
                for chunk in response_stream:
                    if chunk.text:
                        yield f"data: {json.dumps({'type': 'content', 'content': chunk.text})}\n\n"
                
                yield "data: [DONE]\n\n"
            except Exception as stream_e:
                yield f"data: {json.dumps({'error': str(stream_e)})}\n\n"
                
        return StreamingResponse(event_stream(), media_type="text/event-stream")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    print("\n" + "=" * 70)
    print(" Medical Bill Analyzer API Server v3.1 (Refactored)")
    print("=" * 70)
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
        reload_dirs=["e:/Medicon/backend/app"]
    )

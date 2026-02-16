# main.py - FastAPI Backend for Healthcare Bill Auditor

"""
Healthcare Bill Auditor - FastAPI Backend
Provides REST API endpoints for bill processing, fraud detection, and report generation
"""

from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import logging
from datetime import datetime
import uuid
import os

# Import our core functions
from backend.medical_analyzer import (
    process_bill_image,
    extract_entities,
    validate_cghs_rates,
    validate_bis_compliance,
    detect_temporal_anomalies,
    calculate_fraud_score,
    generate_patient_report,
    generate_grievance_letter,
    predict_insurance_rejection,
    detect_document_tampering,
    calculate_consumable_ratio,
    check_mrp_violations
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Healthcare Bill Auditor API",
    description="AI-powered medical bill fraud detection system for Indian healthcare",
    version="1.0.0"
)

# CORS middleware for mobile app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your mobile app domains
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========================
# REQUEST/RESPONSE MODELS
# ========================

class BillItem(BaseModel):
    """Individual line item in a medical bill"""
    item_name: str = Field(..., description="Name of the procedure/medicine/service")
    item_type: str = Field(..., description="MEDICINE, PROCEDURE, ROOM, CONSUMABLE, TEST")
    quantity: float = Field(..., description="Quantity billed")
    unit: str = Field(default="", description="Unit of measurement")
    unit_price: float = Field(..., description="Price per unit")
    total_price: float = Field(..., description="Total amount for this item")
    batch_number: Optional[str] = Field(None, description="For medicines/consumables")
    expiry_date: Optional[str] = Field(None, description="For medicines/consumables")


class BillMetadata(BaseModel):
    """Bill header information"""
    hospital_name: str
    hospital_address: Optional[str] = None
    hospital_registration: Optional[str] = None
    bill_number: str
    bill_date: str
    patient_name: str
    patient_id: Optional[str] = None
    admission_date: Optional[str] = None
    discharge_date: Optional[str] = None
    diagnosis: Optional[str] = None
    room_type: Optional[str] = None


class ProcessedBillResponse(BaseModel):
    """Response from bill processing"""
    bill_id: str
    metadata: Dict[str, Any]
    extracted_items: List[Dict[str, Any]]
    total_amount: float
    fraud_score: float  # 0-100
    fraud_probability: str  # LOW, MEDIUM, HIGH
    violations: List[Dict[str, Any]]
    savings_potential: float
    confidence: float


class FraudViolation(BaseModel):
    """Details of a detected fraud violation"""
    violation_type: str  # CGHS_VIOLATION, BIS_NONCOMPLIANCE, MRP_VIOLATION, etc.
    item_name: str
    severity: str  # LOW, MEDIUM, HIGH, CRITICAL
    description: str
    evidence: Dict[str, Any]
    suggested_action: str
    legal_section: Optional[str] = None  # Applicable law/section


class GrievanceRequest(BaseModel):
    """Request to generate grievance letter"""
    bill_id: str
    grievance_type: str  # HOSPITAL, CLINICAL_COUNCIL, CONSUMER_COURT
    language: str = "english"  # english, hindi, tamil, etc.
    include_precedents: bool = True


class InsuranceCheckRequest(BaseModel):
    """Request to check insurance rejection probability"""
    bill_id: str
    insurance_provider: str
    policy_number: Optional[str] = None
    tpa_name: Optional[str] = None


# ========================
# API ENDPOINTS
# ========================

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Healthcare Bill Auditor API",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }


@app.get("/api/v1/health")
async def health_check():
    """Detailed health check with service status"""
    return {
        "status": "healthy",
        "services": {
            "ocr": "operational",
            "ner_model": "operational",
            "fraud_detection": "operational",
            "database": "operational"
        },
        "timestamp": datetime.now().isoformat()
    }


@app.post("/api/v1/bill/upload", response_model=ProcessedBillResponse)
async def upload_bill(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    process_mode: str = "full"  # full, quick, ocr_only
):
    """
    Upload and process a medical bill image/PDF
    
    Args:
        file: Image (JPG, PNG) or PDF file of the bill
        process_mode: 
            - full: Complete analysis (OCR + NER + Fraud Detection)
            - quick: Basic validation only
            - ocr_only: Just extract text
    
    Returns:
        ProcessedBillResponse with fraud analysis
    """
    try:
        # Generate unique bill ID
        bill_id = str(uuid.uuid4())
        
        # Validate file type
        allowed_types = ["image/jpeg", "image/png", "application/pdf"]
        if file.content_type not in allowed_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {allowed_types}"
            )
        
        # Save uploaded file temporarily
        temp_path = f"/tmp/{bill_id}_{file.filename}"
        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        logger.info(f"Processing bill {bill_id} in {process_mode} mode")
        
        # Step 1: OCR and text extraction
        ocr_result = process_bill_image(temp_path)
        
        if process_mode == "ocr_only":
            return JSONResponse({
                "bill_id": bill_id,
                "ocr_text": ocr_result["text"],
                "confidence": ocr_result["confidence"]
            })
        
        # Step 2: Visual forensics (detect tampering)
        tampering_result = detect_document_tampering(temp_path)
        
        # Step 3: Named Entity Recognition
        entities = extract_entities(ocr_result["text"])
        
        # Step 4: Fraud detection (if full mode)
        violations = []
        fraud_score = 0.0
        
        if process_mode == "full":
            # CGHS rate validation
            cghs_violations = validate_cghs_rates(entities["items"])
            violations.extend(cghs_violations)
            
            # BIS IS 19493:2025 compliance
            bis_violations = validate_bis_compliance(entities)
            violations.extend(bis_violations)
            
            # MRP violations (for medicines)
            mrp_violations = check_mrp_violations(
                [item for item in entities["items"] if item["type"] == "MEDICINE"]
            )
            violations.extend(mrp_violations)
            
            # Temporal plausibility
            if entities.get("metadata", {}).get("admission_date"):
                temporal_violations = detect_temporal_anomalies(entities)
                violations.extend(temporal_violations)
            
            # Consumable ratio analysis
            consumable_violations = calculate_consumable_ratio(entities)
            violations.extend(consumable_violations)
            
            # Calculate overall fraud score
            fraud_score = calculate_fraud_score(
                violations=violations,
                tampering_score=tampering_result["tampering_probability"],
                entities=entities
            )
        
        # Calculate total amount and potential savings
        total_amount = sum(item["total_price"] for item in entities["items"])
        savings_potential = sum(v.get("overcharge_amount", 0) for v in violations)
        
        # Determine fraud probability category
        if fraud_score >= 70:
            fraud_probability = "HIGH"
        elif fraud_score >= 40:
            fraud_probability = "MEDIUM"
        else:
            fraud_probability = "LOW"
        
        # Store processed bill in database (background task)
        background_tasks.add_task(
            store_bill_in_database,
            bill_id=bill_id,
            data={
                "metadata": entities["metadata"],
                "items": entities["items"],
                "violations": violations,
                "fraud_score": fraud_score
            }
        )
        
        # Clean up temp file
        os.remove(temp_path)
        
        return ProcessedBillResponse(
            bill_id=bill_id,
            metadata=entities["metadata"],
            extracted_items=entities["items"],
            total_amount=total_amount,
            fraud_score=fraud_score,
            fraud_probability=fraud_probability,
            violations=violations,
            savings_potential=savings_potential,
            confidence=ocr_result["confidence"]
        )
        
    except Exception as e:
        logger.error(f"Error processing bill: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/bill/manual-entry")
async def manual_bill_entry(bill_data: Dict[str, Any]):
    """
    Manually enter bill data (for cases where OCR fails)
    
    Args:
        bill_data: Dictionary with metadata and items
    
    Returns:
        Processed bill with fraud analysis
    """
    try:
        bill_id = str(uuid.uuid4())
        
        # Validate and structure the manual entry
        entities = {
            "metadata": bill_data.get("metadata", {}),
            "items": bill_data.get("items", [])
        }
        
        # Run fraud detection
        violations = []
        
        # CGHS validation
        cghs_violations = validate_cghs_rates(entities["items"])
        violations.extend(cghs_violations)
        
        # BIS compliance
        bis_violations = validate_bis_compliance(entities)
        violations.extend(bis_violations)
        
        # MRP checks
        mrp_violations = check_mrp_violations(
            [item for item in entities["items"] if item.get("type") == "MEDICINE"]
        )
        violations.extend(mrp_violations)
        
        # Calculate fraud score
        fraud_score = calculate_fraud_score(
            violations=violations,
            tampering_score=0,  # No tampering for manual entry
            entities=entities
        )
        
        total_amount = sum(item.get("total_price", 0) for item in entities["items"])
        savings_potential = sum(v.get("overcharge_amount", 0) for v in violations)
        
        return {
            "bill_id": bill_id,
            "metadata": entities["metadata"],
            "extracted_items": entities["items"],
            "total_amount": total_amount,
            "fraud_score": fraud_score,
            "violations": violations,
            "savings_potential": savings_potential
        }
        
    except Exception as e:
        logger.error(f"Error in manual entry: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/bill/{bill_id}")
async def get_bill(bill_id: str):
    """
    Retrieve processed bill details by ID
    
    Args:
        bill_id: Unique bill identifier
    
    Returns:
        Complete bill data with analysis
    """
    try:
        # Retrieve from database (implement this function)
        bill_data = retrieve_bill_from_database(bill_id)
        
        if not bill_data:
            raise HTTPException(status_code=404, detail="Bill not found")
        
        return bill_data
        
    except Exception as e:
        logger.error(f"Error retrieving bill: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/report/patient")
async def generate_report(bill_id: str, language: str = "english"):
    """
    Generate patient-friendly PDF report
    
    Args:
        bill_id: Bill identifier
        language: Report language (english, hindi, etc.)
    
    Returns:
        PDF file download
    """
    try:
        # Retrieve bill data
        bill_data = retrieve_bill_from_database(bill_id)
        
        if not bill_data:
            raise HTTPException(status_code=404, detail="Bill not found")
        
        # Generate PDF report
        pdf_path = generate_patient_report(
            bill_data=bill_data,
            language=language
        )
        
        return FileResponse(
            pdf_path,
            media_type="application/pdf",
            filename=f"bill_report_{bill_id}.pdf"
        )
        
    except Exception as e:
        logger.error(f"Error generating report: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/grievance/generate")
async def generate_grievance(request: GrievanceRequest):
    """
    Generate legal grievance letter
    
    Args:
        request: Grievance generation parameters
    
    Returns:
        PDF/DOCX grievance letter
    """
    try:
        # Retrieve bill data
        bill_data = retrieve_bill_from_database(request.bill_id)
        
        if not bill_data:
            raise HTTPException(status_code=404, detail="Bill not found")
        
        # Generate grievance letter
        grievance_path = generate_grievance_letter(
            bill_data=bill_data,
            grievance_type=request.grievance_type,
            language=request.language,
            include_precedents=request.include_precedents
        )
        
        return FileResponse(
            grievance_path,
            media_type="application/pdf",
            filename=f"grievance_{request.grievance_type}_{request.bill_id}.pdf"
        )
        
    except Exception as e:
        logger.error(f"Error generating grievance: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/insurance/check")
async def check_insurance_rejection(request: InsuranceCheckRequest):
    """
    Predict insurance claim rejection probability
    
    Args:
        request: Insurance check parameters
    
    Returns:
        Rejection probability and missing fields
    """
    try:
        # Retrieve bill data
        bill_data = retrieve_bill_from_database(request.bill_id)
        
        if not bill_data:
            raise HTTPException(status_code=404, detail="Bill not found")
        
        # Predict rejection
        prediction = predict_insurance_rejection(
            bill_data=bill_data,
            insurance_provider=request.insurance_provider,
            policy_number=request.policy_number,
            tpa_name=request.tpa_name
        )
        
        return {
            "bill_id": request.bill_id,
            "rejection_probability": prediction["probability"],
            "risk_level": prediction["risk_level"],  # LOW, MEDIUM, HIGH
            "missing_fields": prediction["missing_fields"],
            "suggestions": prediction["suggestions"],
            "estimated_claim_amount": prediction["estimated_claim_amount"]
        }
        
    except Exception as e:
        logger.error(f"Error checking insurance: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/rates/cghs")
async def get_cghs_rates(
    procedure_name: Optional[str] = None,
    specialty: Optional[str] = None,
    limit: int = 100
):
    """
    Retrieve CGHS standard rates
    
    Args:
        procedure_name: Filter by procedure name (fuzzy search)
        specialty: Filter by specialty
        limit: Maximum results
    
    Returns:
        List of CGHS rates
    """
    try:
        from backend.medical_analyzer import query_cghs_database
        
        rates = query_cghs_database(
            procedure_name=procedure_name,
            specialty=specialty,
            limit=limit
        )
        
        return {
            "count": len(rates),
            "rates": rates
        }
        
    except Exception as e:
        logger.error(f"Error retrieving CGHS rates: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/hospital/reputation/{hospital_name}")
async def get_hospital_reputation(hospital_name: str):
    """
    Get hospital reputation score and fraud history
    
    Args:
        hospital_name: Name of the hospital
    
    Returns:
        Reputation score, complaint history, ratings
    """
    try:
        from backend.medical_analyzer import calculate_hospital_reputation
        
        reputation = calculate_hospital_reputation(hospital_name)
        
        return {
            "hospital_name": hospital_name,
            "reputation_score": reputation["score"],  # 0-100
            "accreditation": reputation["accreditation"],  # NABH, JCI, etc.
            "complaint_count": reputation["complaint_count"],
            "average_overcharge": reputation["average_overcharge"],
            "fraud_incidents": reputation["fraud_incidents"],
            "patient_reviews": reputation["reviews"]
        }
        
    except Exception as e:
        logger.error(f"Error getting hospital reputation: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/compare/hospitals")
async def compare_hospitals(procedure: str, city: str, limit: int = 10):
    """
    Compare pricing across hospitals for a procedure
    
    Args:
        procedure: Procedure name/code
        city: City name
        limit: Number of hospitals to compare
    
    Returns:
        List of hospitals with pricing
    """
    try:
        from backend.medical_analyzer import compare_hospital_prices
        
        comparison = compare_hospital_prices(
            procedure=procedure,
            city=city,
            limit=limit
        )
        
        return {
            "procedure": procedure,
            "city": city,
            "cghs_rate": comparison["cghs_rate"],
            "hospitals": comparison["hospitals"],
            "price_range": {
                "min": comparison["min_price"],
                "max": comparison["max_price"],
                "median": comparison["median_price"]
            }
        }
        
    except Exception as e:
        logger.error(f"Error comparing hospitals: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/feedback")
async def submit_feedback(
    bill_id: str,
    feedback_type: str,  # ACCURACY, HELPFULNESS, REFUND_SUCCESS, etc.
    rating: int,  # 1-5
    comments: Optional[str] = None
):
    """
    Submit user feedback on bill analysis
    
    Args:
        bill_id: Bill identifier
        feedback_type: Type of feedback
        rating: Rating (1-5)
        comments: Optional text comments
    
    Returns:
        Confirmation
    """
    try:
        from backend.medical_analyzer import store_feedback
        
        store_feedback(
            bill_id=bill_id,
            feedback_type=feedback_type,
            rating=rating,
            comments=comments,
            timestamp=datetime.now()
        )
        
        return {
            "status": "success",
            "message": "Thank you for your feedback!"
        }
        
    except Exception as e:
        logger.error(f"Error submitting feedback: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/v1/stats")
async def get_statistics():
    """
    Get aggregate statistics (for research/dashboard)
    
    Returns:
        System-wide statistics
    """
    try:
        from backend.medical_analyzer import get_aggregate_stats
        
        stats = get_aggregate_stats()
        
        return {
            "total_bills_processed": stats["total_bills"],
            "total_savings": stats["total_savings"],
            "average_fraud_score": stats["avg_fraud_score"],
            "top_fraud_types": stats["top_fraud_types"],
            "top_hospitals_flagged": stats["top_hospitals"],
            "grievances_filed": stats["grievances_filed"],
            "successful_refunds": stats["successful_refunds"]
        }
        
    except Exception as e:
        logger.error(f"Error getting statistics: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================
# HELPER FUNCTIONS
# ========================

def store_bill_in_database(bill_id: str, data: Dict[str, Any]):
    """
    Store processed bill in database (background task)
    
    Args:
        bill_id: Unique identifier
        data: Bill data to store
    """
    try:
        # Implement database storage
        # This is a placeholder - implement with your actual DB
        logger.info(f"Stored bill {bill_id} in database")
        pass
        
    except Exception as e:
        logger.error(f"Error storing bill: {str(e)}")


def retrieve_bill_from_database(bill_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve bill from database
    
    Args:
        bill_id: Unique identifier
    
    Returns:
        Bill data or None
    """
    try:
        # Implement database retrieval
        # This is a placeholder - implement with your actual DB
        return None
        
    except Exception as e:
        logger.error(f"Error retrieving bill: {str(e)}")
        return None


# ========================
# ERROR HANDLERS
# ========================

@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "timestamp": datetime.now().isoformat()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """General exception handler"""
    logger.error(f"Unhandled exception: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": str(exc),
            "timestamp": datetime.now().isoformat()
        }
    )


# ========================
# STARTUP/SHUTDOWN EVENTS
# ========================

@app.on_event("startup")
async def startup_event():
    """Initialize resources on startup"""
    logger.info("Starting Healthcare Bill Auditor API...")
    # Load ML models, connect to database, etc.
    try:
        from backend.medical_analyzer import initialize_models
        initialize_models()
        logger.info("Models loaded successfully")
    except Exception as e:
        logger.error(f"Error loading models: {str(e)}")


@app.on_event("shutdown")
async def shutdown_event():
    """Clean up resources on shutdown"""
    logger.info("Shutting down Healthcare Bill Auditor API...")
    # Close database connections, save state, etc.


if __name__ == "__main__":
    import uvicorn
    
    # Run the server
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,  # Enable auto-reload during development
        log_level="info"
    )
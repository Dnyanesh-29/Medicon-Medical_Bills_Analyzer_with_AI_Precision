
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, field_validator
import math

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
    pre_auth_amount: Optional[float] = None

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
    # Canonical rupee amount by which bill exceeds CGHS / reference
    # For CGHS hospitals: legally enforceable overcharge
    # For non-CGHS hospitals: informational above-reference amount (may be 0.0)
    total_overcharge: float = 0.0
    total_violations: int = 0
    high_severity_count: int = 0
    medium_severity_count: int = 0
    recommendations: List[str] = Field(default_factory=list)
    can_file_cghs_complaint: bool = False
    # Derived risk metrics for UI
    fraud_risk_score: int = 0  # 0–100
    fraud_risk_label: str = "LOW RISK"
    fraud_risk_breakdown: Dict[str, int] = Field(default_factory=dict)
    insurance_rejection_probability: float = 0.0  # 0–100
    insurance_rejection_label: str = "LOW"
    insurance_rejection_reasons: List[str] = Field(default_factory=list)
    # Timeline plausibility
    timeline_plausibility_score: int = 10  # 0–10
    timeline_conflicts: List[str] = Field(default_factory=list)
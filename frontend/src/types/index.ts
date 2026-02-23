export type NABHStatus = "NABH/ NABL" | "Non-NABH" | "Not CGHS-empanelled";

export interface Hospital {
  sr_no?: number;
  hospital_name: string;
  address: string;
  nabh_status: string;
  contact_no: string;
  distance_km?: number;
}

export interface HospitalSearchRequest {
  latitude?: number;
  longitude?: number;
  radius_km?: number;
  nabh_only?: boolean;
  name_query?: string;
}

export interface HospitalSearchResponse {
  hospitals: Hospital[];
  total_count: number;
  nabh_count: number;
  non_nabh_count: number;
}

export interface BillItem {
  description: string;
  quantity: number;
  unit_price?: number;
  total_price: number;
  category?: string;
}

export interface BillData {
  hospital_name: string;
  hospital_address?: string;
  patient_name?: string;
  bill_number?: string;
  bill_date?: string;
  admission_date?: string;
  discharge_date?: string;
  items: BillItem[];
  total_amount: number;
  advance_paid?: number;
  balance_amount?: number;
  pre_auth_amount?: number;
}

export type ViolationType =
  | "package_rate_violation"
  | "balance_billing"
  | "bis_violation"
  | "suspicious_pattern"
  | "informational";

export type Severity = "high" | "medium" | "low" | "compliant" | "info";

export interface Violation {
  type: ViolationType;
  severity: Severity;
  description: string;
  item?: string;
  charged_amount?: number;
  expected_amount?: number;
  deviation_percentage?: number;
  legal_reference?: string;
  is_enforceable?: boolean;
}

export interface PriceComparison {
  item: string;
  charged_amount: number;
  cghs_rate?: number;
  cghs_procedure_matched?: string;
  match_confidence?: number;
  applicable_rate_type: string;
  deviation_percentage: number;
  is_abnormal: boolean;
}

export interface BillAnalysisResult {
  hospital_name: string;
  nabh_status: string;
  is_cghs_empanelled: boolean;
  violations: Violation[];
  price_comparisons: PriceComparison[];
  overall_risk: Severity;
  summary: string;
  /** Canonical rupee amount above CGHS / reference rates, from backend */
  total_overcharge?: number;
  total_violations: number;
  high_severity_count: number;
  medium_severity_count: number;
  recommendations: string[];
  can_file_cghs_complaint: boolean;
  // Derived risk metrics from backend
  fraud_risk_score?: number; // 0–100
  fraud_risk_label?: string;
  fraud_risk_breakdown?: Record<string, number>;
  insurance_rejection_probability?: number; // 0–100
  insurance_rejection_label?: string;
  insurance_rejection_reasons?: string[];
  timeline_plausibility_score?: number; // 0–10
  timeline_conflicts?: string[];
  document_inconsistency_details?: string;
  quantity_anomalies?: QuantityAnomaly[];
}

export interface QuantityAnomaly {
  item: string;
  quantity_billed: number;
  stay_days?: number;
  expected_max?: number;
  severity: Severity;
  reason: string;
}

/** Derived insurance/claim readiness from analysis (for UI) */
export interface InsuranceComplianceInfo {
  claimReadinessScore: number; // 0-100
  checklist: { label: string; passed: boolean; detail?: string }[];
  riskFactors: string[];
  tips: string[];
}

export interface UploadResponse {
  success: boolean;
  extracted_bill_data: BillData;
  hospital_match: {
    found: boolean;
    hospital: Hospital | null;
    match_confidence: number;
    nabh_status: string;
    is_cghs_empanelled: boolean;
    warning?: string;
  };
  analysis: BillAnalysisResult;
}

export interface StatsResponse {
  hospitals: {
    total: number;
    nabh: number;
    non_nabh: number;
  };
  procedures: {
    total: number;
  };
  matching_method: string;
}

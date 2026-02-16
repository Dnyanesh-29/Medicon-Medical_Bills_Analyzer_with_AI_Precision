
from typing import List
from app.models.schemas import (
    BillData, BillAnalysisResult, Violation, PriceComparison, 
    ViolationType, Severity
)
from app.services.validator import SemanticRateValidator
from app.services.ocr import GeminiStructurer

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
            (v.charged_amount or 0) - (v.expected_amount or 0)
            for v in violations 
            if v.type == ViolationType.PACKAGE_RATE_VIOLATION and v.charged_amount and v.expected_amount
        )
        
        # Summary (without emojis, structured text)
        if len(violations) == 0:
            summary = (
                f"This CGHS-empanelled {nabh_status} hospital's billing appears compliant with "
                "CGHS package rates and regulations."
            )
        else:
            summary = (
                f"CGHS-empanelled {nabh_status} hospital with CGHS package rates.\n\n"
                f"Detected {len(violations)} violations of CGHS package rates (legally enforceable).\n"
                f"Total overcharge: ₹{total_overcharge:,.2f}.\n\n"
                "You can ask the hospital to correct the bill, refund overcharged amounts, and you may file "
                "a complaint with CGHS authorities."
            )
        
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

        # Derived risk metrics
        fraud_score, fraud_label, fraud_breakdown = self._compute_fraud_risk(
            bill_data=bill_data,
            violations=violations,
            price_comparisons=price_comparisons,
            total_overcharge=total_overcharge,
            is_cghs=True,
        )
        rejection_prob, rejection_label, rejection_reasons = self._compute_insurance_rejection(
            bill_data=bill_data,
            violations=violations,
            overall_risk=overall_risk,
            is_cghs=True,
            total_overcharge=total_overcharge,
        )

        # Timeline plausibility
        timeline_score, timeline_conflicts = self._compute_timeline_score_and_conflicts(bill_data)

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
            can_file_cghs_complaint=True,
            fraud_risk_score=int(fraud_score),
            fraud_risk_label=fraud_label,
            fraud_risk_breakdown=fraud_breakdown,
            insurance_rejection_probability=rejection_prob,
            insurance_rejection_label=rejection_label,
            insurance_rejection_reasons=rejection_reasons,
            timeline_plausibility_score=int(timeline_score),
            timeline_conflicts=timeline_conflicts,
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
            avg_deviation = sum((pc.deviation_percentage or 0) for pc in price_comparisons) / len(price_comparisons)
        
        # Risk assessment
        info_count = sum(1 for v in violations if v.severity == Severity.INFO)
        
        if avg_deviation > 150:
            overall_risk = Severity.MEDIUM
        elif avg_deviation > 100:
            overall_risk = Severity.LOW
        else:
            overall_risk = Severity.COMPLIANT
        
        # Summary (without emojis, structured text)
        summary = (
            "IMPORTANT: This hospital is NOT in the CGHS empanelment list.\n\n"
            "This hospital is not legally bound by CGHS rates. The analysis below is for reference only.\n\n"
            "Price analysis:\n"
            f"- Average charge is {avg_deviation:.0f}% "
            f"{'higher' if avg_deviation > 0 else 'lower'} than CGHS reference rates\n"
            f"- {len([pc for pc in price_comparisons if pc.is_abnormal])} items significantly above reference rates\n\n"
            "This comparison is useful for:\n"
            "- Insurance claim negotiations\n"
            "- Understanding market pricing\n"
            "- Deciding whether to seek treatment at CGHS hospitals for future procedures\n\n"
            "Note: You cannot file a CGHS complaint against this hospital."
        )
        
        # Recommendations
        recommendations = [
            "Consider seeking treatment at CGHS-empanelled hospitals for regulated pricing",
            "Use this analysis to negotiate with your insurance company",
            "Verify if hospital follows Consumer Protection Act billing standards",
            "Check if you can claim reimbursement under any government health scheme"
        ]
        
        if avg_deviation > 100:
            recommendations.insert(0, "Charges are significantly higher than CGHS reference rates - consider price negotiation")

        # Derived risk metrics (for non-CGHS we treat CGHS differences as reference only)
        fraud_score, fraud_label, fraud_breakdown = self._compute_fraud_risk(
            bill_data=bill_data,
            violations=violations,
            price_comparisons=price_comparisons,
            total_overcharge=0.0,
            is_cghs=False,
        )
        rejection_prob, rejection_label, rejection_reasons = self._compute_insurance_rejection(
            bill_data=bill_data,
            violations=violations,
            overall_risk=overall_risk,
            is_cghs=False,
            total_overcharge=0.0,
        )

        # Timeline plausibility
        timeline_score, timeline_conflicts = self._compute_timeline_score_and_conflicts(bill_data)

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
            can_file_cghs_complaint=False,
            fraud_risk_score=int(fraud_score),
            fraud_risk_label=fraud_label,
            fraud_risk_breakdown=fraud_breakdown,
            insurance_rejection_probability=rejection_prob,
            insurance_rejection_label=rejection_label,
            insurance_rejection_reasons=rejection_reasons,
            timeline_plausibility_score=int(timeline_score),
            timeline_conflicts=timeline_conflicts,
        )

    def _compute_timeline_score_and_conflicts(self, bill_data: BillData) -> tuple[int, list[str]]:
        """
        Simple timeline plausibility: 10/10 = fully plausible, 0/10 = highly suspicious.
        Uses only admission / discharge dates that are available in the bill.
        """
        score = 10
        conflicts: list[str] = []

        if not bill_data.admission_date or not bill_data.discharge_date:
            conflicts.append("Admission or discharge date is missing on the bill.")
            score -= 3
            return max(score, 0), conflicts

        try:
            from datetime import datetime

            a = datetime.fromisoformat(bill_data.admission_date)
            d = datetime.fromisoformat(bill_data.discharge_date)
        except Exception:
            conflicts.append("Admission/discharge dates are not in a valid format.")
            score -= 2
            return max(score, 0), conflicts

        if d < a:
            conflicts.append("Discharge date/time is before admission date/time.")
            return 1, conflicts

        total_hours = (d - a).total_seconds() / 3600.0

        # Very short recorded stay with large bill value
        if total_hours < 2 and bill_data.total_amount and bill_data.total_amount > 50000:
            conflicts.append("Very short recorded stay with a high total bill amount.")
            score -= 5

        # Extremely long recorded stay
        if total_hours > 30 * 24:
            conflicts.append("Very long recorded hospital stay; please verify admission and discharge dates.")
            score -= 2

        score = max(0, min(10, score))
        return score, conflicts

    def _compute_fraud_risk(
        self,
        bill_data: BillData,
        violations: List[Violation],
        price_comparisons: List[PriceComparison],
        total_overcharge: float,
        is_cghs: bool,
    ) -> tuple:
        """
        Heuristic fraud risk score (0–100) with simple breakdown.
        This is intentionally rule-based and explainable.
        """
        # Document tampering (0–30): suspicious patterns + math inconsistencies
        doc_points = 0
        suspicious_count = sum(1 for v in violations if v.type == ViolationType.SUSPICIOUS_PATTERN)
        if suspicious_count:
            doc_points += min(30, suspicious_count * 10)

        if bill_data.items:
            items_sum = sum(item.total_price for item in bill_data.items)
            if bill_data.total_amount:
                diff = abs(items_sum - bill_data.total_amount)
                # Large mismatch between sum of items and total amount
                if diff > 0.15 * bill_data.total_amount:
                    doc_points = max(doc_points, 25)
                elif diff > 0.08 * bill_data.total_amount:
                    doc_points = max(doc_points, 15)
        doc_points = min(30, doc_points)

        # CGHS violations (0–30): only fully weighted for CGHS hospitals
        cg_points = 0
        if total_overcharge and total_overcharge > 0:
            # Overcharge bands
            if total_overcharge > 50000:
                cg_points += 20
            elif total_overcharge > 20000:
                cg_points += 15
            elif total_overcharge > 5000:
                cg_points += 10
            else:
                cg_points += 5

        high_pkg = sum(
            1 for v in violations
            if v.type in (ViolationType.PACKAGE_RATE_VIOLATION, ViolationType.BALANCE_BILLING)
            and v.severity == Severity.HIGH
        )
        if high_pkg:
            cg_points += min(10, high_pkg * 5)

        if not is_cghs:
            # For non-CGHS, treat this as overpricing signal but at half weight
            cg_points = int(cg_points * 0.5)
        cg_points = min(30, cg_points)

        # BIS non-compliance (0–20)
        bis_points = 0
        bis_high = sum(1 for v in violations if v.type == ViolationType.BIS_VIOLATION and v.severity == Severity.HIGH)
        bis_med = sum(1 for v in violations if v.type == ViolationType.BIS_VIOLATION and v.severity == Severity.MEDIUM)
        if bis_high:
            bis_points += min(15, bis_high * 8)
        if bis_med:
            bis_points += min(10, bis_med * 4)
        bis_points = min(20, bis_points)

        # Temporal anomalies (0–10)
        temporal_points = 0
        if not bill_data.admission_date or not bill_data.discharge_date:
            temporal_points += 4
        else:
            try:
                from datetime import datetime

                a = datetime.fromisoformat(bill_data.admission_date)
                d = datetime.fromisoformat(bill_data.discharge_date)
                if d < a:
                    temporal_points = 10
            except Exception:
                # If dates cannot be parsed, treat as mild anomaly
                temporal_points = max(temporal_points, 3)
        temporal_points = min(10, temporal_points)

        # Consumable padding (0–10): repeated small consumables with high deviation
        consumable_keywords = ("consumable", "syringe", "glove", "cotton", "bandage", "disposable")
        consumable_points = 0
        for pc in price_comparisons:
            name_lower = pc.item.lower()
            if any(k in name_lower for k in consumable_keywords) and pc.deviation_percentage and pc.deviation_percentage > 50:
                consumable_points += 3
                if consumable_points >= 10:
                    break
        consumable_points = min(10, consumable_points)

        total_score = doc_points + cg_points + bis_points + temporal_points + consumable_points
        total_score = max(0, min(100, total_score))

        if total_score >= 86:
            label = "CRITICAL RISK"
        elif total_score >= 61:
            label = "HIGH RISK"
        elif total_score >= 31:
            label = "MEDIUM RISK"
        else:
            label = "LOW RISK"

        breakdown = {
            "Document Tampering": int(doc_points),
            "CGHS Violations": int(cg_points),
            "BIS Non-compliance": int(bis_points),
            "Temporal Anomalies": int(temporal_points),
            "Consumable Padding": int(consumable_points),
        }
        return int(total_score), label, breakdown

    def _compute_insurance_rejection(
        self,
        bill_data: BillData,
        violations: List[Violation],
        overall_risk: Severity,
        is_cghs: bool,
        total_overcharge: float,
    ) -> tuple:
        """
        Heuristic probability (0–100) that an insurer/TPA will raise issues
        or reject part of the claim, based on missing fields and violations.
        """
        prob = 10.0
        reasons: list[str] = []

        # Missing basic fields
        if not bill_data.bill_number:
            prob += 15
            reasons.append("Bill number is missing on the invoice.")
        if not bill_data.bill_date:
            prob += 10
            reasons.append("Bill date is missing.")
        if not bill_data.patient_name:
            prob += 8
            reasons.append("Patient name is missing.")
        if not bill_data.items:
            prob += 20
            reasons.append("No itemized charges are present (insurers expect line items).")

        # Severity of violations
        high_count = sum(1 for v in violations if v.severity == Severity.HIGH)
        medium_count = sum(1 for v in violations if v.severity == Severity.MEDIUM)

        if high_count:
            prob += min(25, high_count * 8)
            reasons.append("High-severity billing issues were detected.")
        if medium_count:
            prob += min(15, medium_count * 4)
            reasons.append("Several medium-severity billing issues were detected.")

        # CGHS overcharge (for empanelled hospitals this is serious)
        if is_cghs and total_overcharge and total_overcharge > 0:
            prob += min(20, (total_overcharge / 5000.0) * 5.0)
            reasons.append("Total charges exceed CGHS package rates for this empanelled hospital.")

        # Overall risk band
        if overall_risk == Severity.HIGH:
            prob += 15
        elif overall_risk == Severity.MEDIUM:
            prob += 7

        # Long / unclear stay
        if bill_data.admission_date and bill_data.discharge_date:
            try:
                from datetime import datetime

                a = datetime.fromisoformat(bill_data.admission_date)
                d = datetime.fromisoformat(bill_data.discharge_date)
                days = (d - a).days
                if days > 15:
                    prob += 5
                    reasons.append("Long hospital stay may trigger closer scrutiny from insurer.")
            except Exception:
                pass

        prob = max(0.0, min(100.0, prob))
        if prob > 70:
            label = "HIGH"
        elif prob >= 40:
            label = "MEDIUM"
        else:
            label = "LOW"

        return round(prob, 1), label, reasons

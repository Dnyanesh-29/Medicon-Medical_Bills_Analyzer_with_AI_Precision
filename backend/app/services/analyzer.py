
from typing import List, Optional
from datetime import datetime
from app.models.schemas import (
    BillData, BillAnalysisResult, Violation, PriceComparison,
    ViolationType, Severity, QuantityAnomaly
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
        
        # 3. Pre-auth Balance Billing Check
        if bill_data.pre_auth_amount and bill_data.total_amount > bill_data.pre_auth_amount:
            diff = bill_data.total_amount - bill_data.pre_auth_amount
            violations.append(Violation(
                type=ViolationType.BALANCE_BILLING,
                severity=Severity.HIGH,
                description=f"Initial pre-authorization was ₹{bill_data.pre_auth_amount:,.0f}, but bill is ₹{bill_data.total_amount:,.0f} (₹{diff:,.0f} extra).",
                charged_amount=bill_data.total_amount,
                expected_amount=bill_data.pre_auth_amount,
                deviation_percentage=(diff / bill_data.pre_auth_amount) * 100,
                legal_reference="IRDAI Guidelines on Cashless Claims",
                is_enforceable=True
            ))

        # 4. Generate price comparisons
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
        
        # Calculate canonical total overcharge (₹ above CGHS rate)
        # Includes both direct package violations and explicit balance billing where we have amounts.
        total_overcharge = 0.0
        for v in violations:
            if v.charged_amount is None or v.expected_amount is None:
                continue
            if v.charged_amount <= v.expected_amount:
                continue
            if v.type == ViolationType.PACKAGE_RATE_VIOLATION:
                total_overcharge += (v.charged_amount - v.expected_amount)
        
        # Summary (without emojis, structured text)
        if len(violations) == 0:
            summary = (
                f"This CGHS-empanelled {nabh_status} hospital's billing appears compliant with "
                "CGHS package rates and regulations."
            )
        else:
            # Split violations count
            pkg_violations = sum(1 for v in violations if v.type == ViolationType.PACKAGE_RATE_VIOLATION)
            ins_violations = sum(1 for v in violations if v.type == ViolationType.BALANCE_BILLING)
            
            violation_msg = f"Detected {pkg_violations} CGHS rate violations"
            if ins_violations > 0:
                violation_msg += f" + {ins_violations} insurance billing issue"
            
            summary_lines = [
                f"CGHS-empanelled {nabh_status} hospital with CGHS package rates.",
                "",
                f"{violation_msg} (legally enforceable).",
            ]
            if total_overcharge > 0:
                summary_lines.append(f"Estimated total overcharge vs CGHS rates: ₹{total_overcharge:,.2f}.")
            summary_lines.extend(
                [
                    "",
                    "You can ask the hospital to correct the bill, refund overcharged amounts, and you may file "
                    "a complaint with CGHS authorities.",
                ]
            )
            summary = "\n".join(summary_lines)
        
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
        fraud_score, fraud_label, fraud_breakdown, doc_details = self._compute_fraud_risk(
            bill_data=bill_data,
            violations=violations,
            price_comparisons=price_comparisons,
            total_overcharge=total_overcharge,
            is_cghs=True,
            quantity_anomalies=self._detect_quantity_anomalies(bill_data),
        )
        rejection_prob, rejection_label, rejection_reasons = self._compute_insurance_rejection(
            bill_data=bill_data,
            violations=violations,
            overall_risk=overall_risk,
            is_cghs=True,
            total_overcharge=total_overcharge,
            quantity_anomalies=self._detect_quantity_anomalies(bill_data),
        )

        # Quantity anomaly detection
        quantity_anomalies = self._detect_quantity_anomalies(bill_data)

        # Timeline plausibility
        timeline_score, timeline_conflicts = self._compute_timeline_score_and_conflicts(bill_data, quantity_anomalies)

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
            total_overcharge=total_overcharge,
            document_inconsistency_details=doc_details,
            quantity_anomalies=quantity_anomalies,
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
        detected_anomalies = self._detect_quantity_anomalies(bill_data)
        fraud_score, fraud_label, fraud_breakdown, doc_details = self._compute_fraud_risk(
            bill_data=bill_data,
            violations=violations,
            price_comparisons=price_comparisons,
            total_overcharge=0.0,
            is_cghs=False,
            quantity_anomalies=detected_anomalies,
        )
        rejection_prob, rejection_label, rejection_reasons = self._compute_insurance_rejection(
            bill_data=bill_data,
            violations=violations,
            overall_risk=overall_risk,
            is_cghs=False,
            total_overcharge=0.0,
            quantity_anomalies=detected_anomalies,
        )

        # Quantity anomaly detection (single pass — reuse from above)
        quantity_anomalies = detected_anomalies

        # Timeline plausibility
        timeline_score, timeline_conflicts = self._compute_timeline_score_and_conflicts(bill_data, quantity_anomalies)

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
            total_overcharge=0.0,
            document_inconsistency_details=doc_details,
            quantity_anomalies=quantity_anomalies,
        )

    def _detect_quantity_anomalies(self, bill_data: BillData) -> List[QuantityAnomaly]:
        """
        Detects per-item quantity irregularities relative to hospital stay duration.
        Applies a set of heuristics covering consumables, consultations, lab tests,
        drugs, meals, and physiotherapy sessions.
        """
        anomalies: List[QuantityAnomaly] = []

        # --- compute stay_days from dates ---
        stay_days: Optional[int] = None
        if bill_data.admission_date and bill_data.discharge_date:
            try:
                a = datetime.fromisoformat(bill_data.admission_date.split("T")[0])
                d = datetime.fromisoformat(bill_data.discharge_date.split("T")[0])
                diff = (d - a).days
                stay_days = max(1, diff) if diff >= 0 else None
            except Exception:
                pass
        # fallback: if no dates, treat everything as 1-day stay for relative checks
        effective_days = stay_days if stay_days else 1

        # ── Rule definitions ──────────────────────────────────────────────────
        # Each rule: (keyword_list, max_per_day_multiplier, severity, reason_template)
        #   max_abs: optional absolute cap regardless of stay length
        #   max_per_day: relative to stay duration
        CONSUMABLE_RULES = [
            {
                "keywords": ["mask", "face mask", "surgical mask", "n95"],
                "max_per_day": 4,  # 4 masks per day is generous
                "severity_thresholds": {"high": 10, "medium": 5},
                "label": "mask",
                "reason": "Surgical masks are typically changed 1-3 times per day per patient. {qty} masks for a {days}-day stay ({rate:.1f}/day) is unusually high.",
            },
            {
                "keywords": ["glove", "latex glove", "examination glove"],
                "max_per_day": 10,
                "severity_thresholds": {"high": 30, "medium": 20},
                "label": "gloves",
                "reason": "{qty} gloves for a {days}-day stay ({rate:.1f}/day) is excessive. Normal usage is 4-8 pairs/day for a general ward patient.",
            },
            {
                "keywords": ["syringe"],
                "max_per_day": 8,
                "severity_thresholds": {"high": 25, "medium": 12},
                "label": "syringes",
                "reason": "{qty} syringes over {days} days ({rate:.1f}/day). Unless patient is ICU/multi-IV, more than 8/day is questionable.",
            },
            {
                "keywords": ["cannula", "iv cannula", "iv set", "iv line"],
                "max_per_day": 2,
                "severity_thresholds": {"high": 5, "medium": 3},
                "label": "IV cannulas",
                "reason": "{qty} IV cannulas over {days} days. Standard practice replaces cannula every 72 hrs; {rate:.1f}/day is an anomaly.",
            },
            {
                "keywords": ["cotton", "gauze", "bandage"],
                "max_per_day": 5,
                "severity_thresholds": {"high": 20, "medium": 10},
                "label": "dressing items",
                "reason": "{qty} dressing/cotton units over {days} days ({rate:.1f}/day). Routine wound care uses 2-3 per day.",
            },
            {
                "keywords": ["catheter", "foley", "urinary catheter"],
                "max_per_day": 1,
                "severity_thresholds": {"high": 3, "medium": 2},
                "label": "catheters",
                "reason": "{qty} catheters billed across {days} days. A catheter is a single-use device; more than 1-2 per stay warrants explanation.",
            },
            {
                "keywords": ["diaper", "adult diaper"],
                "max_per_day": 4,
                "severity_thresholds": {"high": 15, "medium": 8},
                "label": "diapers",
                "reason": "{qty} adult diapers for {days} days ({rate:.1f}/day) is high unless intensive care; standard ward use is 2-3/day.",
            },
            {
                "keywords": ["nebulizer", "nebulisation", "nebulization"],
                "max_per_day": 4,
                "severity_thresholds": {"high": 10, "medium": 6},
                "label": "nebulization sessions",
                "reason": "{qty} nebulization sessions over {days} days ({rate:.1f}/day). Respiratory protocol rarely exceeds 4 per day.",
            },
        ]

        CONSULTATION_RULES = [
            {
                "keywords": ["consultation", "doctor visit", "visit charge", "physician fee"],
                "max_per_day": 3,
                "severity_thresholds": {"high": 5, "medium": 4},
                "label": "daily consultations",
                "reason": "{qty} consultation charges over {days} days ({rate:.1f}/day). CGHS caps one consultation per specialty per day; multiple daily consultations are a common padding tactic.",
            },
        ]

        LAB_RULES = [
            {
                "keywords": ["cbc", "complete blood count", "blood count", "hemogram", "haemogram"],
                "max_per_day_abs": 1,  # 1 CBC per day is the ceiling
                "severity_thresholds": {"high": 3, "medium": 2},
                "label": "CBC / blood count tests",
                "reason": "{qty} CBC tests over {days} days. Repeated daily CBCs might be valid in ICU, but {qty} total is suspicious for a general ward admission.",
            },
            {
                "keywords": ["x-ray", "xray", "chest xray", "x ray chest"],
                "max_per_stay": 3,  # absolute cap
                "severity_thresholds": {"high": 5, "medium": 3},
                "label": "X-rays",
                "reason": "{qty} X-rays billed during stay. Unless treating a fracture or acute respiratory condition, more than 2-3 X-rays is unusual.",
            },
        ]

        MEAL_RULES = [
            {
                "keywords": ["diet charge", "meal charge", "food charge", "meal", "diet"],
                "max_per_day": 3,
                "severity_thresholds": {"high": 5, "medium": 4},
                "label": "meal charges",
                "reason": "{qty} meal charges for {days} days ({rate:.1f}/day). Standard is 3 meals/day; any excess is billing padding.",
            },
        ]

        PHYSIO_RULES = [
            {
                "keywords": ["physiotherapy", "physio", "physio session"],
                "max_per_day": 2,
                "severity_thresholds": {"high": 3, "medium": 2},
                "label": "physiotherapy sessions/day",
                "reason": "{qty} physiotherapy sessions over {days} days ({rate:.1f}/day). More than 2 sessions/day is excessive ─ flag for review.",
            },
        ]

        ROOM_RULES = [
            {
                "keywords": ["room", "ward", "icu", "bed", "accommodation"],
                "max_per_day": 1,
                "severity_thresholds": {"high": 1.5, "medium": 1.1},
                "label": "room days",
                "reason": "Billed {qty} days of room/bed charges for a {days}-day stay. This is a direct timeline discrepancy and clear billing error.",
            },
        ]

        all_rules = CONSUMABLE_RULES + CONSULTATION_RULES + LAB_RULES + MEAL_RULES + PHYSIO_RULES + ROOM_RULES

        for item in bill_data.items:
            name_lower = item.description.lower()
            qty = item.quantity or 1.0

            for rule in all_rules:
                if not any(kw in name_lower for kw in rule["keywords"]):
                    continue

                high_thr = rule["severity_thresholds"]["high"]
                med_thr  = rule["severity_thresholds"]["medium"]

                # Determine effective threshold
                if "max_per_stay" in rule:
                    effective_max = rule["max_per_stay"]
                elif "max_per_day_abs" in rule:
                    effective_max = rule["max_per_day_abs"] * effective_days
                elif "max_per_day" in rule:
                    effective_max = rule["max_per_day"] * effective_days
                else:
                    effective_max = None

                rate = qty / effective_days

                if effective_max and qty <= effective_max:
                    continue  # within normal range

                # Determine severity by per-day rate, not absolute
                per_day_rate = qty / effective_days
                if per_day_rate >= high_thr:
                    sev = Severity.HIGH
                elif per_day_rate >= med_thr:
                    sev = Severity.MEDIUM
                else:
                    sev = Severity.LOW

                reason = rule["reason"].format(
                    qty=int(qty),
                    days=effective_days,
                    rate=rate,
                    stay_desc=f"{effective_days} day{'s' if effective_days != 1 else ''}"
                )

                anomalies.append(QuantityAnomaly(
                    item=item.description,
                    quantity_billed=qty,
                    stay_days=stay_days,
                    expected_max=effective_max,
                    severity=sev,
                    reason=reason,
                ))
                break  # one rule match per item is enough

        return anomalies

    def _compute_timeline_score_and_conflicts(self, bill_data: BillData, quantity_anomalies: Optional[List[QuantityAnomaly]] = None) -> tuple[int, list[str]]:
        """
        Simple timeline plausibility: 10/10 = fully plausible, 0/10 = highly suspicious.
        Uses admission / discharge dates and quantity anomaly timeline mismatches.
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

        # Quantity anomalies directly conflict with timeline
        if quantity_anomalies:
            for anomaly in quantity_anomalies:
                if anomaly.severity == Severity.HIGH:
                    conflicts.append(f"Timeline mismatch: {anomaly.reason}")
                    score -= 3
                elif anomaly.severity == Severity.MEDIUM:
                    conflicts.append(f"Timeline mismatch: {anomaly.reason}")
                    score -= 1

        score = max(0, min(10, score))
        return score, conflicts

    def _compute_fraud_risk(
        self,
        bill_data: BillData,
        violations: List[Violation],
        price_comparisons: List[PriceComparison],
        total_overcharge: float,
        is_cghs: bool,
        quantity_anomalies: Optional[List] = None,
        timeline_score: int = 10,
    ) -> tuple:
        """
        Heuristic fraud risk score (0–100) with simple breakdown.
        Also returns specific explanation for document inconsistencies if any.
        """
        doc_details_msg = None
        # Document / math inconsistencies (0–30): suspicious patterns + math inconsistencies
        doc_points = 0
        suspicious_count = sum(1 for v in violations if v.type == ViolationType.SUSPICIOUS_PATTERN)
        if suspicious_count:
            doc_points += min(30, suspicious_count * 10)

        if bill_data.items:
            items_sum = sum(item.total_price for item in bill_data.items)
            n_items = len(bill_data.items)
            if bill_data.total_amount and items_sum > 0:
                diff = bill_data.total_amount - items_sum  # signed: positive means total > items_sum
                abs_diff = abs(diff)
                gap_pct = (abs_diff / bill_data.total_amount) * 100

                # Check if the gap is plausibly just GST (~5% on items_sum)
                expected_gst_5pct  = items_sum * 0.05
                expected_gst_18pct = items_sum * 0.18
                actual_gap_pct_of_items = (abs_diff / items_sum) * 100

                # Large gap (>15% of total) ─ almost certainly not just GST
                if abs_diff > 0.15 * bill_data.total_amount:
                    doc_points = max(doc_points, 25)

                    if actual_gap_pct_of_items <= 7:
                        # Looks like ~5% GST
                        doc_details_msg = (
                            f"OCR extracted {n_items} line items totalling ₹{items_sum:,.0f}.\n"
                            f"Actual bill total: ₹{bill_data.total_amount:,.0f}.\n"
                            f"Gap: ₹{abs_diff:,.0f} ({gap_pct:.1f}% of total) — "
                            f"consistent with 5% GST on itemized charges (expected ~₹{expected_gst_5pct:,.0f})."
                        )
                    else:
                        # Gap is much larger than GST can account for
                        likely_gst = round(items_sum * 0.05 / 100) * 100  # round to nearest ₹100
                        likely_remaining = abs_diff - likely_gst

                        causes = []
                        if any(
                            kw in item.description.lower()
                            for item in bill_data.items
                            for kw in ("pharmacy", "drug", "medicine", "tablet", "injection")
                        ):
                            causes.append("Additional pharmacy / medicine charges")
                        causes.append("Consumables and surgical supplies billed separately")
                        if likely_gst > 0:
                            causes.append(f"GST at 5%  ≈ ₹{likely_gst:,.0f}")
                        causes.append("Nursing / procedure fees not extracted by OCR")
                        causes.append("Rounding and miscellaneous charges")

                        causes_str = "\n  • ".join(causes)
                        doc_details_msg = (
                            f"OCR extracted {n_items} line items totalling ₹{items_sum:,.0f}.\n"
                            f"Actual bill total: ₹{bill_data.total_amount:,.0f}.\n"
                            f"Gap: ₹{abs_diff:,.0f} ({gap_pct:.1f}% of total).\n\n"
                            f"A gap this large ({actual_gap_pct_of_items:.1f}% of extracted items) "
                            f"is mathematically too big to be GST alone "
                            f"(5% GST would only be ~₹{expected_gst_5pct:,.0f}).\n"
                            f"Likely causes:\n  • {causes_str}\n\n"
                            f"⚠ Request a complete itemized breakdown from the hospital to account "
                            f"for all ₹{abs_diff:,.0f} in unlisted charges."
                        )

                # Moderate gap (8–15% of total) ─ might be GST + minor omissions
                elif abs_diff > 0.08 * bill_data.total_amount:
                    doc_points = max(doc_points, 15)
                    if actual_gap_pct_of_items <= 7:
                        doc_details_msg = (
                            f"OCR extracted {n_items} line items totalling ₹{items_sum:,.0f}.\n"
                            f"Actual bill total: ₹{bill_data.total_amount:,.0f}.\n"
                            f"Gap: ₹{abs_diff:,.0f} ({gap_pct:.1f}% of total) — "
                            f"likely 5% GST (~₹{expected_gst_5pct:,.0f}) plus minor unlisted charges."
                        )
                    else:
                        doc_details_msg = (
                            f"OCR extracted {n_items} line items totalling ₹{items_sum:,.0f}.\n"
                            f"Actual bill total: ₹{bill_data.total_amount:,.0f}.\n"
                            f"Gap: ₹{abs_diff:,.0f} ({gap_pct:.1f}% of total) — "
                            f"some charges may not have been captured by OCR. "
                            f"Request itemized bill to verify."
                        )

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

        unbundled_count = sum(1 for v in violations if "Unbundled" in v.description)
        if unbundled_count > 0:
            cg_points += min(15, unbundled_count * 8)

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

        # Temporal anomalies (0–20)
        temporal_points = max(0, (10 - timeline_score) * 2)
        temporal_points = min(20, temporal_points)

        # Quantity / consumable padding (0–15)
        # Replaces the old narrow CGHS-rate-only consumable check.
        # Anomalies are detected independently of rate data, so they apply to all bills.
        padding_points = 0
        if quantity_anomalies:
            high_anomalies = sum(1 for a in quantity_anomalies if a.severity == Severity.HIGH)
            med_anomalies  = sum(1 for a in quantity_anomalies if a.severity == Severity.MEDIUM)
            padding_points += min(10, high_anomalies * 5)
            padding_points += min(5,  med_anomalies  * 2)
        else:
            # Fallback: old price-deviation-only check
            consumable_keywords = ("consumable", "syringe", "glove", "cotton", "bandage", "disposable")
            for pc in price_comparisons:
                name_lower = pc.item.lower()
                if any(k in name_lower for k in consumable_keywords) and pc.deviation_percentage and pc.deviation_percentage > 50:
                    padding_points += 3
                    if padding_points >= 10:
                        break
        padding_points = min(15, padding_points)

        total_score = doc_points + cg_points + bis_points + temporal_points + padding_points
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
            "Document inconsistencies": int(doc_points),
            "CGHS Violations": int(cg_points),
            "BIS Non-compliance": int(bis_points),
            "Temporal Anomalies": int(temporal_points),
            "Quantity Padding": int(padding_points),
        }
        return int(total_score), label, breakdown, doc_details_msg

    def _compute_insurance_rejection(
        self,
        bill_data: BillData,
        violations: List[Violation],
        overall_risk: Severity,
        is_cghs: bool,
        total_overcharge: float,
        quantity_anomalies: Optional[List] = None,
    ) -> tuple:
        """
        Heuristic probability (0–100) that an insurer/TPA will raise issues
        or reject part of the claim, based on missing fields and violations.
        Tuned to be conservative: clean bills sit in ~10–30%, clearly bad
        bills can reach 70–90%.
        """
        prob = 5.0
        reasons: list[str] = []

        # Missing basic fields
        if not bill_data.bill_number:
            prob += 20
            reasons.append("Bill number is missing (+20% risk): Essential for claim tracking.")
        if not bill_data.bill_date:
            prob += 10
            reasons.append("Bill date is missing (+10% risk): Prevents timeline verification.")
        if not bill_data.patient_name:
            prob += 8
            reasons.append("Patient name is missing (+8% risk): Basic identity check failed.")
        if not bill_data.items:
            prob += 25
            reasons.append("No itemized charges (+25% risk): Insurers strictly reject aggregated lump-sums without line-item breakdowns.")

        # Severity of violations
        high_count = sum(1 for v in violations if v.severity == Severity.HIGH)
        medium_count = sum(1 for v in violations if v.severity == Severity.MEDIUM)

        if high_count:
            added_prob = min(18, high_count * 6)
            prob += added_prob
            reasons.append(f"High-severity billing issues (+{added_prob}% risk): Direct package rate violations or missing critical standards.")
        if medium_count:
            added_prob = min(12, medium_count * 3)
            prob += added_prob
            reasons.append(f"Medium-severity billing issues (+{added_prob}% risk): Non-compliance with expected billing norms.")

        # CGHS overcharge (for empanelled hospitals this is serious)
        if is_cghs and total_overcharge and total_overcharge > 0:
            added_prob = min(18, (total_overcharge / 10000.0) * 8.0)
            prob += added_prob
            reasons.append(f"CGHS Overcharge (+{added_prob:.1f}% risk): Billed amount exceeds statutory limits for empanelled hospitals.")
            
            if bill_data.total_amount and total_overcharge > (0.5 * bill_data.total_amount):
                prob += 25
                reasons.append("Extreme Overcharging (+25.0% risk): Total overcharge exceeds 50% of the entire bill amount. This routinely triggers mandatory TPA audits.")

        # Unbundled charges
        unbundled_count = sum(1 for v in violations if "Unbundled" in v.description)
        if unbundled_count > 0:
            added_prob = min(25, unbundled_count * 10)
            prob += added_prob
            reasons.append(f"Unbundled Charges Detected ({unbundled_count} instances) (+{added_prob:.1f}% risk): Insurers strictly reject separate billing for items that should be part of a package or room rent.")

        # Balance billing deviation vs pre-auth
        balance_billing_v = next(
            (v for v in violations if v.type == ViolationType.BALANCE_BILLING), None
        )
        if balance_billing_v and balance_billing_v.deviation_percentage:
            dev = balance_billing_v.deviation_percentage
            if dev > 50:
                added_prob = min(20, dev * 0.25)  # up to +20%
                prob += added_prob
                reasons.append(
                    f"Severe balance billing (+{added_prob:.1f}% risk): Bill is {dev:.0f}% above pre-authorization "
                    f"(₹{balance_billing_v.charged_amount:,.0f} vs approved ₹{balance_billing_v.expected_amount:,.0f}). "
                    f"TPAs routinely cap payment at authorized amount."
                )
            elif dev > 20:
                added_prob = min(10, dev * 0.2)
                prob += added_prob
                reasons.append(
                    f"Balance billing overshoot (+{added_prob:.1f}% risk): Bill exceeds pre-auth by {dev:.0f}%."
                )

        # Quantity anomalies flagged by the anomaly detector
        if quantity_anomalies:
            high_qa = sum(1 for a in quantity_anomalies if a.severity == Severity.HIGH)
            med_qa  = sum(1 for a in quantity_anomalies if a.severity == Severity.MEDIUM)
            if high_qa:
                added_prob = min(15, high_qa * 5)
                prob += added_prob
                reasons.append(
                    f"Excessive consumable quantities ({high_qa} HIGH anomal{'ies' if high_qa>1 else 'y'}) (+{added_prob}% risk): "
                    f"Unusually high quantity of consumables is a common padding pattern that insurers flag."
                )
            if med_qa:
                added_prob = min(8, med_qa * 3)
                prob += added_prob
                reasons.append(
                    f"Elevated consumable quantities ({med_qa} MEDIUM anomal{'ies' if med_qa>1 else 'y'}) (+{added_prob}% risk): "
                    f"Consumable usage above expected norms."
                )

        # Overall risk band
        if overall_risk == Severity.HIGH:
            prob += 10
        elif overall_risk == Severity.MEDIUM:
            prob += 5

        # Long / unclear stay
        if bill_data.admission_date and bill_data.discharge_date:
            try:
                from datetime import datetime
                a = datetime.fromisoformat(bill_data.admission_date.split("T")[0])
                d = datetime.fromisoformat(bill_data.discharge_date.split("T")[0])
                days = (d - a).days
                if days > 15:
                    prob += 5
                    reasons.append(f"Extended hospital stay ({days} days) (+5% risk): Automatically flags for closer manual scrutiny by TPA.")
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

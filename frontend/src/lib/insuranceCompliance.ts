import type { BillData, BillAnalysisResult, InsuranceComplianceInfo } from "@/types";

/**
 * Derive insurance/claim readiness from bill analysis for display.
 * Used for the Insurance Compliance section in the report.
 */
export function getInsuranceComplianceInfo(
  analysis: BillAnalysisResult,
  billData: BillData
): InsuranceComplianceInfo {
  const checklist: { label: string; passed: boolean; detail?: string }[] = [];
  const riskFactors: string[] = [];
  const tips: string[] = [];

  // CGHS / empanelment
  const cghsOk = analysis.is_cghs_empanelled;
  checklist.push({
    label: "Hospital CGHS / reference rate eligible",
    passed: cghsOk,
    detail: cghsOk ? "Empanelled – rates comparable" : "Non-empanelled – use as reference only",
  });

  // NABH
  const nabhOk = analysis.nabh_status?.toLowerCase().includes("nabh") ?? false;
  checklist.push({
    label: "NABH/NABL accreditation",
    passed: nabhOk,
    detail: analysis.nabh_status || "Not verified",
  });

  // No high-severity violations
  const noHighViolations = analysis.high_severity_count === 0;
  checklist.push({
    label: "No high-severity rate violations",
    passed: noHighViolations,
    detail: noHighViolations ? "None" : `${analysis.high_severity_count} high-severity issue(s)`,
  });

  // Itemization present
  const hasItemization = (billData.items?.length ?? 0) > 0 || analysis.price_comparisons.length > 0;
  checklist.push({
    label: "Itemized bill / line-item match",
    passed: hasItemization,
    detail: hasItemization ? "Available" : "Missing or not matched",
  });

  // Overcharge: prefer backend canonical value if provided
  const totalOvercharge =
    analysis.total_overcharge ??
    analysis.violations.reduce((acc, v) => {
      if (v.charged_amount != null && v.expected_amount != null && v.charged_amount > v.expected_amount)
        return acc + (v.charged_amount - v.expected_amount);
      return acc;
    }, 0);
  const noSignificantOvercharge = totalOvercharge <= 0;
  checklist.push({
    label: "Within reference rates (no significant overcharge)",
    passed: noSignificantOvercharge,
    detail: noSignificantOvercharge ? "Yes" : `Est. overcharge ₹${Math.round(totalOvercharge).toLocaleString()}`,
  });

  // Risk factors for tips
  if (!noHighViolations) riskFactors.push("High-severity rate violations may trigger claim scrutiny.");
  if (totalOvercharge > 0) riskFactors.push("Overcharged amounts may be disputed by insurer.");
  if (!nabhOk) riskFactors.push("Non-NABH hospitals may have different insurer acceptance.");
  if (!hasItemization) riskFactors.push("Missing itemization can delay claim processing.");

  // Tips
  if (analysis.recommendations?.length) tips.push(...analysis.recommendations.slice(0, 3));
  if (totalOvercharge > 0) tips.push("Request hospital to justify charges or align with CGHS/reference rates before filing.");
  if (analysis.can_file_cghs_complaint) tips.push("You may file a CGHS complaint for rate violations.");
  if (tips.length === 0) tips.push("Bill appears suitable for claim submission; keep this report for records.");

  // Score 0–100: compliant base, deduct for violations and overcharge
  let score = 100;
  if (!cghsOk) score -= 15;
  if (!nabhOk) score -= 10;
  if (!noHighViolations) score -= Math.min(30, analysis.high_severity_count * 15);
  if (analysis.medium_severity_count > 0) score -= Math.min(20, analysis.medium_severity_count * 5);
  if (!noSignificantOvercharge) score -= Math.min(25, Math.floor(totalOvercharge / 5000) * 5);
  if (!hasItemization) score -= 10;
  score = Math.max(0, Math.min(100, score));

  return {
    claimReadinessScore: score,
    checklist,
    riskFactors,
    tips,
  };
}

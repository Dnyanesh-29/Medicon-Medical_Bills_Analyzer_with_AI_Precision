"use client";

import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Outfit } from "next/font/google";
import {
  CheckCircle2, AlertTriangle, AlertOctagon, Info,
  Building2, ArrowRight, BadgeCheck, Activity,
  PieChart as PieChartIcon, ShieldAlert,
  ChevronDown, ChevronUp, Package2
} from "lucide-react";
import { BillData, BillAnalysisResult } from "@/types";
import { cn } from "@/lib/utils";
import { getInsuranceComplianceInfo } from "@/lib/insuranceCompliance";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";
import Chatbot from "./Chatbot";

const fontHeading = Outfit({ subsets: ["latin"], weight: ["400", "500", "600", "700"] });

interface AnalysisResultProps {
  billData: BillData;
  analysis: BillAnalysisResult;
}

const formatDate = (dateString?: string) => {
  if (!dateString) return "—";
  const d = new Date(dateString);
  if (isNaN(d.getTime())) return dateString;
  return d.toLocaleDateString("en-IN", { year: "numeric", month: "short", day: "numeric" });
};

function getStayDays(admission?: string, discharge?: string): number | null {
  if (!admission || !discharge) return null;
  const a = new Date(admission).getTime();
  const d = new Date(discharge).getTime();
  if (isNaN(a) || isNaN(d) || d < a) return null;
  return Math.max(1, Math.ceil((d - a) / (24 * 60 * 60 * 1000)));
}

const FRAUD_BREAKDOWN_MAX: Record<string, number> = {
  "Document inconsistencies": 30,
  "CGHS Violations": 30,
  "BIS Non-compliance": 20,
  "Temporal Anomalies": 10,
  "Consumable Padding": 10,
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function CustomChartTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="bg-white/95 backdrop-blur-md border border-stone-200/50 rounded-xl shadow-xl p-4 text-xs font-sans">
      <p className="font-semibold text-stone-800 mb-3 max-w-[200px]">{label}</p>
      {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
      {payload.map((p: any) => (
        <div key={p.dataKey} className="flex items-center gap-3 mb-1.5">
          <span className="w-2.5 h-2.5 rounded-full shadow-sm" style={{ background: p.fill }} />
          <span className="text-stone-500 font-medium">{p.name}:</span>
          <span className="font-mono font-semibold text-stone-900 ml-auto">₹{p.value?.toLocaleString()}</span>
        </div>
      ))}
    </div>
  );
}

export default function AnalysisResult({ billData, analysis }: AnalysisResultProps) {
  const [showAllItems, setShowAllItems] = useState(false);
  const [showBreakdown, setShowBreakdown] = useState(true);

  const insuranceInfo = useMemo(() => getInsuranceComplianceInfo(analysis, billData), [analysis, billData]);
  const fraudBreakdown = analysis.fraud_risk_breakdown ?? {};
  const isCghs = analysis.is_cghs_empanelled;
  const isNabh = (analysis.nabh_status || "").toLowerCase().includes("nabh") && !(analysis.nabh_status || "").toLowerCase().includes("non-nabh");

  const rejectionProb = analysis.insurance_rejection_probability ??
    Math.max(0, Math.min(100, 100 - insuranceInfo.claimReadinessScore));
  const rejectionLabel = analysis.insurance_rejection_label ??
    (rejectionProb > 70 ? "HIGH" : rejectionProb >= 40 ? "MEDIUM" : "LOW");
  const rejectionReasons = analysis.insurance_rejection_reasons?.length
    ? analysis.insurance_rejection_reasons : insuranceInfo.riskFactors;

  const totalExtra = analysis.total_overcharge ??
    analysis.violations.reduce((acc, v) => {
      if (v.charged_amount && v.expected_amount && v.charged_amount > v.expected_amount)
        return acc + (v.charged_amount - v.expected_amount);
      return acc;
    }, 0);

  const { totalSavingsPotential } = useMemo(() => {
    let savings = 0;
    for (const pc of analysis.price_comparisons) {
      if (pc.cghs_rate != null && pc.charged_amount > pc.cghs_rate)
        savings += pc.charged_amount - pc.cghs_rate;
    }
    if (isCghs && typeof analysis.total_overcharge === "number")
      savings = Math.max(0, analysis.total_overcharge);
    return { totalSavingsPotential: savings };
  }, [analysis.price_comparisons, isCghs, analysis.total_overcharge]);

  const stayDays = useMemo(() =>
    getStayDays(billData.admission_date, billData.discharge_date),
    [billData.admission_date, billData.discharge_date]);

  const chartData = analysis.price_comparisons
    .filter((pc) => pc.cghs_rate && pc.is_abnormal)
    .map((pc) => ({
      name: pc.item.length > 22 ? pc.item.slice(0, 22) + "…" : pc.item,
      fullName: pc.item,
      charged: Math.round(pc.charged_amount),
      cghs: Math.round(pc.cghs_rate ?? 0),
    }));

  const displayItems = showAllItems ? analysis.price_comparisons : analysis.price_comparisons.slice(0, 5);
  const bisViolation = analysis.violations.find((v) => v.type === "bis_violation" && v.legal_reference);

  const outcomeLine = analysis.total_violations === 0
    ? "Everything we checked matches the reference rates."
    : (totalExtra > 0 || totalSavingsPotential > 0)
      ? `We found ₹${Math.round(totalExtra || totalSavingsPotential).toLocaleString()} above the reference on matched items.`
      : "A few items are worth double-checking with the hospital.";

  const statusVariant = analysis.total_violations === 0 && (totalExtra === 0 && totalSavingsPotential === 0)
    ? "ok"
    : rejectionProb > 60 || (totalExtra > 0 || totalSavingsPotential > 0) ? "review" : "ok";

  const steps: { text: string; type: "action" | "info" | "warning" }[] = [];
  if (analysis.total_violations === 0) {
    steps.push({ text: "Bill is within CGHS reference rates. Safe to pay and submit for claim.", type: "info" });
    steps.push({ text: "Keep this report with your documents for insurance.", type: "info" });
  } else {
    if (analysis.high_severity_count > 0)
      steps.push({ text: "Show this report at the billing desk and ask for corrections on the overcharged items.", type: "action" });
    if (analysis.can_file_cghs_complaint)
      steps.push({ text: "You can file a complaint with CGHS. This report is your evidence.", type: "action" });
    if (!isCghs)
      steps.push({ text: "This hospital is not CGHS-empanelled — use the report to negotiate with the hospital or insurer.", type: "warning" });
    steps.push({ text: "When claiming from insurance, attach this report for reference.", type: "info" });
  }

  const riskPieData = useMemo(() => {
    return Object.entries(FRAUD_BREAKDOWN_MAX).map(([name, maxVal]) => {
      return { name, value: fraudBreakdown[name] ?? 0, maxVal };
    }).filter(d => d.value > 0);
  }, [fraudBreakdown]);
  const pieColors = ['#f43f5e', '#f97316', '#eab308', '#06b6d4', '#8b5cf6'];

  const containerVariants = {
    hidden: { opacity: 0 },
    show: { opacity: 1, transition: { staggerChildren: 0.08 } }
  } as const;
  const itemVariants = {
    hidden: { opacity: 0, y: 15 },
    show: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 300, damping: 24 } }
  } as const;

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="show"
      className="w-full max-w-7xl mx-auto space-y-6 lg:space-y-8 px-4 sm:px-6 mb-24"
    >
      {/* ── Dashboard Hero Header ─────────────────────────────────────────── */}
      <motion.div variants={itemVariants} className="relative overflow-hidden rounded-[2rem] p-8 lg:p-10 border border-white/40 bg-gradient-to-br from-stone-100/80 via-white/90 to-teal-50/60 backdrop-blur-2xl shadow-2xl shadow-teal-900/5">
        <div className="absolute top-0 right-0 p-8 opacity-10 pointer-events-none">
          {statusVariant === "ok" ? <ShieldAlert className="w-64 h-64 text-teal-600" /> : <Activity className="w-64 h-64 text-amber-600" />}
        </div>
        <div className="relative z-10 max-w-3xl">
          <p className="inline-flex py-1 px-3 rounded-full bg-white/60 border border-stone-200/50 text-stone-500 text-xs font-semibold tracking-widest uppercase mb-4 shadow-sm backdrop-blur-md">
            AI Analytics Report
          </p>
          <h2 className={cn("text-3xl sm:text-4xl lg:text-5xl font-black text-stone-800 tracking-tight leading-tight mb-4", fontHeading.className)}>
            {billData.hospital_name}
          </h2>
          {billData.hospital_address && (
            <p className="text-stone-500 text-base flex items-center gap-2 mb-6 font-medium">
              <Building2 className="w-5 h-5 opacity-70" />
              {billData.hospital_address}
            </p>
          )}
          <p className={cn("text-lg sm:text-xl text-stone-600 font-medium leading-relaxed mb-6", fontHeading.className)}>
            {outcomeLine}
          </p>
          <div className="flex flex-wrap items-center gap-4">
            <span className={cn(
              "inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold shadow-sm transition-transform hover:scale-105",
              statusVariant === "ok"
                ? "bg-teal-500 text-white shadow-teal-500/20"
                : "bg-rose-500 text-white shadow-rose-500/20"
            )}>
              {statusVariant === "ok" ? <CheckCircle2 className="w-4 h-4" /> : <AlertTriangle className="w-4 h-4" />}
              {statusVariant === "ok" ? "All Clear" : "Action Required"}
            </span>
            {isCghs && (
              <span className="text-xs font-semibold text-teal-800 bg-teal-100/50 border border-teal-200/50 px-3 py-2 rounded-xl flex items-center gap-1.5 backdrop-blur-sm">
                <BadgeCheck className="w-4 h-4" />
                CGHS Empanelled {isNabh ? "· NABH" : ""}
              </span>
            )}
            <span className="text-xs font-semibold text-stone-600 bg-stone-100/80 border border-stone-200/50 px-3 py-2 rounded-xl backdrop-blur-sm">
              Date: {formatDate(billData.bill_date)}
            </span>
          </div>
        </div>
      </motion.div>

      {/* ── Key Metrics Grid ────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 lg:gap-6">
        {[
          { label: "Total Billed", value: `₹${billData.total_amount.toLocaleString()}`, sub: stayDays ? `${stayDays} day stay` : "—", color: "from-stone-50 to-stone-100" },
          { label: isCghs ? "Overcharge" : "Above ref.", value: (totalExtra > 0 || totalSavingsPotential > 0) ? `₹${Math.round(isCghs ? totalExtra : totalSavingsPotential).toLocaleString()}` : "₹0", sub: "Potential savings", color: (totalExtra > 0 || totalSavingsPotential > 0) ? "from-rose-50 to-rose-100/50" : "from-teal-50 to-teal-100/50", highlight: (totalExtra > 0 || totalSavingsPotential > 0) },
          { label: "Claim Risk", value: `${Math.round(rejectionProb)}%`, sub: `${rejectionLabel} scrutiny`, color: rejectionProb > 40 ? "from-amber-50 to-amber-100/50" : "from-stone-50 to-stone-100", highlight: rejectionProb > 40 },
          { label: "Flagged Items", value: analysis.violations.length.toString(), sub: "Needs review", color: analysis.violations.length > 0 ? "from-rose-50 to-amber-50" : "from-stone-50 to-stone-100", highlight: analysis.violations.length > 0 }
        ].map((metric, i) => (
          <motion.div key={i} variants={itemVariants} className={cn("rounded-[1.5rem] p-6 border border-white/60 bg-gradient-to-br shadow-lg shadow-black/5 hover:shadow-xl hover:-translate-y-1 transition-all duration-300", metric.color)}>
            <p className="text-stone-500 text-xs font-bold uppercase tracking-widest mb-2 opacity-80">{metric.label}</p>
            <p className={cn("text-2xl sm:text-3xl font-black mb-1", fontHeading.className, metric.highlight ? "text-stone-900" : "text-stone-800")}>{metric.value}</p>
            <p className="text-stone-500 text-xs font-medium">{metric.sub}</p>
          </motion.div>
        ))}
      </div>

      {/* ── Main Dashboard Layout ───────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 lg:gap-8">

        {/* Left Column (Main Details) */}
        <div className="lg:col-span-8 space-y-6 lg:space-y-8">

          {/* Comparison Chart */}
          {chartData.length > 0 && (
            <motion.div variants={itemVariants} className="rounded-[2rem] border border-stone-200/60 bg-white/80 p-6 sm:p-8 shadow-xl shadow-stone-200/20 backdrop-blur-xl">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
                <h3 className={cn("text-xl font-bold text-stone-800", fontHeading.className)}>
                  Pricing Anomalies: Billed vs Reference
                </h3>
                <div className="flex items-center gap-4 text-xs font-bold uppercase tracking-wider text-stone-500 bg-stone-100/80 px-4 py-2 rounded-full">
                  <span className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-stone-300" /> Billed</span>
                  <span className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-teal-500 shadow-[0_0_8px_rgba(20,184,166,0.6)]" /> Reference</span>
                </div>
              </div>
              <div style={{ height: Math.max(250, chartData.length * 50) + "px" }} className="w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} layout="vertical" margin={{ top: 0, right: 20, left: 0, bottom: 0 }} barGap={6}>
                    <XAxis type="number" hide />
                    <YAxis dataKey="name" type="category" width={140} tick={{ fontSize: 12, fill: "#57534e", fontWeight: 500 }} axisLine={false} tickLine={false} />
                    <Tooltip content={<CustomChartTooltip />} cursor={{ fill: "rgba(0,0,0,0.03)" }} />
                    <Bar dataKey="charged" name="Billed" fill="#d6d3d1" radius={[0, 6, 6, 0]} barSize={14} />
                    <Bar dataKey="cghs" name={isCghs ? "CGHS Rate" : "Reference"} fill="#0d9488" radius={[0, 6, 6, 0]} barSize={14} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </motion.div>
          )}

          {/* Line Items Table */}
          {analysis.price_comparisons.length > 0 && (
            <motion.div variants={itemVariants} className="rounded-[2rem] border border-stone-200/60 bg-white/80 shadow-xl shadow-stone-200/20 backdrop-blur-xl overflow-hidden">
              <div className="p-6 sm:p-8 pb-4">
                <h3 className={cn("text-xl font-bold text-stone-800", fontHeading.className)}>
                  Itemized Audit ({analysis.price_comparisons.length} matched)
                </h3>
              </div>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-stone-50/80 border-y border-stone-100">
                      <th className="text-left py-4 px-6 sm:px-8 text-xs font-bold text-stone-500 uppercase tracking-widest">Service / Item</th>
                      <th className="text-right py-4 px-6 text-xs font-bold text-stone-500 uppercase tracking-widest">Billed</th>
                      <th className="text-right py-4 px-6 text-xs font-bold text-stone-500 uppercase tracking-widest">{isCghs ? "CGHS" : "Expected"}</th>
                      <th className="text-right py-4 px-6 sm:px-8 text-xs font-bold text-stone-500 uppercase tracking-widest">Var.</th>
                    </tr>
                  </thead>
                  <tbody>
                    {displayItems.map((item, idx) => {
                      const diff = item.deviation_percentage;
                      const isOver = diff > 0;
                      const isSignificant = Math.abs(diff) > 10;
                      return (
                        <tr key={idx} className="border-b border-stone-50 hover:bg-stone-50/50 transition-colors">
                          <td className="py-4 px-6 sm:px-8">
                            <p className="text-stone-800 font-semibold max-w-[250px] truncate leading-tight" title={item.item}>{item.item}</p>
                            {item.cghs_procedure_matched && item.cghs_procedure_matched !== item.item && (
                              <p className="text-stone-400 text-xs truncate max-w-[250px] mt-1 italic" title={item.cghs_procedure_matched}>
                                Maps to: {item.cghs_procedure_matched}
                              </p>
                            )}
                          </td>
                          <td className="py-4 px-6 text-right font-mono font-medium text-stone-800">₹{item.charged_amount.toLocaleString()}</td>
                          <td className="py-4 px-6 text-right font-mono font-medium text-stone-500">
                            {item.cghs_rate != null ? `₹${item.cghs_rate.toLocaleString()}` : "—"}
                          </td>
                          <td className="py-4 px-6 sm:px-8 text-right">
                            {item.cghs_rate != null ? (
                              <span className={cn(
                                "inline-flex items-center gap-1 text-xs font-bold px-2.5 py-1 rounded-lg",
                                isOver && isSignificant ? "bg-rose-100 text-rose-700" :
                                  isOver ? "bg-amber-50 text-amber-700" : "bg-teal-50 text-teal-700"
                              )}>
                                {isOver ? "+" : ""}{diff.toFixed(0)}%
                              </span>
                            ) : (
                              <span className="text-stone-300 font-mono">—</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {analysis.price_comparisons.length > 5 && (
                <div className="p-4 border-t border-stone-100 bg-white text-center">
                  <button
                    onClick={() => setShowAllItems(!showAllItems)}
                    className="text-sm font-bold text-teal-600 hover:text-teal-700 hover:bg-teal-50 px-4 py-2 rounded-xl inline-flex items-center gap-2 transition-colors mx-auto"
                  >
                    {showAllItems ? <><ChevronUp className="w-4 h-4" /> Collapse List</> : <><ChevronDown className="w-4 h-4" /> View All {analysis.price_comparisons.length}</>}
                  </button>
                </div>
              )}
            </motion.div>
          )}

          {/* Action Steps */}
          <motion.div variants={itemVariants} className="rounded-[2rem] border border-stone-200/60 bg-gradient-to-tr from-stone-50 to-white p-6 sm:p-8 shadow-xl shadow-stone-200/20 backdrop-blur-xl">
            <h3 className={cn("text-xl font-bold text-stone-800 mb-6", fontHeading.className)}>Action Plan</h3>
            <ol className="space-y-4 list-none pl-0">
              {steps.map((s, i) => (
                <li
                  key={i}
                  className={cn(
                    "flex items-start gap-4 text-[15px] font-medium rounded-2xl p-4 transition-all duration-300 hover:scale-[1.01] hover:shadow-md",
                    s.type === "action" ? "bg-white border border-rose-100 text-rose-900 shadow-sm" :
                      s.type === "warning" ? "bg-white border border-amber-100 text-amber-900 shadow-sm" : "bg-white border border-teal-100 text-stone-700 shadow-sm"
                  )}
                >
                  <span className={cn(
                    "w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shrink-0 text-white shadow-inner",
                    s.type === "action" ? "bg-rose-500" : s.type === "warning" ? "bg-amber-500" : "bg-teal-500"
                  )}>
                    {i + 1}
                  </span>
                  <div className="pt-1 leading-snug">{s.text}</div>
                </li>
              ))}
            </ol>
          </motion.div>
        </div>

        {/* Right Column (Sidebar) */}
        <div className="lg:col-span-4 space-y-6 lg:space-y-8">

          {/* Donut Chart - Fraud Breakdown */}
          {riskPieData.length > 0 && (
            <motion.div variants={itemVariants} className="rounded-[2rem] border border-stone-200/60 bg-white/80 p-6 sm:p-8 shadow-xl shadow-stone-200/20 backdrop-blur-xl">
              <div className="flex items-center justify-between mb-2">
                <h3 className={cn("text-xl font-bold text-stone-800", fontHeading.className)}>Risk Analysis</h3>
                <PieChartIcon className="w-5 h-5 text-stone-400" />
              </div>
              <p className="text-stone-500 text-sm font-medium mb-6">Distribution of flagged anomalies</p>

              <div className="h-56 relative flex justify-center items-center group">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={riskPieData}
                      cx="50%"
                      cy="50%"
                      innerRadius={65}
                      outerRadius={85}
                      paddingAngle={4}
                      dataKey="value"
                      stroke="none"
                    >
                      {riskPieData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={pieColors[index % pieColors.length]} className="hover:opacity-80 transition-opacity" />
                      ))}
                    </Pie>
                    {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                    <Tooltip
                      formatter={(value: any, name: any) => [`Score: ${value}`, name]}
                      contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1)', fontWeight: 600, fontFamily: 'sans-serif' }}
                    />
                  </PieChart>
                </ResponsiveContainer>
                {/* Center text for donut */}
                <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none transition-transform group-hover:scale-110">
                  <span className={cn("text-3xl font-black text-stone-800", fontHeading.className)}>{analysis.fraud_risk_score}</span>
                  <span className="text-xs font-bold text-stone-400 uppercase tracking-widest">Total Risk</span>
                </div>
              </div>

              <div className="mt-6 space-y-4">
                {riskPieData.map((d, i) => {
                  const descMap: Record<string, string> = {
                    "Document inconsistencies": "Mathematical mismatches between line items, total amount, or missing details.",
                    "CGHS Violations": "Direct overcharges above statutory reference rates.",
                    "BIS Non-compliance": "Failure to follow standard hospital billing transparency guidelines.",
                    "Temporal Anomalies": "Suspicious hospital stay lengths or chronologically impossible dates.",
                    "Consumable Padding": "Heavy markup on generic items like gloves, syringes, or cotton.",
                  };
                  return (
                    <div key={i} className="flex flex-col gap-1 border-b border-stone-100/50 pb-3 last:border-0 last:pb-0">
                      <div className="flex items-center justify-between text-sm">
                        <span className="flex items-center gap-2 font-bold text-stone-700">
                          <span className="w-2.5 h-2.5 rounded-full" style={{ background: pieColors[i % pieColors.length] }} />
                          {d.name}
                        </span>
                        <span className="font-mono font-bold text-stone-500 bg-stone-100 px-2 py-0.5 rounded-md">{d.value}/{d.maxVal}</span>
                      </div>
                      <p className="text-xs text-stone-500 font-medium pl-4.5 ml-4 leading-snug">
                        {descMap[d.name] || "Various discrepancies detected by the validator engine."}
                      </p>
                    </div>
                  );
                })}
              </div>
            </motion.div>
          )}

          {/* Insurance Risk Details */}
          <motion.div variants={itemVariants} className="rounded-[2rem] border border-stone-200/60 bg-white/80 p-6 sm:p-8 shadow-xl shadow-stone-200/20 backdrop-blur-xl">
            <h3 className={cn("text-xl font-bold text-stone-800 mb-6", fontHeading.className)}>Insurance Health</h3>

            <div className="mb-6 bg-stone-50 rounded-2xl p-4 border border-stone-100">
              <div className="flex items-center justify-between mb-3">
                <p className="text-stone-600 font-bold text-sm uppercase tracking-wider">Rejection Risk</p>
                <span className={cn(
                  "text-xs font-bold px-3 py-1 rounded-full",
                  rejectionProb > 70 ? "bg-red-100 text-red-800" :
                    rejectionProb >= 40 ? "bg-amber-100 text-amber-800" : "bg-teal-100 text-teal-800"
                )}>
                  {rejectionLabel}
                </span>
              </div>
              <div className="h-2.5 w-full bg-stone-200 rounded-full overflow-hidden shadow-inner">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.round(rejectionProb)}%` }}
                  transition={{ duration: 1, ease: "easeOut", delay: 0.2 }}
                  className={cn(
                    "h-full rounded-full transition-colors duration-500",
                    rejectionProb > 70 ? "bg-rose-500" : rejectionProb >= 40 ? "bg-amber-500" : "bg-teal-500"
                  )}
                />
              </div>
            </div>

            {rejectionReasons.length > 0 && (
              <div className="mb-6">
                <p className="text-xs font-bold text-stone-500 uppercase tracking-widest mb-3">Risk Factors</p>
                <ul className="space-y-2">
                  {rejectionReasons.slice(0, 3).map((r, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-stone-700 font-medium">
                      <AlertOctagon className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                      <span className="leading-snug">{r}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {insuranceInfo.tips.length > 0 && (
              <div className="pt-6 border-t border-stone-100/80">
                <p className="text-xs font-bold text-stone-500 uppercase tracking-widest mb-4">Submission Tips</p>
                <ul className="space-y-3">
                  {insuranceInfo.tips.slice(0, 3).map((t, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-stone-600 font-medium bg-teal-50/50 p-2.5 rounded-xl">
                      <ArrowRight className="w-4 h-4 text-teal-500 shrink-0 mt-0.5" />
                      <span className="leading-snug">{t}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </motion.div>

          {/* Quantity Anomalies Card */}
          {(analysis.quantity_anomalies?.length ?? 0) > 0 && (
            <motion.div variants={itemVariants} className="rounded-[2rem] border border-amber-200/60 bg-amber-50/40 p-6 sm:p-8 shadow-xl shadow-amber-100/30 backdrop-blur-xl">
              <div className="flex items-center justify-between mb-2">
                <h3 className={cn("text-xl font-bold text-amber-900", fontHeading.className)}>Quantity Alerts</h3>
                <span className="bg-amber-100 text-amber-800 text-xs font-bold px-3 py-1 rounded-full flex items-center gap-1">
                  <Package2 className="w-3.5 h-3.5" />
                  {analysis.quantity_anomalies!.length} flagged
                </span>
              </div>
              <p className="text-amber-700/80 text-sm font-medium mb-5">
                Items billed in quantities unusual for the hospital stay duration.
              </p>
              <div className="space-y-3">
                {analysis.quantity_anomalies!.map((anomaly, i) => (
                  <div
                    key={i}
                    className={cn(
                      "rounded-2xl p-4 border text-sm",
                      anomaly.severity === "high"
                        ? "bg-red-50 border-red-200/60"
                        : anomaly.severity === "medium"
                          ? "bg-amber-50 border-amber-200/60"
                          : "bg-stone-50 border-stone-200/40"
                    )}
                  >
                    <div className="flex items-start gap-3">
                      <div className={cn(
                        "mt-0.5 shrink-0 w-6 h-6 rounded-full flex items-center justify-center",
                        anomaly.severity === "high" ? "bg-red-500" : anomaly.severity === "medium" ? "bg-amber-500" : "bg-stone-400"
                      )}>
                        <AlertTriangle className="w-3.5 h-3.5 text-white" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center justify-between gap-2 flex-wrap mb-1">
                          <p className="font-bold text-stone-800 text-[13px] truncate max-w-[160px]" title={anomaly.item}>
                            {anomaly.item}
                          </p>
                          <div className="flex items-center gap-1.5 shrink-0">
                            <span className="text-[11px] font-bold text-stone-500">Billed:</span>
                            <span className={cn(
                              "text-[11px] font-black px-1.5 py-0.5 rounded-md",
                              anomaly.severity === "high" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"
                            )}>
                              ×{anomaly.quantity_billed}
                            </span>
                            {anomaly.expected_max != null && (
                              <>
                                <span className="text-stone-300 text-xs">vs</span>
                                <span className="text-[11px] font-bold text-teal-700 bg-teal-50 px-1.5 py-0.5 rounded-md">max ×{anomaly.expected_max}</span>
                              </>
                            )}
                          </div>
                        </div>
                        <p className="text-xs text-stone-600 font-medium leading-snug">
                          {anomaly.reason}
                        </p>
                        {anomaly.stay_days != null && (
                          <p className="text-[10px] text-stone-400 font-semibold mt-1 uppercase tracking-wide">
                            Stay: {anomaly.stay_days} day{anomaly.stay_days !== 1 ? "s" : ""}
                          </p>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </motion.div>
          )}

          {/* Context Card & Timeline */}
          <motion.div variants={itemVariants} className="space-y-4">
            <div className={cn(
              "rounded-2xl border p-5 text-sm font-medium shadow-sm backdrop-blur-sm",
              isCghs ? "bg-teal-50 border-teal-200/60 text-teal-900" : "bg-stone-50 border-stone-200/60 text-stone-700"
            )}>
              <div className="flex gap-3 items-start">
                <Info className={cn("w-5 h-5 shrink-0 mt-0.5", isCghs ? "text-teal-600" : "text-stone-400")} />
                <p className="leading-relaxed">
                  {isCghs
                    ? "This hospital is bound by CGHS rates. The identified overcharges should be corrected by the hospital before you pay."
                    : "This hospital is not CGHS empanelled. The rate comparisons are benchmarks to help you negotiate."}
                </p>
              </div>
            </div>

            <div className="rounded-2xl border border-stone-200/60 bg-white/60 p-5 shadow-sm">
              <h3 className={cn("text-lg font-bold text-stone-800 mb-4", fontHeading.className)}>Timeline Analysis</h3>

              <div className="grid grid-cols-2 gap-4 mb-5 text-sm">
                <div className="bg-stone-50/50 p-3 rounded-xl border border-stone-100">
                  <p className="text-stone-500 font-bold uppercase tracking-wider text-[10px] mb-1">Admission</p>
                  <p className="font-semibold text-stone-800">{billData.admission_date ? formatDate(billData.admission_date) : "Not found"}</p>
                </div>
                <div className="bg-stone-50/50 p-3 rounded-xl border border-stone-100">
                  <p className="text-stone-500 font-bold uppercase tracking-wider text-[10px] mb-1">Discharge</p>
                  <p className="font-semibold text-stone-800">{billData.discharge_date ? formatDate(billData.discharge_date) : "Not found"}</p>
                </div>
              </div>

              <div className="flex items-center justify-between mb-3 text-sm pt-2 border-t border-stone-100/80">
                <span className="text-stone-500 font-bold uppercase tracking-wider text-xs">Plausibility Score</span>
                <span className="font-bold text-stone-800 bg-white px-2 py-0.5 rounded shadow-sm border border-stone-100">{analysis.timeline_plausibility_score ?? 10}/10</span>
              </div>
              {(analysis.timeline_conflicts?.length ?? 0) > 0 && (
                <div className="pt-3 border-t border-stone-100 space-y-2">
                  {analysis.timeline_conflicts!.map((c, i) => (
                    <p key={i} className="text-xs text-amber-700 font-medium flex items-start flex-wrap gap-1.5 leading-snug">
                      <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" /> {c}
                    </p>
                  ))}
                </div>
              )}
            </div>
          </motion.div>

        </div>
      </div>
      <Chatbot billData={billData} analysis={analysis} />
    </motion.div>
  );
}

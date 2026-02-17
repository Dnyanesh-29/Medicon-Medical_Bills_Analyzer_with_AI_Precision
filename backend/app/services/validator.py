import json
import math
import re
import os
import traceback
import logging
from typing import List, Optional, Tuple, Dict
import numpy as np
from fuzzywuzzy import fuzz
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

try:
    from google.genai import Client as GeminiClient
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("⚠️  google-genai not installed — LLM reranking disabled")

from app.core.config import settings
from app.models.schemas import (
    BillData, BillItem, Violation, PriceComparison,
    ViolationType, Severity
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Procedure category taxonomy
# Used to restrict semantic search to the right medical domain before scoring
# ---------------------------------------------------------------------------
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "radiology": [
        "xray", "x-ray", "x ray", "mri", "ct scan", "ct ", "usg", "ultrasound",
        "echo", "doppler", "mammogram", "fluoroscopy", "angiography", "dexa",
        "pet scan", "nuclear", "scintigraphy", "radiograph", "imaging",
        "sonography", "scan", "radiolo",
    ],
    "pathology": [
        "cbc", "blood", "urine", "stool", "culture", "sensitivity", "biopsy",
        "histopathology", "cytology", "serology", "electrolyte", "lft", "kft",
        "rft", "thyroid", "lipid", "glucose", "hba1c", "creatinine", "bilirubin",
        "protein", "albumin", "enzyme", "hormone", "smear", "gram stain",
        "pathol", "lab", "laboratory", "test", "investigation",
    ],
    "icu": [
        "icu", "intensive care", "critical care", "hdu", "high dependency",
        "ventilator", "ventilation", "nicu", "picu", "post op observation",
        "post-op", "recovery room", "step down",
    ],
    "surgery": [
        "surgery", "surgical", "operation", "laparoscop", "appendectomy",
        "cholecystectomy", "hernia", "anesthesia", "anaesthesia", "ot charges",
        "operation theatre", "laparotomy", "appendix", "bypass", "resection",
        "excision", "incision", "repair", "replacement", "transplant",
        "arthroscop", "endoscop",
    ],
    "room": [
        "room", "bed", "ward", "accommodation", "semi private",
        "private", "general ward", "deluxe",
    ],
    "opd": [
        "consultation", "visit", "opd", "doctor fee", "physician fee",
        "professional fee", "specialist", "review",
    ],
    "physiotherapy": [
        "physiotherapy", "physio", "rehabilitation", "rehab", "exercise therapy",
    ],
    "pharmacy": [
        "tablet", "capsule", "injection", "inj.", "syrup", "ointment", "cream",
        "drops", "infusion", "iv fluid", "saline", "drug", "medicine",
    ],
    "consumable": [
        "syringe", "glove", "gauze", "bandage", "catheter", "cannula",
        "iv set", "tape", "cotton", "pad", "disposable", "consumable",
        "mask", "cap", "gown",
    ],
}

# Items that are billed per day — normalise total → per-day before comparing
PER_DAY_KEYWORDS = [
    "per day", "bed", "room", "ward", "icu", "hdu", "nursing",
    "accommodation", "intensive care", "critical care",
]

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _classify_item_category(description: str) -> Optional[str]:
    """Return the best-fit CATEGORY_KEYWORDS category, or None if ambiguous."""
    desc_lower = description.lower()
    scores = {cat: 0 for cat in CATEGORY_KEYWORDS}
    for cat, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in desc_lower:
                scores[cat] += 1
    best_cat = max(scores, key=scores.get)
    return best_cat if scores[best_cat] > 0 else None


def _is_per_day_item(description: str) -> bool:
    """Return True if the item is likely a per-day recurring charge."""
    desc_lower = description.lower()
    return any(kw in desc_lower for kw in PER_DAY_KEYWORDS)


def _safe_float(value) -> Optional[float]:
    """Return float or None — treats NaN / Inf as None."""
    if value is None:
        return None
    try:
        f = float(value)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class SemanticRateValidator:
    """
    Intelligent CGHS rate matching using a four-tier pipeline:

      Tier 1 — Skip generic aggregates (pharmacy total, misc, etc.)
      Tier 2 — Manual overrides  (exact / longest-alias match, correct rates)
      Tier 3 — Category-filtered semantic search  (cosine similarity in domain)
               └─ LLM reranking when semantic confidence is moderate (60–88%)
                  Batched into a SINGLE Gemini API call per bill to cut latency
      Tier 4 — Fuzzy fallback  (token_sort_ratio, threshold >= 70)

    All LLM decisions are logged for auditability / research reproducibility.
    """

    # Cosine similarity thresholds (0.0 – 1.0)
    SEMANTIC_HIGH_CONFIDENCE = 0.88   # Trust semantic match directly
    LLM_RERANK_MIN           = 0.60   # Below this — don't ask LLM
    # Minimum confidence % to flag a legal VIOLATION (CGHS hospital)
    VIOLATION_MIN_CONFIDENCE = 75.0
    # Minimum confidence % for informational comparison (non-CGHS)
    INFO_MIN_CONFIDENCE      = 85.0
    # Minimum deviation % to flag for non-CGHS
    # (private hospitals legitimately charge >CGHS; only flag extreme outliers)
    NON_CGHS_MIN_DEVIATION   = 100.0

    def __init__(self, rates_json_path: str):
        # ── Load & clean CGHS rates ───────────────────────────────────────
        with open(rates_json_path, "r", encoding="utf-8") as f:
            raw_rates = json.load(f)

        self.rates_db: List[dict] = []
        current_json_category = "General"

        for rate in raw_rates:
            nabh_val     = rate.get("nabh_rate")
            non_nabh_val = rate.get("non_nabh_rate")
            nabh_none    = nabh_val is None or (isinstance(nabh_val, float) and math.isnan(nabh_val))
            non_nabh_none = non_nabh_val is None or (isinstance(non_nabh_val, float) and math.isnan(non_nabh_val))

            # Rows with both rates missing are section headers
            if nabh_none and non_nabh_none and rate.get("procedure"):
                current_json_category = rate["procedure"].strip()
                continue

            cleaned = {
                k: (None if (isinstance(v, float) and math.isnan(v)) else v)
                for k, v in rate.items()
            }
            cleaned["json_category"] = current_json_category
            self.rates_db.append(cleaned)

        print(f"   ✓ Loaded {len(self.rates_db)} CGHS rate entries")

        # ── Manual overrides ─────────────────────────────────────────────
        # Rules:
        #  • aliases are complete, normalised billing descriptions
        #  • rates are verified against CGHS 2024-25 rate list
        #  • USG split by body region: KUB (₹680) != Abdomen & Pelvis (₹1,350)
        #  • ICU split by care level: Full ICU (₹4,590) != HDU/post-op (₹2,800)
        self._raw_overrides: List[dict] = [
            # ── OPD / Consultation ────────────────────────────────────────
            {
                "aliases": [
                    "consultation", "opd", "doctor visit",
                    "professional fee", "doctor fee", "specialist consultation",
                    "physician fee",
                ],
                "procedure": "Consultation OPD",
                "non_nabh": 350, "nabh": 350, "confidence": 100,
            },
            # ── Room / Ward ───────────────────────────────────────────────
            {
                "aliases": [
                    "general ward", "ward charges", "bed charges",
                    "room rent", "accommodation charges",
                ],
                "procedure": "General Ward (per day)",
                "non_nabh": 1500, "nabh": 1500, "confidence": 95,
            },
            # ── ICU — Full ────────────────────────────────────────────────
            {
                "aliases": [
                    "icu charges", "icu", "intensive care unit",
                    "intensive care charges", "critical care unit",
                    "post-op icu", "post op icu", 
                    "post-op observation", "post op observation",
                    "recovery room charges",
                ],
                "procedure": "ICU including room rent",
                "non_nabh": 4590, "nabh": 5400, "confidence": 95,
            },
            # ── HDU / Step-down (Strict aliases only) ────────────────────
            # Users report "Post-op" is often billed as full ICU. 
            # Only map explicit "HDU" or "Step down" to the lower rate.
            {
                "aliases": [
                    "hdu", "high dependency unit",
                    "step down unit", "step-down unit",
                ],
                "procedure": "HDU / Step-down",
                "non_nabh": 2800, "nabh": 3200, "confidence": 90,
            },
            # ── ICU — Neonatal ────────────────────────────────────────────
            {
                "aliases": [
                    "nicu", "neonatal icu", "neonatal intensive care",
                    "newborn icu",
                ],
                "procedure": "NICU (per day)",
                "non_nabh": 3500, "nabh": 4000, "confidence": 92,
            },
            # ── USG — Abdomen & Pelvis ────────────────────────────────────
            # FIX: was wrongly mapped to KUB (Rs 680).
            # Correct rate for USG Abdomen & Pelvis is Rs 1,350 non-NABH.
            {
                "aliases": [
                    "usg abdomen & pelvis",
                    "usg abdomen and pelvis",
                    "usg abdomen pelvis",
                    "ultrasound abdomen pelvis",
                    "ultrasound abdomen and pelvis",
                    "sonography abdomen pelvis",
                    "usg abdomen & pelvis with doppler",
                ],
                "procedure": "USG Abdomen & Pelvis",
                "non_nabh": 1350, "nabh": 1600, "confidence": 98,
            },
            # ── USG — Whole Abdomen ───────────────────────────────────────
            {
                "aliases": [
                    "usg abdomen", "ultrasound abdomen",
                    "sonography abdomen", "usg whole abdomen",
                    "ultrasound whole abdomen",
                ],
                "procedure": "USG Whole Abdomen",
                "non_nabh": 1200, "nabh": 1400, "confidence": 95,
            },
            # ── USG — KUB (Kidney Ureter Bladder — different from abdomen) ─
            {
                "aliases": [
                    "usg kub", "ultrasound kub",
                    "usg kidney ureter bladder",
                    "usg whole abdomen kub",
                    "usg abdomen kub",
                    "usg whole abdomen / kub",
                ],
                "procedure": "USG KUB including PVR",
                "non_nabh": 680, "nabh": 800, "confidence": 98,
            },
            # ── USG — Pelvis only ─────────────────────────────────────────
            {
                "aliases": [
                    "usg pelvis", "ultrasound pelvis",
                    "usg lower abdomen", "sonography pelvis",
                ],
                "procedure": "USG Pelvis",
                "non_nabh": 800, "nabh": 950, "confidence": 95,
            },
            # ── CT Scan ───────────────────────────────────────────────────
            {
                "aliases": [
                    "ct scan abdomen contrast",
                    "ct abdomen contrast",
                    "ct whole abdomen with contrast",
                    "cect abdomen",
                    "ct scan abdomen (contrast)",
                    "ct abdomen with contrast",
                ],
                "procedure": "CT Scan Whole Abdomen With Contrast",
                "non_nabh": 4500, "nabh": 5200, "confidence": 98,
            },
            {
                "aliases": [
                    "ct scan abdomen", "ct abdomen plain",
                    "ct abdomen without contrast",
                    "ct scan abdomen plain",
                ],
                "procedure": "CT Scan Whole Abdomen Plain",
                "non_nabh": 3000, "nabh": 3500, "confidence": 95,
            },
            {
                "aliases": [
                    "ct chest", "ct scan chest", "hrct chest",
                    "hrct thorax", "high resolution ct chest",
                ],
                "procedure": "CT Chest / HRCT Thorax",
                "non_nabh": 3500, "nabh": 4000, "confidence": 95,
            },
            # ── X-Ray ─────────────────────────────────────────────────────
            {
                "aliases": [
                    "chest xray", "chest x-ray", "x-ray chest",
                    "xray chest", "chest x ray pa view",
                    "chest xray pa", "x-ray chest pa view",
                    "chest pa view",
                ],
                "procedure": "X-Ray Chest PA View",
                "non_nabh": 150, "nabh": 175, "confidence": 98,
            },
            # ── MRI ───────────────────────────────────────────────────────
            {
                "aliases": ["mri brain", "mri head", "mri brain plain"],
                "procedure": "MRI Brain Plain",
                "non_nabh": 5500, "nabh": 6500, "confidence": 97,
            },
            {
                "aliases": [
                    "mri spine", "mri lumbar spine",
                    "mri cervical spine", "mri thoracic spine",
                    "mri ls spine",
                ],
                "procedure": "MRI Spine (per region)",
                "non_nabh": 5500, "nabh": 6500, "confidence": 95,
            },
            # ── ECG ───────────────────────────────────────────────────────
            {
                "aliases": [
                    "ecg", "electrocardiogram", "ecg 12 lead",
                    "12 lead ecg", "ecg - 12 lead",
                ],
                "procedure": "ECG",
                "non_nabh": 150, "nabh": 175, "confidence": 100,
            },
            # ── Surgery packages ──────────────────────────────────────────
            {
                "aliases": [
                    "laparoscopic appendectomy",
                    "laparoscopic appendectomy package",
                    "lap appendectomy", "laparoscopic appendicectomy",
                    "laparoscopic appendicectomy package",
                ],
                "procedure": "Laparoscopic Appendicectomy",
                "non_nabh": 25500, "nabh": 30000, "confidence": 97,
            },
            {
                "aliases": [
                    "laparoscopic cholecystectomy",
                    "lap cholecystectomy",
                    "laparoscopic cholecystectomy package",
                ],
                "procedure": "Laparoscopic Cholecystectomy",
                "non_nabh": 22000, "nabh": 26000, "confidence": 97,
            },
            # ── Pathology ─────────────────────────────────────────────────
            {
                "aliases": [
                    "cbc", "complete blood count",
                    "complete blood picture", "cbp", "haemogram", "hemogram",
                ],
                "procedure": "Complete Blood Count (CBC)",
                "non_nabh": 120, "nabh": 140, "confidence": 100,
            },
            {
                "aliases": [
                    "lft", "liver function test", "liver function tests",
                    "liver function",
                ],
                "procedure": "Liver Function Tests (LFT)",
                "non_nabh": 350, "nabh": 400, "confidence": 100,
            },
            {
                "aliases": [
                    "kft", "rft", "kidney function test",
                    "renal function test", "kidney function tests",
                    "renal function tests",
                ],
                "procedure": "Renal Function Tests (KFT/RFT)",
                "non_nabh": 300, "nabh": 350, "confidence": 100,
            },
            {
                "aliases": [
                    "blood sugar random", "bsr",
                    "blood glucose random", "random blood sugar",
                    "blood sugar - random",
                ],
                "procedure": "Blood Sugar (Random)",
                "non_nabh": 60, "nabh": 70, "confidence": 100,
            },
            {
                "aliases": [
                    "blood sugar fasting", "bsf",
                    "fasting blood sugar", "fasting glucose",
                    "blood sugar - fasting",
                ],
                "procedure": "Blood Sugar (Fasting)",
                "non_nabh": 60, "nabh": 70, "confidence": 100,
            },
            # ── Misc procedures ───────────────────────────────────────────
            {
                "aliases": ["blood transfusion"],
                "procedure": "Blood Transfusion",
                "non_nabh": 1000, "nabh": 1000, "confidence": 100,
            },
            {
                "aliases": ["nebulization", "nebulisation"],
                "procedure": "Nebulization",
                "non_nabh": 100, "nabh": 100, "confidence": 100,
            },
            {
                "aliases": [
                    "injection charge", "injection administration",
                    "inj administration fee",
                ],
                "procedure": "Injection Administration",
                "non_nabh": 50, "nabh": 50, "confidence": 100,
            },
            {
                "aliases": [
                    "physiotherapy", "physio session",
                    "physiotherapy session", "physiotherapy charges",
                ],
                "procedure": "Physiotherapy Session",
                "non_nabh": 500, "nabh": 600, "confidence": 95,
            },
            {
                "aliases": [
                    "dietician", "dietitian",
                    "diet consultation", "nutrition consultation",
                    "dietician consultation",
                ],
                "procedure": "Dietician Consultation",
                "non_nabh": 300, "nabh": 350, "confidence": 90,
            },
        ]

        # Build alias → override dict (lowercase keys)
        self.manual_overrides: Dict[str, dict] = {}
        for entry in self._raw_overrides:
            for alias in entry["aliases"]:
                self.manual_overrides[alias.lower().strip()] = entry

        # ── Skip terms ───────────────────────────────────────────────────
        # FIX: use proper single-backslash raw strings for word boundaries.
        # r"\bmisc\b"   <- correct  (matches the word "misc")
        # r"\\bmisc\\b" <- WRONG    (matches the literal string \bmisc\b)
        self._skip_terms_raw = [
            "total", "subtotal", "amount due", "balance due", "net amount",
            "drugs", "pharmacy", "medicines", "consumables", "disposables",
            r"\blaboratory\b", "investigations",
            r"\bmisc\b", "miscellaneous",
            "round off", r"\btax\b", r"\bgst\b", "service charge",
            "ward procedures", "treatment fee",
            # Nursing is bundled in room rent under CGHS — skip standalone
            r"\bnursing\b",
        ]
        self._skip_patterns = [
            re.compile(p, re.IGNORECASE) for p in self._skip_terms_raw
        ]

        # ── Semantic model ────────────────────────────────────────────────
        self.semantic_available = False
        self.procedures: List[str] = []
        self.procedure_embeddings = None
        self._category_index: Dict[str, List[int]] = {
            cat: [] for cat in CATEGORY_KEYWORDS
        }

        try:
            print("   🧠 Loading semantic matching model...")
            self.model = SentenceTransformer("all-MiniLM-L6-v2")
            self.procedures = [
                r.get("procedure", "") for r in self.rates_db if r.get("procedure")
            ]
            print(f"   📊 Computing embeddings for {len(self.procedures)} procedures…")
            self.procedure_embeddings = self.model.encode(
                self.procedures, show_progress_bar=False
            )
            for idx, proc in enumerate(self.procedures):
                cat = _classify_item_category(proc)
                if cat:
                    self._category_index[cat].append(idx)

            self.semantic_available = True
            print("   ✓ Semantic matching ready")
        except Exception as exc:
            print(f"   ⚠️  Semantic model loading failed: {exc}")
            print("   ℹ️  Falling back to fuzzy matching only")

        # ── LLM client (Gemini) ───────────────────────────────────────────
        self.llm_client = None
        self.llm_model_name = "gemini-2.0-flash"   # verified model string

        if GEMINI_AVAILABLE and getattr(settings, "GOOGLE_API_KEY", None):
            try:
                creds_path = os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
                try:
                    self.llm_client = GeminiClient(api_key=settings.GOOGLE_API_KEY)
                    print(
                        f"   ✓ Gemini LLM ({self.llm_model_name}) "
                        "initialised for reranking"
                    )
                finally:
                    if creds_path:
                        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
            except Exception as exc:
                print(f"   ⚠️  Gemini LLM init failed: {exc}")

        # Cache populated by _batch_llm_rerank before violation loop
        self._llm_cache: Dict[str, Optional[dict]] = {}

    # ──────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────

    def find_cghs_rate_with_confidence(
        self,
        item_description: str,
        nabh_status: str,
    ) -> Tuple[Optional[float], Optional[str], float]:
        """
        Find best-matching CGHS rate for a single item description.

        Returns:
            (rate, matched_procedure_name, confidence_0_to_100)
        """
        if not item_description:
            return (None, None, 0.0)

        item_lower = item_description.lower().strip()

        # Tier 1 — skip generic aggregates
        if self._should_skip(item_lower):
            return (None, "Aggregate item — skipped", 0.0)

        # Tier 2 — manual overrides (highest precision)
        override = self._lookup_override(item_lower)
        if override:
            rate = (
                override["nabh"] if nabh_status == "NABH/ NABL"
                else override["non_nabh"]
            )
            return (float(rate), override["procedure"], float(override["confidence"]))

        # Tier 3 — semantic + LLM reranking
        if self.semantic_available:
            return self._semantic_match(item_description, nabh_status)

        # Tier 4 — fuzzy fallback
        return self._fuzzy_match(item_description, nabh_status)

    def check_rate_violations(
        self,
        bill_data: BillData,
        nabh_status: str,
        is_cghs: bool,
    ) -> List[Violation]:
        """
        Return Violation objects for all items that exceed CGHS rates.

        For CGHS hospitals violations are legally enforceable.
        For non-CGHS they are informational only, shown when deviation
        exceeds NON_CGHS_MIN_DEVIATION (100%).
        """
        violations: List[Violation] = []

        # Pre-populate LLM cache for ALL moderate-confidence items in ONE
        # Gemini API call — avoids N sequential calls during the loop below.
        if self.semantic_available and self.llm_client:
            self._batch_llm_rerank(bill_data.items, nabh_status)

        for item in bill_data.items:
            cghs_rate, matched_proc, confidence = self.find_cghs_rate_with_confidence(
                item.description, nabh_status
            )
            cghs_rate = _safe_float(cghs_rate)
            if cghs_rate is None:
                continue

            # Use same normalisation as compare_with_cghs_rate for consistency
            charged = self._normalise_charge(item)
            if charged is None or charged <= cghs_rate:
                continue

            try:
                deviation = ((charged - cghs_rate) / cghs_rate) * 100
            except ZeroDivisionError:
                continue

            if _safe_float(deviation) is None:
                continue

            if is_cghs:
                if confidence < self.VIOLATION_MIN_CONFIDENCE:
                    continue
                v_type      = ViolationType.PACKAGE_RATE_VIOLATION
                severity    = Severity.HIGH if deviation > 20 else Severity.MEDIUM
                legal_ref   = "CGHS Package Rate Guidelines"
                enforceable = True
            else:
                if confidence < self.INFO_MIN_CONFIDENCE:
                    continue
                if deviation < self.NON_CGHS_MIN_DEVIATION:
                    continue
                v_type      = ViolationType.INFORMATIONAL
                severity    = Severity.INFO
                legal_ref   = "Informational — hospital not CGHS-empanelled"
                enforceable = False

            violations.append(
                Violation(
                    type=v_type,
                    severity=severity,
                    description=(
                        f"Exceeds CGHS rate by {deviation:.1f}% "
                        f"(matched: '{matched_proc}', "
                        f"confidence: {confidence:.0f}%)"
                    ),
                    item=item.description,
                    charged_amount=charged,
                    expected_amount=cghs_rate,
                    deviation_percentage=deviation,
                    legal_reference=legal_ref,
                    is_enforceable=enforceable,
                )
            )

        return violations

    def compare_with_cghs_rate(
        self,
        item: BillItem,
        nabh_status: str,
    ) -> Optional[PriceComparison]:
        """Return a PriceComparison for display in bill table / chart."""
        cghs_rate, matched_proc, confidence = self.find_cghs_rate_with_confidence(
            item.description, nabh_status
        )
        cghs_rate = _safe_float(cghs_rate)
        if cghs_rate is None or confidence < 50:
            return None

        charged = self._normalise_charge(item)
        if charged is None:
            return None

        try:
            deviation = ((charged - cghs_rate) / cghs_rate) * 100
        except ZeroDivisionError:
            return None

        if _safe_float(deviation) is None:
            return None

        display_proc = matched_proc
        if _is_per_day_item(item.description) and item.quantity and item.quantity > 1:
            display_proc = f"{matched_proc} (per day)"

        return PriceComparison(
            item=item.description,
            charged_amount=charged,
            cghs_rate=cghs_rate,
            cghs_procedure_matched=display_proc,
            match_confidence=confidence,
            applicable_rate_type=nabh_status,
            deviation_percentage=deviation,
            is_abnormal=abs(deviation) > 50,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Private — matching pipeline
    # ──────────────────────────────────────────────────────────────────────

    def _should_skip(self, item_lower: str) -> bool:
        """
        Return True if item is a generic aggregate that should not be matched.
        Uses word-boundary regex — prevents 'Diagnostic Imaging' being skipped
        because it contains 'diagnostic'.
        """
        for pattern in self._skip_patterns:
            if pattern.search(item_lower):
                return True
        return False

    def _lookup_override(self, item_lower: str) -> Optional[dict]:
        """
        Manual override lookup.
          (a) Exact alias match
          (b) Longest alias that appears as a complete word-bounded phrase
              — prevents 'usg abdomen' from eating 'usg abdomen & pelvis'
        """
        if item_lower in self.manual_overrides:
            return self.manual_overrides[item_lower]

        best_alias: Optional[str] = None
        for alias in self.manual_overrides:
            pattern = r"(?<![a-z])" + re.escape(alias) + r"(?![a-z])"
            if re.search(pattern, item_lower):
                if best_alias is None or len(alias) > len(best_alias):
                    best_alias = alias

        return self.manual_overrides[best_alias] if best_alias else None

    def _semantic_match(
        self,
        item_description: str,
        nabh_status: str,
    ) -> Tuple[Optional[float], Optional[str], float]:
        """
        Category-filtered semantic match with LLM reranking for ambiguous cases.
        """
        try:
            item_embedding = self.model.encode(
                [item_description], show_progress_bar=False
            )
            candidates, best_score = self._get_top_k_candidates(
                item_embedding, item_description, k=5
            )

            if not candidates:
                return (None, None, 0.0)

            best = candidates[0]

            # High confidence — trust semantic directly
            if best_score >= self.SEMANTIC_HIGH_CONFIDENCE:
                return self._candidate_to_result(
                    best["procedure"], nabh_status, best_score
                )

            # Moderate confidence — check LLM cache first, then call if needed
            if best_score >= self.LLM_RERANK_MIN and self.llm_client:
                llm_result = self._get_llm_result(item_description, candidates)
                if llm_result:
                    # Blended confidence: 40% semantic weight + 60% LLM weight
                    blended = min(92.0, (best_score * 100 * 0.4) + (95.0 * 0.6))
                    return self._candidate_to_result(
                        llm_result["procedure"], nabh_status, blended / 100
                    )

            # Low confidence — return raw (unlikely to pass violation threshold)
            return self._candidate_to_result(best["procedure"], nabh_status, best_score)

        except Exception as exc:
            logger.warning(
                f"Semantic matching error for '{item_description}': {exc}"
            )
            traceback.print_exc()
            return self._fuzzy_match(item_description, nabh_status)

    def _get_top_k_candidates(
        self,
        item_embedding: np.ndarray,
        item_description: str,
        k: int = 5,
    ) -> Tuple[List[dict], float]:
        """
        Return (candidates, best_score) from category-filtered cosine search.
        Falls back to full procedure list if category index is empty.
        """
        item_category = _classify_item_category(item_description)
        candidate_indices: List[int] = []

        if item_category and self._category_index.get(item_category):
            candidate_indices = self._category_index[item_category]

        if not candidate_indices:
            candidate_indices = list(range(len(self.procedures)))

        candidate_embeddings = self.procedure_embeddings[candidate_indices]
        similarities = cosine_similarity(item_embedding, candidate_embeddings)[0]

        top_k_local = np.argsort(similarities)[-k:][::-1]

        candidates = []
        for local_idx in top_k_local:
            score = float(similarities[int(local_idx)])
            global_idx = candidate_indices[int(local_idx)]
            candidates.append({
                "procedure": self.rates_db[global_idx],
                "score": score,
            })

        best_score = candidates[0]["score"] if candidates else 0.0
        return candidates, best_score

    def _candidate_to_result(
        self,
        procedure_dict: dict,
        nabh_status: str,
        score: float,
    ) -> Tuple[Optional[float], Optional[str], float]:
        """Extract (rate, name, confidence) from a matched procedure dict."""
        rate_key = "nabh_rate" if nabh_status == "NABH/ NABL" else "non_nabh_rate"
        rate = _safe_float(procedure_dict.get(rate_key))
        if rate is None:
            return (None, None, 0.0)
        name = procedure_dict.get("procedure", "Unknown")
        confidence = min(99.0, score * 100)
        return (rate, name, confidence)

    def _get_llm_result(
        self,
        item_description: str,
        candidates: List[dict],
    ) -> Optional[dict]:
        """Return LLM reranking result from cache or single-item call."""
        if item_description in self._llm_cache:
            return self._llm_cache.get(item_description)
        return self._rerank_with_llm_single(item_description, candidates)

    # ──────────────────────────────────────────────────────────────────────
    # Private — LLM reranking
    # ──────────────────────────────────────────────────────────────────────

    def _batch_llm_rerank(
        self,
        items: List[BillItem],
        nabh_status: str,
    ) -> None:
        """
        Batch LLM reranking: ONE Gemini API call for all moderate-confidence
        items in the bill.  Results stored in self._llm_cache.

        This avoids N sequential API calls which would add 3-8 seconds of
        latency for a typical bill with 15-20 items.
        """
        if not self.llm_client or not self.semantic_available:
            return

        self._llm_cache = {}
        moderate_items: List[Tuple[str, List[dict]]] = []

        for item in items:
            item_lower = item.description.lower().strip()
            if self._should_skip(item_lower) or self._lookup_override(item_lower):
                continue  # Skip terms or overrides handle these

            embedding = self.model.encode(
                [item.description], show_progress_bar=False
            )
            candidates, best_score = self._get_top_k_candidates(
                embedding, item.description, k=5
            )

            if self.LLM_RERANK_MIN <= best_score < self.SEMANTIC_HIGH_CONFIDENCE:
                moderate_items.append((item.description, candidates))

        if not moderate_items:
            return

        # Build a single batched prompt
        prompt_parts = [
            "You are a medical billing expert matching Indian hospital bill items "
            "to official CGHS (Central Government Health Scheme) procedure names.\n\n"
            "For each numbered bill item below, pick the best matching candidate "
            "(1-5) from its list, or 0 if none match.\n\n"
            "Strict rules:\n"
            "- Body region must match: 'Abdomen' != 'Chest', 'Abdomen' != 'KUB'\n"
            "- KUB = Kidney Ureter Bladder (NOT a general abdomen scan)\n"
            "- Post-op observation ICU = HDU / step-down level, NOT full ICU\n"
            "- CBC = Complete Blood Count, LFT = Liver Function, "
            "KFT = Kidney Function\n"
            "- USG/Ultrasound/Sonography are the same modality\n\n"
        ]

        for i, (desc, cands) in enumerate(moderate_items):
            prompt_parts.append(f"ITEM {i + 1}: \"{desc}\"\n")
            for j, cand in enumerate(cands):
                proc_name = cand["procedure"].get("procedure", "")
                proc_cat  = cand["procedure"].get("json_category", "")
                prompt_parts.append(f"  {j + 1}. {proc_name}  [{proc_cat}]\n")
            prompt_parts.append("\n")

        prompt_parts.append(
            f"Return ONLY a JSON array of {len(moderate_items)} integers, "
            "e.g. [2, 0, 3].  No extra text."
        )
        prompt = "".join(prompt_parts)

        try:
            response = self.llm_client.models.generate_content(
                model=self.llm_model_name,
                contents=prompt,
            )
            ans_text = response.text.strip()
            logger.info(f"LLM batch rerank response: {ans_text}")

            # FIX: correct single-backslash regex to find JSON array
            json_match = re.search(r"\[[\d,\s]+\]", ans_text)
            if not json_match:
                logger.warning(
                    f"LLM did not return a valid JSON array. "
                    f"Response: {ans_text[:200]}"
                )
                return

            indices = json.loads(json_match.group())

            for i, (desc, cands) in enumerate(moderate_items):
                if i >= len(indices):
                    break
                chosen = indices[i]
                if isinstance(chosen, int) and 1 <= chosen <= len(cands):
                    result = cands[chosen - 1]
                    self._llm_cache[desc] = result
                    logger.info(
                        f"LLM reranked: '{desc}' → "
                        f"'{result['procedure'].get('procedure')}' "
                        f"(candidate {chosen})"
                    )
                else:
                    self._llm_cache[desc] = None
                    logger.info(
                        f"LLM rejected all candidates for: '{desc}'"
                    )

        except Exception as exc:
            logger.warning(f"Batch LLM reranking failed: {exc}")
            traceback.print_exc()

    def _rerank_with_llm_single(
        self,
        item_description: str,
        candidates: List[dict],
    ) -> Optional[dict]:
        """
        Single-item LLM reranking (fallback when batch cache not available).
        """
        if not self.llm_client:
            return None

        try:
            candidate_text = ""
            for i, cand in enumerate(candidates):
                proc = cand["procedure"].get("procedure", "")
                cat  = cand["procedure"].get("json_category", "")
                candidate_text += f"{i + 1}. {proc}  [{cat}]\n"

            prompt = (
                f'You are a medical billing expert.\n\n'
                f'Bill item: "{item_description}"\n\n'
                f'Candidates:\n{candidate_text}\n'
                f'Rules:\n'
                f'- Body region must match exactly (Abdomen != KUB != Chest)\n'
                f'- Post-op observation ICU = HDU level, NOT full ICU\n\n'
                f'Return ONLY a single integer (0-{len(candidates)}). '
                f'0 = no match.'
            )

            response = self.llm_client.models.generate_content(
                model=self.llm_model_name,
                contents=prompt,
            )
            ans_text = response.text.strip()

            # FIX: correct single-backslash word-boundary regex
            match = re.search(r"\b([0-5])\b", ans_text)
            if match:
                idx = int(match.group(1))
                if 1 <= idx <= len(candidates):
                    chosen = candidates[idx - 1]
                    logger.info(
                        f"LLM reranked (single): '{item_description}' → "
                        f"'{chosen['procedure'].get('procedure')}'"
                    )
                    self._llm_cache[item_description] = chosen
                    return chosen
                else:
                    logger.info(
                        f"LLM rejected all for: '{item_description}'"
                    )
                    self._llm_cache[item_description] = None
                    return None

        except Exception as exc:
            logger.warning(
                f"Single LLM rerank failed for '{item_description}': {exc}"
            )

        return None

    # ──────────────────────────────────────────────────────────────────────
    # Private — fuzzy fallback
    # ──────────────────────────────────────────────────────────────────────

    def _fuzzy_match(
        self,
        item_description: str,
        nabh_status: str,
    ) -> Tuple[Optional[float], Optional[str], float]:
        """Fuzzy token_sort_ratio fallback — minimum score 70."""
        item_lower = item_description.lower().strip()
        best_match: Optional[dict] = None
        best_score = 0

        for rate_entry in self.rates_db:
            proc = rate_entry.get("procedure", "")
            if not proc:
                continue
            proc_lower = proc.lower()

            if item_lower == proc_lower:
                best_match = rate_entry
                best_score = 100
                break

            if item_lower in proc_lower:
                score = 90
            elif proc_lower in item_lower:
                score = 85
            else:
                score = fuzz.token_sort_ratio(item_lower, proc_lower)

            if score > best_score and score >= 70:
                best_score = score
                best_match = rate_entry

        if best_match and best_score >= 70:
            rate_key = (
                "nabh_rate" if nabh_status == "NABH/ NABL"
                else "non_nabh_rate"
            )
            rate = _safe_float(best_match.get(rate_key))
            if rate is None:
                return (None, None, 0.0)
            return (
                rate,
                best_match.get("procedure", "Unknown"),
                float(best_score),
            )

        return (None, None, 0.0)

    # ──────────────────────────────────────────────────────────────────────
    # Private — charge normalisation
    # ──────────────────────────────────────────────────────────────────────

    def _normalise_charge(self, item: BillItem) -> Optional[float]:
        """
        Return the charge to compare against the CGHS per-occurrence rate.

        For per-day items (room, ICU, nursing…) with quantity > 1,
        divides total_price by quantity to get the per-day rate:

          3-day ICU: total ₹25,500 → per-day ₹8,500 vs CGHS ₹4,590  (+85%)
          Without this it would show +455% which is meaningless.

        Used in BOTH check_rate_violations AND compare_with_cghs_rate to
        guarantee consistent numbers across all output fields.
        """
        total = _safe_float(item.total_price)
        if total is None:
            return None

        qty = _safe_float(item.quantity) if item.quantity else None
        if qty and qty > 1 and _is_per_day_item(item.description):
            return _safe_float(total / qty)

        return total

import json
import math
from typing import List, Optional, Tuple
import numpy as np
from fuzzywuzzy import fuzz
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

from app.models.schemas import (
    BillData, BillItem, Violation, PriceComparison, 
    ViolationType, Severity
)

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
            
            # Application of Room Rent logic
            'room rent': {'procedure': 'General Ward (per day)', 'non_nabh': 1500, 'nabh': 1500, 'confidence': 95},
            'general ward': {'procedure': 'General Ward (per day)', 'non_nabh': 1500, 'nabh': 1500, 'confidence': 95},
            'ward': {'procedure': 'General Ward (Reference)', 'non_nabh': 1500, 'nabh': 1500, 'confidence': 90}, 
            'bed charges': {'procedure': 'General Ward (per day)', 'non_nabh': 1500, 'nabh': 1500, 'confidence': 95},
            
            # ICU
            'icu': {'procedure': 'ICU including room rent', 'non_nabh': 4590, 'nabh': 5400, 'confidence': 95},
            'intensive care': {'procedure': 'ICU including room rent', 'non_nabh': 4590, 'nabh': 5400, 'confidence': 95},

            # Added Overrides
            'blood transfusion': {'procedure': 'Blood Transfusion', 'non_nabh': 1000, 'nabh': 1000, 'confidence': 100},
            'nebulization': {'procedure': 'Nebulization', 'non_nabh': 100, 'nabh': 100, 'confidence': 100},
            'injection charge': {'procedure': 'Injection Administration', 'non_nabh': 50, 'nabh': 50, 'confidence': 100},
        }

        # Terms that are too generic to match to a specific single procedure
        self.skip_terms = [
            'total', 'subtotal', 'amount', 'due', 'balance', 'net',
            'drugs', 'pharmacy', 'medicines', 'consumables', 'disposables',
            'laboratory', 'investigations', 'diagnostics', 'misc', 'miscellaneous',
            'round off', 'tax', 'gst', 'service charge',
            'ward procedures', 'treatment fee'
        ]
        
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

        # 1. Skip Generic Aggregates
        # If the item description implies a broad category (e.g. "Pharmacy", "Laboratory Investigations"),
        # it is an aggregate of many small items. Matching it to a single package (e.g. "Aspirin" or "Blood Test") is wrong.
        for term in self.skip_terms:
            # Check if term is the WHOLE description or a major part
            # e.g. "Pharmacy" -> Skip. "Pharmacy Charges" -> Skip.
            # But "MRI Scan" -> Keep.
            if term in item_lower:
                # Specialized checks to allow specific items through if needed
                # For now, aggressively skip generics to avoid False Positives
                return (None, f"Generic Category ({term.title()}) - Skipped", 0)
        
        # 2. Check manual overrides first (High confidence)
        for key, override in self.manual_overrides.items():
            if key in item_lower:
                rate = override['nabh'] if nabh_status == "NABH/ NABL" else override['non_nabh']
                return (rate, override['procedure'], override['confidence'])
        
        # 3. Use semantic matching if available
        if self.semantic_available:
            return self._semantic_match(item_description, nabh_status)
        else:
            return self._fuzzy_match(item_description, nabh_status)
    
    def _semantic_match(self, item_description: str, nabh_status: str, threshold=0.45):
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
                                description=f"Exceeds CGHS matched rate by {deviation:.1f}% (matched: '{matched_proc}')",
                                item=item.description,
                                charged_amount=item.total_price,
                                expected_amount=cghs_rate,
                                deviation_percentage=deviation,
                                legal_reference="CGHS Package Rate Guidelines",
                                is_enforceable=True
                            ))
                    else:
                        # Non-CGHS hospital - require very high confidence (85%)
                        if deviation > 100 and confidence >= 85:
                            violations.append(Violation(
                                type=ViolationType.INFORMATIONAL,
                                severity=Severity.INFO,
                                description=f"{deviation:.0f}% above CGHS reference (matched: '{matched_proc}')",
                                item=item.description,
                                charged_amount=item.total_price,
                                expected_amount=cghs_rate,
                                deviation_percentage=deviation,
                                legal_reference="Informational - Hospital not CGHS-empanelled",
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

        # Special handling for per-day charges
        actual_charge = item.total_price
        
        # If it's a room/bed charge and has quantity > 1 (days), calculate per-day rate
        if item.quantity and item.quantity > 1:
            if any(keyword in item.description.lower() for keyword in ['bed', 'room', 'ward', 'accommodation']):
                try:
                    actual_charge = item.total_price / item.quantity
                    matched_procedure = f"{matched_procedure} (per day)"
                except:
                    pass
        
        try:
            deviation = ((actual_charge - cghs_rate) / cghs_rate) * 100
            
            if math.isnan(deviation) or math.isinf(deviation):
                return None
            
            is_abnormal = abs(deviation) > 50
        except:
            return None
        
        return PriceComparison(
            item=item.description,
            charged_amount=actual_charge,
            cghs_rate=cghs_rate,
            cghs_procedure_matched=matched_procedure,
            match_confidence=confidence,
            applicable_rate_type=nabh_status,
            deviation_percentage=deviation,
            is_abnormal=is_abnormal
        )

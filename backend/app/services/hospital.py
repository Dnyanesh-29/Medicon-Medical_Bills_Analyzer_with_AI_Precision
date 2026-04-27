
import json
from typing import Optional
from fuzzywuzzy import fuzz
from app.models.schemas import Hospital, HospitalSearchRequest, HospitalSearchResponse

class HospitalDiscoveryService:
    def __init__(self, hospitals_json_path: str):
        with open(hospitals_json_path, 'r', encoding='utf-8') as f:
            raw_data = json.load(f)
        
        # Normalize NABH status
        self.hospitals_db = []
        for h in raw_data:
            status = h.get('nabh_status', '').strip()
            status_upper = status.upper()
            
            # Standardize variations
            if 'NON' in status_upper:
                h['nabh_status'] = 'Non-NABH'
            elif 'NABH' in status_upper:
                h['nabh_status'] = 'NABH/ NABL'
            else:
                h['nabh_status'] = 'Non-NABH'
            
            self.hospitals_db.append(h)
        
        nabh_count = sum(1 for h in self.hospitals_db if h['nabh_status'] == 'NABH/ NABL')
        print(f"   ✓ Loaded {len(self.hospitals_db)} CGHS hospitals")
        print(f"   ℹ️  NABH hospitals: {nabh_count}")
    
    def find_nearby_hospitals(self, search_request: HospitalSearchRequest) -> HospitalSearchResponse:
        """Find hospitals (simplified without geolocation)"""
        
        filtered_hospitals = []
        
        for hospital_data in self.hospitals_db:
            # NABH filter
            if search_request.nabh_only:
                status = hospital_data.get('nabh_status', '')
                if status == 'Non-NABH':
                    continue
            
            # Name search filter
            if search_request.name_query:
                if search_request.name_query.lower() not in hospital_data.get('hospital_name', '').lower():
                    continue
            
            try:
                # Use strict=False or construct manually to avoid issues if schema changed, 
                # but Hospital(**hospital_data) should work if keys match
                hospital = Hospital(**hospital_data)
                filtered_hospitals.append(hospital)
            except Exception as e:
                # print(f"   ⚠️  Skipped hospital due to validation error: {e}")
                pass
        
        nabh_count = sum(1 for h in filtered_hospitals if h.nabh_status == 'NABH/ NABL')
        non_nabh_count = len(filtered_hospitals) - nabh_count
        
        return HospitalSearchResponse(
            hospitals=filtered_hospitals[:100],
            total_count=len(filtered_hospitals),
            nabh_count=nabh_count,
            non_nabh_count=non_nabh_count
        )
    
    def get_hospital_by_name(self, hospital_name: str) -> Optional[Hospital]:
        """Get hospital details by fuzzy name matching"""
        if not hospital_name or hospital_name.strip() == "":
            return None
        
        best_match = None
        best_score = 0
        
        hospital_name_clean = hospital_name.strip().lower()
        
        # --- Manual Override for Sahyadri ---
        # Forces the NABH version (sr_no 21) if the OCR detects Sahyadri Speciality
        if "sahyadri" in hospital_name_clean and "speciality" in hospital_name_clean:
            for hospital_data in self.hospitals_db:
                if "sahyadri hospital limited" in hospital_data.get('hospital_name', '').lower() and hospital_data.get('nabh_status') == 'NABH/ NABL':
                    return Hospital(**hospital_data)
        # ------------------------------------
        
        for hospital_data in self.hospitals_db:
            db_name = hospital_data.get('hospital_name', '').lower()
            
            # Exact match
            if hospital_name_clean == db_name:
                return Hospital(**hospital_data)
            
            # Use a weighted combination of token_set_ratio (handles substrings) 
            # and ratio (penalizes huge length differences) to accurately tie-break.
            ts_score = fuzz.token_set_ratio(hospital_name_clean, db_name)
            r_score = fuzz.ratio(hospital_name_clean, db_name)
            
            score = (ts_score * 0.8) + (r_score * 0.2)
            
            if score > best_score:
                best_score = score
                best_match = hospital_data
        
        # INCREASED threshold from 75 to 85 for stricter matching
        if best_score >= 85:
            return Hospital(**best_match)
        
        return None

import sys
import re
sys.path.append(r'E:\Medicon\backend')
try:
    from app.services.validator import RateValidator
    v = RateValidator(r'E:\Medicon\cghs_rates.json')
    res = v._lookup_override('ultrasound abdomen & pelvis')
    print('Override matched:', res)
    for k in v.manual_overrides:
        if 'abdomen' in k:
            print('Found alias:', k)
except Exception as e:
    import traceback
    traceback.print_exc()

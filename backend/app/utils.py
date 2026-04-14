
import math
from enum import Enum

def clean_float(value):
    """Convert NaN/Inf to None for JSON compatibility"""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
    return value

def clean_dict_for_json(obj):
    """Recursively clean NaN/Inf values and enum objects from dict/list"""
    if isinstance(obj, dict):
        return {k: clean_dict_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_dict_for_json(item) for item in obj]
    elif isinstance(obj, float):
        return clean_float(obj)
    elif isinstance(obj, Enum):
        return obj.value  # convert Severity.HIGH → "high" etc.
    else:
        return obj

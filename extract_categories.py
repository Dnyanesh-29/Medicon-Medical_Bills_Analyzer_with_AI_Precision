
import json

try:
    with open('e:/Medicon/cghs_rates.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"Loaded {len(data)} items.")
    
    categories = []
    for item in data:
        if item.get('non_nabh_rate') is None and item.get('nabh_rate') is None:
            categories.append(item.get('procedure'))
        elif item.get('procedure') and ("PROCEDURE" in item.get('procedure') or "INVESTIGATIONS" in item.get('procedure')):
             # Sometimes they might have rates but look like headers? Unlikely based on previous view.
             pass
             
    with open('e:/Medicon/categories.txt', 'w', encoding='utf-8') as f_out:
        for c in categories:
            f_out.write(f"{c}\n")

    print(f"Found {len(categories)} categories. Saved to categories.txt")

except Exception as e:
    print(f"Error: {e}")

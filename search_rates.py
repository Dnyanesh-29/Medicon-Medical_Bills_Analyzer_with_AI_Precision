
import json

try:
    with open('e:/Medicon/cghs_rates.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"Loaded {len(data)} items.")
    
    with open('e:/Medicon/usg_search_results.txt', 'w', encoding='utf-8') as f_out:
        usg_items = [item for item in data if item.get('procedure') and 'USG' in item.get('procedure')]
        f_out.write(f"Found {len(usg_items)} USG items:\n")
        f_out.write("==================\n")
        for item in usg_items:
            f_out.write(json.dumps(item, indent=2) + "\n")
            
        abdomen_items = [item for item in data if item.get('procedure') and 'Abdomen' in item.get('procedure') and 'Pelvis' in item.get('procedure')]
        f_out.write(f"\nFound {len(abdomen_items)} items with 'Abdomen' and 'Pelvis':\n")
        f_out.write("==================\n")
        for item in abdomen_items:
            f_out.write(json.dumps(item, indent=2) + "\n")

    print("Done. Check usg_search_results.txt")

except Exception as e:
    print(f"Error: {e}")

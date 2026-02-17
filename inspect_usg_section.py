
import json

try:
    with open('e:/Medicon/cghs_rates.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    start_idx = -1
    for i, item in enumerate(data):
        if item.get('procedure') and "USG," in item.get('procedure'):
             start_idx = i
             break
             
    with open('e:/Medicon/usg_inspect_out.txt', 'w', encoding='utf-8') as f_out:
        if start_idx != -1:
            f_out.write(f"Found header at index {start_idx}\n")
            for j in range(start_idx, start_idx + 20):
                if j < len(data):
                    f_out.write(json.dumps(data[j], indent=2) + "\n")
        else:
            f_out.write("Header not found")

except Exception as e:
    with open('e:/Medicon/usg_inspect_out.txt', 'w', encoding='utf-8') as f_out:
        f_out.write(f"Error: {e}")

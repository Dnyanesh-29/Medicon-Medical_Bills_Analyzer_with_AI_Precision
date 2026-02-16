import pandas as pd
import json
import os

# =========================
# CONFIG
# =========================
EXCEL_PATH = r"E:\Medicon\public\mumbai-CGHS.xlsx"
JSON_PATH = "cghs_hospitals_basic.json"

# =========================
# LOAD EXISTING JSON
# =========================
if os.path.exists(JSON_PATH):
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        hospitals = json.load(f)
else:
    hospitals = []

# Get last sr_no safely
last_sr_no = max((h["sr_no"] for h in hospitals), default=0)

# =========================
# READ ALL SHEETS
# =========================
sheets = pd.read_excel(
    EXCEL_PATH,
    sheet_name=None,   # <-- IMPORTANT: reads Sheet1, Sheet2, etc.
    header=None,
    skiprows=1
)

new_records = []

# =========================
# PROCESS EACH SHEET
# =========================
for sheet_name, df in sheets.items():

    # Select required columns ONLY
    # Based on your sheet:
    # 1 -> Hospital Name
    # 2 -> Address
    # 4 -> Contact No
    # 5 -> NABH Status
    df = df.iloc[:, [1, 2, 5, 4]]

    df.columns = [
        "hospital_name",
        "address",
        "nabh_status",
        "contact_no"
    ]

    # Drop empty rows
    df = df.dropna(how="all")
    df = df.dropna(subset=["hospital_name"])

    # Clean text
    for col in df.columns:
        df[col] = (
            df[col]
            .astype(str)
            .str.replace("\n", " ", regex=False)
            .str.strip()
        )

    # Create JSON records
    for _, row in df.iterrows():
        last_sr_no += 1
        new_records.append({
            "sr_no": last_sr_no,
            "hospital_name": row["hospital_name"],
            "address": row["address"],
            "nabh_status": row["nabh_status"],
            "contact_no": row["contact_no"]
        })

# =========================
# APPEND & SAVE
# =========================
all_hospitals = hospitals + new_records

with open(JSON_PATH, "w", encoding="utf-8") as f:
    json.dump(all_hospitals, f, indent=4, ensure_ascii=False)

print("✅ All sheets processed successfully")
print(f"➕ New hospitals added: {len(new_records)}")
print(f"🏥 Total hospitals now: {len(all_hospitals)}")

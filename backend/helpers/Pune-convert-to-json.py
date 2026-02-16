import pandas as pd
import json
import os

# =========================
# CONFIG
# =========================
EXCEL_PATH = r"E:\Medicon\public\pune-CGHS.xlsx"   # <-- update
OUTPUT_JSON = "cghs_hospitals_basic.json"

# =========================
# FILE CHECK
# =========================
if not os.path.exists(EXCEL_PATH):
    raise FileNotFoundError("Excel file not found")

# =========================
# READ EXCEL (HANDLE DIRTY HEADERS)
# =========================
df = pd.read_excel(
    EXCEL_PATH,
    header=None,     # ignore broken headers
    skiprows=1       # skip title row
)

# =========================
# SELECT ONLY REQUIRED COLUMNS
# =========================
# Column positions based on your sheet:
# 0 -> S.No
# 1 -> Hospital Name
# 2 -> Address
# 3 -> NABH/NABL Status
# 4 -> Contact No
df = df.iloc[:, [0, 1, 2, 3, 4]]

# =========================
# ASSIGN CLEAN COLUMN NAMES
# =========================
df.columns = [
    "sr_no",
    "hospital_name",
    "address",
    "nabh_status",
    "contact_no"
]

# =========================
# CLEAN DATA
# =========================
df = df.dropna(how="all")

# Remove rows where hospital name is missing
df = df.dropna(subset=["hospital_name"])

# Clean text fields
for col in ["hospital_name", "address", "nabh_status", "contact_no"]:
    df[col] = (
        df[col]
        .astype(str)
        .str.replace("\n", " ", regex=False)
        .str.strip()
    )

# Convert S.No to integer
df["sr_no"] = pd.to_numeric(df["sr_no"], errors="coerce")

# Remove junk rows (like address continuation rows)
df = df[df["sr_no"].notna()]

# =========================
# CONVERT TO JSON
# =========================
records = df.to_dict(orient="records")

# =========================
# SAVE JSON
# =========================
with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(records, f, indent=4, ensure_ascii=False)

print("✅ Hospital data extracted successfully")
print(f"🏥 Total hospitals: {len(records)}")
print(f"📄 Output file: {OUTPUT_JSON}")

import pandas as pd
import json
import os

EXCEL_PATH = r"E:\Medicon\backend\CGHS-Rates.xlsx"
OUTPUT_JSON = "cghs_pune_rates.json"

# -----------------------------
# Check file exists
# -----------------------------
if not os.path.exists(EXCEL_PATH):
    raise FileNotFoundError("Excel file not found")

# -----------------------------
# Read Excel (skip title row)
# -----------------------------
df = pd.read_excel(
    EXCEL_PATH,
    header=None,        # ignore existing headers
    skiprows=1          # skip the title row
)

# -----------------------------
# Assign correct column names
# -----------------------------
df.columns = [
    "sr_no",
    "procedure",
    "non_nabh_rate",
    "nabh_rate"
]

# -----------------------------
# Remove empty rows
# -----------------------------
df = df.dropna(how="all")

# -----------------------------
# Clean data
# -----------------------------
df["sr_no"] = pd.to_numeric(df["sr_no"], errors="coerce")
df["non_nabh_rate"] = pd.to_numeric(df["non_nabh_rate"], errors="coerce")
df["nabh_rate"] = pd.to_numeric(df["nabh_rate"], errors="coerce")

df = df.dropna(subset=["procedure"])

# -----------------------------
# Convert to JSON
# -----------------------------
records = df.to_dict(orient="records")

# -----------------------------
# Save JSON
# -----------------------------
with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(records, f, indent=4, ensure_ascii=False)

print("✅ Excel converted to JSON successfully")
print(f"📊 Total records: {len(records)}")

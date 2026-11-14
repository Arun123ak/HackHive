"""
Optional helper to inspect locally downloaded Kaggle ZIP files.
This script does not import their contents into the demo database.
The hackathon brief says real customer/financial data must not be used.
Use this only to inspect schema or after obtaining organizer approval.
"""
import sys
import zipfile
from pathlib import Path
import pandas as pd

def inspect_zip(path):
    path = Path(path)
    if not path.exists():
        print(f"Not found: {path}")
        return
    print(f"\n--- {path.name} ---")
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.lower().endswith(".csv"):
                with archive.open(name) as f:
                    try:
                        df = pd.read_csv(f, nrows=5, encoding="latin1")
                        print(f"\n{name}")
                        print("Columns:", list(df.columns))
                        print(df.head(2).to_string(index=False))
                    except Exception as exc:
                        print(f"Could not inspect {name}: {exc}")

if __name__ == "__main__":
    for item in sys.argv[1:]:
        inspect_zip(item)

"""Download the two public inputs into data/raw (git-ignored).

Federal Reserve: Gurkaynak, Sack and Wright nominal yield curve (feds200628.csv).
Kenneth French data library: monthly research factors (for the one-month bill return RF).
"""
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    ROOT / "data" / "raw" / "gsw" / "feds200628.csv":
        "https://www.federalreserve.gov/data/yield-curve-tables/feds200628.csv",
    ROOT / "data" / "raw" / "french" / "F-F_Research_Data_Factors_CSV.zip":
        "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/F-F_Research_Data_Factors_CSV.zip",
}

for path, url in FILES.items():
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        print("have", path.name)
        continue
    request = urllib.request.Request(url, headers={"User-Agent": "research-download"})
    with urllib.request.urlopen(request, timeout=120) as response:
        path.write_bytes(response.read())
    print("downloaded", path.name, path.stat().st_size)

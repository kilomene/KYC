#!/usr/bin/env python3
"""Download the REAL OFAC SDN list and convert it to this project's
screening CSV format (full_name,dob,country,list_source,entry_id).

Source: the US Treasury OFAC SDN CSV (sdn.csv). The SDN file has a
different layout (no header; columns: ent_num, SDN_Name, SDN_Type,
Program(s), Title, Call_Sign, Vessel_Type, Tonnage, Gross_Tonnage,
Vessel_Flag, Vessel_Owner, Remarks). Dates of birth, when present, are
inside Remarks ("DOB 12 Jan 1960; ...") and are parsed out. The SDN CSV
has no country column (addresses live in a separate file), so country is
left empty for SDN entries. Only individuals are imported.

Output: data/lists/ofac_sdn.csv (data/ is gitignored — lists are data,
not code). Usage: python3 scripts/fetch_ofac.py
Exits non-zero if the download fails (offline-safe: nothing is faked).
"""
import csv, io, os, re, sys, urllib.request

URL = "https://www.treasury.gov/ofac/downloads/sdn.csv"
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "data", "lists", "ofac_sdn.csv")
MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}
DOB_RE = re.compile(r"DOB\s+(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})")

def convert(text):
    rows = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 3 or not row[0].strip().isdigit():
            continue
        ent_num, name, typ = row[0].strip(), row[1].strip(), row[2].strip().lower()
        if typ != "individual" or not name or name == "-0-":
            continue
        remarks = row[11] if len(row) > 11 else ""
        dob = ""
        m = DOB_RE.search(remarks or "")
        if m and m.group(2).title() in MONTHS:
            dob = f"{int(m.group(3)):04d}-{MONTHS[m.group(2).title()]:02d}-{int(m.group(1)):02d}"
        # SDN names are "LAST, First Middle" — normalise to "First Last".
        if "," in name:
            last, first = name.split(",", 1)
            name = (first.strip() + " " + last.strip()).strip()
        rows.append({"full_name": name.title(), "dob": dob, "country": "",
                     "list_source": "OFAC_SDN", "entry_id": f"OFAC-{ent_num}"})
    return rows

def main():
    print(f"[ofac] downloading {URL}")
    try:
        req = urllib.request.Request(URL, headers={"User-Agent": "kyc-fetch-ofac"})
        with urllib.request.urlopen(req, timeout=120) as r:
            text = r.read().decode("utf-8", "replace")
    except Exception as e:
        print(f"[ofac] FAILED: {e}"); return 1
    rows = convert(text)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["full_name", "dob", "country", "list_source", "entry_id"])
        w.writeheader(); w.writerows(rows)
    print(f"[ofac] wrote {len(rows)} individual entries to {OUT}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

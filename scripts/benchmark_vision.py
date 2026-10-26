#!/usr/bin/env python3
"""Labelled accuracy benchmark for the Fortified Vision extraction
pipeline (Phase 4 WS1).

Generates synthetic documents for the priority types with KNOWN
ground-truth fields, applies named degradations, runs the REAL
pipeline (vision.read_document_text + fieldtemplates.extract_fields),
and reports per-field exact-match accuracy and character error rate
(CER), per document type and per degradation level.

The corpus is synthetic and drawn to each type's template layout, so
these numbers are an UPPER-BOUND signal about the extraction wiring
(zone/label/format logic), not a real-world accuracy claim — real
documents vary in layout, print and capture conditions in ways a
drawn corpus cannot. That limit is stated in benchmarks/RESULTS.md
and must stay attached to any use of these numbers.

Usage:
    python3 scripts/benchmark_vision.py [--identities 2]
        [--levels clean,blur_light,...] [--types NG:passport,...]
        [--out benchmarks/results.json]
"""
import argparse, io, json, os, sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

from server import checks as C
from server import docregistry as DOCREG
from server import fieldtemplates as FT
from server import vision as VISION

def _font(size, mono=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf" if mono else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf" if mono else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default(size)

# ---------------- corpus ----------------
# Identities are synthetic. Document numbers are generated to each
# type's real format (NIN = 11 digits; Aadhaar carries a real
# Verhoeff check digit; PAN matches the published pattern).
PEOPLE = [
    {"surname": "ERIKSSON", "given": "ANNA MARIA", "dob": "1974-08-12", "expiry": "2032-04-15"},
    {"surname": "OKONKWO", "given": "CHIDI", "dob": "1990-03-05", "expiry": "2031-11-30"},
    {"surname": "MULLER", "given": "JONAS", "dob": "1988-07-22", "expiry": "2033-01-19"},
]

def _number_for(country, kind, seed):
    if kind in ("nin_slip", "nin_card", "national_id") and country == "NG":
        return str(10000000000 + seed * 1234567)[:11]
    if (country, kind) == ("IN", "aadhaar"):
        base = str(20000000000 + seed * 7654321)[:11]
        return base + FT.verhoeff_digit(base)
    if (country, kind) == ("IN", "pan_card"):
        return "ABCDE1234F" if seed == 0 else "PQRSX6789K"
    if (country, kind) == ("GH", "national_id"):
        return "GHA" + str(1000000000 + seed * 12345)[:10]
    if country == "SG":
        digs = str(1000000 + seed * 111111)[:7]
        return "S" + digs + FT.nric_check_letter("S", digs)
    if (country, kind) == ("AE", "emirates_id"):
        return "784" + str(198000000000 + seed * 999983)[:12]
    if (country, kind) == ("PH", "philid"):
        return str(1000000000000000 + seed * 123456789)[:16]
    if (country, kind) == ("ZA", "smart_id"):
        return str(8001015009087 + seed * 111111111111)[:13]
    if kind == "passport":
        return "L898902C3" if seed == 0 else f"B{seed}2345678"[:9]
    return f"D{seed}234567"[:8] if seed else "D1234567"

# (country, kind, title lines, label language pack)
_SPECS = [
    ("NG", "passport", ["PASSPORT", "FEDERAL REPUBLIC OF NIGERIA"], "en"),
    ("NG", "drivers_licence", ["DRIVER LICENCE", "FEDERAL REPUBLIC OF NIGERIA"], "en"),
    ("NG", "voter_card", ["VOTER CARD INEC", "FEDERAL REPUBLIC OF NIGERIA"], "en"),
    ("NG", "nin_card", ["NATIONAL IDENTITY CARD", "FEDERAL REPUBLIC OF NIGERIA"], "en"),
    ("NG", "nin_slip", ["NATIONAL IDENTIFICATION NUMBER"], "nin"),
    ("US", "passport", ["PASSPORT", "UNITED STATES OF AMERICA"], "en"),
    ("US", "passport_card", ["PASSPORT CARD", "UNITED STATES OF AMERICA"], "en"),
    ("US", "drivers_license", ["DRIVER LICENSE", "UNITED STATES OF AMERICA"], "en"),
    ("US", "state_id", ["IDENTIFICATION CARD", "UNITED STATES OF AMERICA"], "en"),
    ("GB", "drivers_licence", ["DRIVING LICENCE", "UNITED KINGDOM"], "en"),
    ("DE", "national_id", ["PERSONALAUSWEIS", "BUNDESREPUBLIK DEUTSCHLAND"], "de"),
    ("IN", "aadhaar", ["AADHAAR", "GOVERNMENT OF INDIA"], "aadhaar"),
]
PRIORITY_TYPES = [(c, k) for c, k, _t, _l in _SPECS]

_LABEL_TEXT = {
    "en": {"surname": "SURNAME", "given": "GIVEN NAMES", "dob": "DATE OF BIRTH", "expiry": "DATE OF EXPIRY", "number": "NUMBER"},
    "de": {"surname": "NAME", "given": "VORNAMEN", "dob": "GEBURTSDATUM", "expiry": "GÜLTIG BIS", "number": "NUMMER"},
    "aadhaar": {"surname": "SURNAME", "given": "GIVEN NAMES", "dob": "DOB", "expiry": None, "number": "AADHAAR NUMBER"},
    "nin": {"surname": "SURNAME", "given": "FIRST NAME", "dob": "DATE OF BIRTH", "expiry": None, "number": "NIN"},
}

def _fmt_date(iso, lang):
    y, m, d = iso.split("-")
    if lang == "de":
        return f"{d}.{m}.{y}"
    return iso  # ISO is unambiguous in every language pack

def _mrz_lines(person, number):
    surname = person["surname"].replace(" ", "<")
    given = person["given"].replace(" ", "<")
    l1 = ("P<UTO" + surname + "<<" + given).ljust(44, "<")[:44]
    yy = lambda iso: iso[2:4] + iso[5:7] + iso[8:10]
    dob6, exp6 = yy(person["dob"]), yy(person["expiry"])
    l2 = (number + C.mrz_check_digit(number) + "UTO" + dob6 + C.mrz_check_digit(dob6) + "F"
          + exp6 + C.mrz_check_digit(exp6) + "<" * 14 + "<" + "0")
    l2 = l2[:43] + C.mrz_check_digit(l2[0:10] + l2[13:20] + l2[21:43])
    return l1, l2

def render_document(country, kind, person, number):
    """Draw one synthetic document. Returns (PIL image, ground_truth)."""
    entry = DOCREG.get_document(country, kind)
    aspect = entry["aspect"]
    W = 1063
    H = int(W / aspect)
    im = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([14, 14, W - 14, H - 14], outline="black", width=3)
    spec = next(s for s in _SPECS if s[0] == country and s[1] == kind)
    titles, lang = spec[2], spec[3]
    labels = _LABEL_TEXT[lang]
    gt = {"surname": person["surname"], "given_names": person["given"],
          "dob": person["dob"], "number": number}
    if entry.get("has_expiry"):
        gt["expiry"] = person["expiry"]
    if kind == "nin_slip":
        d.text((40, 30), titles[0], fill="black", font=_font(34))
        d.rectangle([int(0.72 * W), 90, int(0.95 * W), int(0.52 * H)], outline="black", width=3)
        d.text((40, int(0.14 * H)), f"NIN {number}", fill="black", font=_font(44, mono=True))
        d.text((40, int(0.36 * H)), f"SURNAME {person['surname']}", fill="black", font=_font(36))
        d.text((40, int(0.50 * H)), f"FIRST NAME {person['given']}", fill="black", font=_font(36))
        d.text((40, int(0.64 * H)), f"DATE OF BIRTH {person['dob']}", fill="black", font=_font(36))
        return im, gt
    # portrait placeholder (left) — a box + head ellipse, no real face
    d.rectangle([int(0.04 * W), int(0.20 * H), int(0.28 * W), int(0.82 * H)], outline="black", width=3)
    d.ellipse([int(0.10 * W), int(0.28 * H), int(0.22 * W), int(0.52 * H)], outline="black", width=3)
    # Layout discipline (measured): text must clear the border stroke
    # and keep clean vertical separation, or tesseract's segmentation
    # silently drops whole lines.
    y = 24
    for t in titles:
        d.text((int(0.36 * W), y), t, fill="black", font=_font(26))
        y += 34
    x = int(0.36 * W)
    num_x = int(0.56 * W) if kind == "passport" else x
    d.text((num_x, int(0.15 * H)), f"{labels['number']} {number}", fill="black", font=_font(28))
    d.text((x, int(0.24 * H)), f"{labels['surname']} {person['surname']}", fill="black", font=_font(34))
    d.text((x, int(0.38 * H)), f"{labels['given']} {person['given']}", fill="black", font=_font(34))
    d.text((x, int(0.54 * H)), f"{labels['dob']} {_fmt_date(person['dob'], lang)}", fill="black", font=_font(34))
    if entry.get("has_expiry"):
        d.text((x, int(0.70 * H)), f"{labels['expiry']} {_fmt_date(person['expiry'], lang)}", fill="black", font=_font(34))
    if (country, kind) == ("IN", "aadhaar"):
        grouped = " ".join(number[i:i + 4] for i in range(0, len(number), 4))
        d.text((int(0.30 * W), int(0.80 * H)), grouped, fill="black", font=_font(40))
    if entry.get("mrz"):
        l1, l2 = _mrz_lines(person, number)
        d.text((40, int(0.84 * H)), l1, fill="black", font=_font(24, mono=True))
        d.text((40, int(0.90 * H)), l2, fill="black", font=_font(24, mono=True))
    # background texture so the image is not a flat synthetic card
    for xx in range(50, W - 50, 26):
        d.line([(xx, H - 60), (xx + 12, H - 30)], fill=(180, 180, 180), width=1)
    return im, gt

# ---------------- degradations ----------------

def degrade(im, level):
    if level == "clean":
        return im
    if level == "blur_light":
        return im.filter(ImageFilter.GaussianBlur(radius=1.2))
    if level == "blur_heavy":
        return im.filter(ImageFilter.GaussianBlur(radius=2.5))
    if level == "downscale_50":
        return im.resize((im.width // 2, im.height // 2), Image.LANCZOS)
    if level == "downscale_35":
        return im.resize((int(im.width * 0.35), int(im.height * 0.35)), Image.LANCZOS)
    if level == "dark":
        return ImageEnhance.Brightness(im).enhance(0.65)
    if level == "bright":
        return ImageEnhance.Brightness(im).enhance(1.35)
    if level == "rotate_4":
        return im.rotate(4, expand=False, fillcolor="white", resample=Image.BICUBIC)
    raise ValueError(level)

LEVELS = ["clean", "blur_light", "blur_heavy", "downscale_50", "downscale_35", "dark", "bright", "rotate_4"]

# ---------------- metrics ----------------

def _lev(a, b):
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if not la:
        return lb
    if not lb:
        return la
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        for j in range(1, lb + 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] != b[j - 1]))
        prev = cur
    return prev[lb]

def _norm(field, v):
    if v is None:
        return ""
    if field == "number":
        import re
        return re.sub(r"[^A-Z0-9]", "", str(v).upper())
    if field in ("surname", "given_names"):
        return " ".join(sorted(str(v).upper().split()))
    return str(v).strip()

def run(types, n_identities, levels, workdir):
    os.makedirs(workdir, exist_ok=True)
    results = []  # per-document records
    for (country, kind) in types:
        entry = DOCREG.get_document(country, kind)
        for pi in range(n_identities):
            person = PEOPLE[pi % len(PEOPLE)]
            number = _number_for(country, kind, pi)
            base_im, gt = render_document(country, kind, person, number)
            for level in levels:
                im = degrade(base_im.copy(), level)
                path = os.path.join(workdir, f"{country}_{kind}_{pi}_{level}.png")
                im.save(path)
                text = VISION.read_document_text(path, expect_mrz=bool(entry.get("mrz")))["text"]
                res = FT.extract_fields(path, country, kind, ocr_text=text)
                got = {f: (res["findings"]["fields"].get(f) or {}).get("value") for f in gt}
                rec = {"country": country, "kind": kind, "level": level, "fields": {}}
                for f, want in gt.items():
                    g = _norm(f, got.get(f))
                    w = _norm(f, want)
                    rec["fields"][f] = {"exact": g == w and bool(w),
                                        "cer": round(_lev(g, w) / max(len(w), 1), 4) if w else 1.0}
                results.append(rec)
    return results

def aggregate(results):
    def _agg(recs):
        fields = {}
        all_exact, all_cer, n = [], [], 0
        for r in recs:
            for f, m in r["fields"].items():
                fields.setdefault(f, []).append(m)
                all_exact.append(m["exact"]); all_cer.append(m["cer"]); n += 1
        out = {"documents": len(recs), "field_values": n,
               "exact_match": round(sum(all_exact) / len(all_exact), 4) if all_exact else None,
               "mean_cer": round(sum(all_cer) / len(all_cer), 4) if all_cer else None,
               "per_field": {f: {"exact_match": round(sum(m["exact"] for m in ms) / len(ms), 4),
                                 "mean_cer": round(sum(m["cer"] for m in ms) / len(ms), 4), "n": len(ms)}
                             for f, ms in sorted(fields.items())}}
        return out
    by_type, by_level = {}, {}
    for r in results:
        by_type.setdefault(f"{r['country']}/{r['kind']}", []).append(r)
        by_level.setdefault(r["level"], []).append(r)
    return {"overall": _agg(results),
            "per_type": {k: _agg(v) for k, v in sorted(by_type.items())},
            "per_level": {k: _agg(v) for k, v in sorted(by_level.items())},
            "clean": _agg([r for r in results if r["level"] == "clean"])}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--identities", type=int, default=2)
    ap.add_argument("--levels", default="clean,blur_light,downscale_50,dark,rotate_4")
    ap.add_argument("--types", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--workdir", default="/tmp/kyc-bench")
    args = ap.parse_args()
    types = PRIORITY_TYPES
    if args.types:
        types = [tuple(t.split(":")) for t in args.types.split(",")]
    levels = [l.strip() for l in args.levels.split(",") if l.strip()]
    results = run(types, args.identities, levels, args.workdir)
    agg = aggregate(results)
    agg["corpus"] = {"types": [f"{c}/{k}" for c, k in types],
                      "identities_per_type": args.identities, "levels": levels,
                      "documents": len(results)}
    print(json.dumps(agg, indent=1))
    if args.out:
        with open(args.out, "w") as f:
            json.dump(agg, f, indent=1)

if __name__ == "__main__":
    main()

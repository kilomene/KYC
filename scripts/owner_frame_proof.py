#!/usr/bin/env python3
"""Owner-frame proof for the paper rectification (2026-10-26).

Runs the owner's two production-test screenshots (his REAL NIN slip —
PRIVATE: inputs live outside the repo, outputs only under data/,
which is gitignored) through every rectified layer:

  1. server framing (quad / aspect / warp) on the camera viewport;
  2. the shipped client detector (Node harness, flow.html code) on
     the canvas-equivalent frame;
  3. OCR on the warped rendition, nin_slip classification, and field
     extraction — reported in FIELD TERMS ONLY (statuses, lengths,
     format booleans). Document values are never printed or stored.

Usage: python3 scripts/owner_frame_proof.py
Writes data/owner-frame-proof/proof.json and the derived viewport /
warp artefacts beside it.
"""
import json, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PIL import Image
from server import framing as F, vision as V, templates as T, fieldtemplates as FT

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "owner-frame-proof")
# Phone screenshots 1179x2556; camera viewport measured on the frames.
VIEWPORT = (45, 110, 1135, 2045)
FRAMES = {
    "clear": os.path.expanduser("~/workspace/user/media_library/image/9a/9a75b2dc170b060338eee950bc7f1fe3dfbf6110e4b1481c71e9333d4e516b74.jpg"),
    "dark": os.path.expanduser("~/workspace/user/media_library/image/89/89fdfa26f907ec046d97f3ce6506a21a1daf34d51eca00c5b6d8f277e3f229ca.jpg"),
}
SLIP_GEO = json.dumps({"physical": "paper", "aspectMin": 1.2, "aspectMax": 2.8})
CARD_GEO = json.dumps({"physical": "card", "aspect": 1.41})


def client_state(raw_path, w, h, geo, src_w, src_h):
    out = subprocess.run(["node", os.path.join(ROOT, "tests", "detector_harness.js"),
                          "--grey", raw_path, str(w), str(h), geo, str(src_w), str(src_h)],
                         capture_output=True, text=True, timeout=300)
    return json.loads(out.stdout)["state"]


def field_terms(ext):
    terms = {}
    for name, e in ext["findings"]["fields"].items():
        v = e.get("value")
        if not v:
            terms[name] = {"extracted": False}
        elif name == "number":
            terms[name] = {"extracted": True, "chars": len(str(v)),
                           "all_digits": str(v).isdigit(),
                           "format_valid": e.get("format_valid")}
        else:
            terms[name] = {"extracted": True, "chars": len(str(v)),
                           "words": len(str(v).split()), "source": e.get("source")}
    return terms


def main():
    os.makedirs(OUT, exist_ok=True)
    proof = {}
    for name, src in FRAMES.items():
        im = Image.open(src)
        crop = im.crop(VIEWPORT)
        crop_path = os.path.join(OUT, f"{name}_viewport.png")
        crop.save(crop_path)
        entry = {"viewport": list(VIEWPORT), "crop_size": list(crop.size)}

        fr = F.check_document_framing(path=crop_path)
        entry["server_framing"] = {"status": fr["status"], "reason_codes": fr["reason_codes"],
                                   "quad_found": fr["findings"]["quad_found"],
                                   "aspect": fr["findings"]["aspect"],
                                   "method": fr["findings"]["method"],
                                   "fill_rule": fr["findings"]["fill_rule"],
                                   "warp_applied": fr["findings"]["warp_applied"]}

        # Client detector on the canvas-equivalent frame (analyseFrame
        # draws the stream into a 320x420-capped canvas; source dims
        # carried for the aspect correction, exactly as in flow.html).
        small = crop.convert("L").resize((320, 420))
        raw_path = os.path.join(OUT, f"{name}_grey.raw")
        with open(raw_path, "wb") as fh:
            fh.write(small.tobytes())
        entry["client_detector"] = {
            "paper_path": client_state(raw_path, 320, 420, SLIP_GEO, *crop.size),
            "old_card_path_at_1.41": client_state(raw_path, 320, 420, CARD_GEO, *crop.size),
        }

        if fr["status"] == "pass":
            ocr = V.read_document_text(crop_path, expect_mrz=False)
            entry["ocr"] = {"status": ocr["status"], "chars": ocr["findings"]["chars"],
                            "warp": ocr["findings"].get("warp")}
            cls = T.check_classification(crop_path, "NG", "nin_slip", ocr_text=ocr["text"])
            entry["classification"] = {"status": cls["status"], "score": cls["findings"].get("score"),
                                        "measured_on": cls["findings"].get("measured_on"),
                                        "aspect_element": cls["findings"]["elements"].get("aspect"),
                                        "portrait_found": (cls["findings"]["elements"].get("portrait") or {}).get("found"),
                                        "labels_found": (cls["findings"]["elements"].get("labels") or {}).get("found")}
            ext = FT.extract_fields(crop_path, "NG", "nin_slip", ocr_text=ocr["text"])
            entry["extraction"] = {"status": ext["status"], "fields": field_terms(ext)}
        proof[name] = entry
        print(f"== {name}: framing={entry['server_framing']['status']} "
              f"client={entry['client_detector']['paper_path']} "
              f"classification={entry.get('classification', {}).get('status')} "
              f"extraction={entry.get('extraction', {}).get('status')}")
    with open(os.path.join(OUT, "proof.json"), "w") as fh:
        json.dump(proof, fh, indent=1)
    print("wrote", os.path.join(OUT, "proof.json"))


if __name__ == "__main__":
    main()

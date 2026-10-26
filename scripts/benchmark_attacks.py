#!/usr/bin/env python3
"""Presentation-attack suite (Phase 4 WS2).

Attack families from the plan — printed photo, screen replay, video
replay, mask, deepfake — built from REAL source material (the owner's
own stored captures, used for his own platform's testing, plus LFW
faces) and run against the PRODUCTION defences: active liveness
(server/liveness.py), deepfake/injection analysis
(server/deepfake.py), continuous face tracking (server/facetrack.py),
track/doc face match (server/face.py) and the document-path screen
signals (server/authenticity.py moire + pixel-grid, read on attack
frames — those signals guard the document path in production and are
reported here as signal readings, not as a liveness verdict).

REAL vs SIMULATED, stated per family (and in benchmarks/BIOMETRICS.md):
  replay    REAL artefacts — the owner's genuine liveness videos,
            replayed as-is against FRESH server challenges. The
            defence under test is challenge freshness, which is the
            only layer that can catch a bit-perfect replay.
  print     SIMULATED print (documented synthesis: matte contrast,
            halftone dot screen, paper tint — applied to a genuine
            face photo), presented as a handheld video. Not a physical
            print photographed in the real world.
  screen    SIMULATED screen (documented synthesis: moire grating,
            pixel grid, refresh flicker, gamut shift — applied to
            genuine frames). Not a physical screen photographed.
  mask      SIMULATED rigid-mask proxy (printed face texture on a
            uniform oval, rigid motion, no internal deformation, no
            pulse). A physical 3D mask CANNOT be produced in this
            environment: that family is UNMEASURED for real masks;
            the proxy measures only the rigid-2D case.
  deepfake  SIMULATED (face morph stills + morph-composited video +
            identity crossfade). No DNN face-swap generator is
            installed; a true GAN/diffusion swap corpus is UNMEASURED.

Verdicts per artefact, from the production combination doctrine
(server/engine.biometric_evidence): an attack is REJECTED when any
required leg fails (face_track / liveness / face_match fail, or
deepfake fail) — that is an automatic rejection in production. It is
BLOCKED when it is not rejected but the combination would not
auto-approve it either. Both numbers are reported; the headline
catch rate is REJECTED.

Genuine controls (the owner's two real liveness videos + his real
document/selfie pair) run through the same harness and are reported
as-is, including where a genuine capture is itself rejected.

Usage: python3 scripts/benchmark_attacks.py [--out benchmarks/attacks.json]
"""
import argparse, io, json, os, random, sys, zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

try:
    import cv2
except Exception:
    cv2 = None

from server import authenticity as AUTH
from server import deepfake as DF
from server import engine as ENGINE
from server import face as FACE
from server import facetrack as FT
from server import liveness as LV

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OWNER_DIR = os.path.join(ROOT, "data", "files",
                         "f9774493-369d-4e89-b075-dc7988759faa",
                         "6c9e537a-2a9d-401f-b94e-19bf9b07f17f")
OWNER_SELFIE = os.path.join(OWNER_DIR, "e19d49a4-2fba-4ddd-81ac-dca651a52bc4_selfie.jpg")
OWNER_DOC = os.path.join(OWNER_DIR, "b33691ae-54f1-4466-b144-2a14e075d81e_front.jpg")
OWNER_CLEAN = os.path.join(OWNER_DIR, "6ff7568e-11ba-4312-b5c7-781e602661dc_liveness.webm")
OWNER_HARD = os.path.join(OWNER_DIR, "9480d246-0dfe-4bf9-bbdf-9ca818ea2581_liveness.webm")
OWNER_CHALLENGE = {"movements": ["down", "right"], "version": 1}  # stored session challenge
LFW_DIR = os.path.join(ROOT, "benchmarks", "corpus", "lfw_funneled")
WORK = os.path.join(ROOT, "benchmarks", "corpus", "attacks_work")
FPS = 20

# ---------------------------------------------------------------- media helpers

def write_video(frames, path, fps=FPS):
    if not frames:
        return None
    h, w = frames[0].shape[:2]
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    if not vw.isOpened():
        return None
    for fr in frames:
        vw.write(fr)
    vw.release()
    return path

def read_frames(path, max_frames=400):
    cap = cv2.VideoCapture(path)
    frames = []
    while len(frames) < max_frames:
        ok, fr = cap.read()
        if not ok:
            break
        frames.append(fr)
    cap.release()
    return frames

def mid_face_frame(frames):
    """First frame at/after the middle where YuNet finds a face."""
    if not frames:
        return None
    for fr in frames[len(frames) // 2:] + frames[:len(frames) // 2]:
        if FACE.largest_face(fr) is not None:
            return fr
    return frames[len(frames) // 2]

def save_img(img, name):
    path = os.path.join(WORK, name)
    cv2.imwrite(path, img)
    return path

def lfw_faces(n=3):
    """First n LFW identities with >= 2 images -> (img1, img2) paths."""
    out = []
    if not os.path.isdir(LFW_DIR):
        return out
    for person in sorted(os.listdir(LFW_DIR)):
        pdir = os.path.join(LFW_DIR, person)
        if not os.path.isdir(pdir):
            continue
        imgs = sorted(f for f in os.listdir(pdir) if f.endswith(".jpg"))
        if len(imgs) >= 2:
            out.append((os.path.join(pdir, imgs[0]), os.path.join(pdir, imgs[1])))
        if len(out) >= n:
            break
    return out

def aligned_crop(img_path):
    """SFace-aligned 112x112 crop via the production recognizer."""
    img = cv2.imread(img_path)
    if img is None:
        return None
    row = FACE.largest_face(img)
    if row is None:
        return None
    rec = FACE._recognizer()
    return rec.alignCrop(img, row)

# ---------------------------------------------------------------- attack synthesis (documented methods)

def simulate_print(img):
    """SIMULATED print: matte contrast flatten, halftone dot screen
    (periodic dot gain), paper tint, slight blur. Applied to a genuine
    photo — synthesis of a print's texture, not a photographed print."""
    x = img.astype(np.float64)
    x = 255.0 * (0.12 + 0.76 * (x / 255.0))  # matte: lifted blacks, compressed whites
    h, w = x.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    dot = 0.92 + 0.08 * np.sin(xx * 2.1) * np.sin(yy * 2.1)  # halftone dot gain
    x = x * dot[:, :, None]
    x[:, :, 0] *= 0.96; x[:, :, 2] *= 1.05  # paper tint (BGR: warmer red)
    out = np.clip(x, 0, 255).astype(np.uint8)
    return cv2.GaussianBlur(out, (3, 3), 0.6)

def present_on_paper(face_img, seconds=4, seed=5, handheld=True):
    """Render a (printed) face photo on a paper sheet, handheld drift."""
    rng = random.Random(seed)
    H, W = 480, 640
    paper = np.full((H, W, 3), (196, 190, 178), np.uint8)
    face = cv2.resize(face_img, (300, 360))
    frames = []
    jx = jy = 0.0
    for i in range(int(FPS * seconds)):
        if handheld:
            jx = max(-8, min(8, jx + rng.gauss(0, 1.6)))
            jy = max(-8, min(8, jy + rng.gauss(0, 1.6)))
        canvas = paper.copy()
        x0, y0 = 170 + int(jx), 60 + int(jy)
        canvas[y0:y0 + 360, x0:x0 + 300] = face
        frames.append(canvas)
    return frames

def simulate_screen_frame(img, t=0.0, strength=1.0):
    """SIMULATED screen: moire grating + pixel grid + flicker + gamut."""
    x = img.astype(np.float64)
    h, w = x.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    moire = 1.0 + strength * 0.10 * np.sin((xx * 0.9 + yy * 0.35) * 1.7)
    x = x * moire[:, :, None]
    x[::3, :, :] *= 0.82; x[:, ::3, :] *= 0.82  # pixel grid
    flicker = 1.0 + 0.05 * np.sin(2 * np.pi * 8 * t)
    x = x * flicker
    x[:, :, 0] *= 1.06  # cool screen cast (B channel up in BGR)
    return np.clip(x, 0, 255).astype(np.uint8)

def simulate_mask(face_img, seconds=4, seed=9):
    """SIMULATED rigid-mask proxy: face texture flattened onto a
    uniform oval (the 'mask'), dark eye holes, rigid sinusoidal
    motion, zero internal deformation. NOT a physical mask."""
    H, W = 480, 640
    face = cv2.resize(face_img, (280, 340))
    face = (255 * (0.25 + 0.6 * (face.astype(np.float64) / 255.0))).astype(np.uint8)
    frames = []
    for i in range(int(FPS * seconds)):
        canvas = np.full((H, W, 3), (88, 92, 96), np.uint8)
        cx = 320 + int(28 * np.sin(2 * np.pi * i / (FPS * seconds)))
        cy = 240 + int(10 * np.sin(4 * np.pi * i / (FPS * seconds)))
        mask = np.zeros((H, W), np.uint8)
        cv2.ellipse(mask, (cx, cy), (150, 180), 0, 0, 360, 255, -1)
        base = np.full((H, W, 3), (168, 148, 128), np.uint8)
        x0, y0 = cx - 140, cy - 170
        region = base[y0:y0 + 340, x0:x0 + 280]
        blended = cv2.addWeighted(region, 0.35, face, 0.65, 0)
        base[y0:y0 + 340, x0:x0 + 280] = blended
        # eye holes: dark ellipses that move WITH the mask (rigid)
        for ex in (-52, 52):
            cv2.ellipse(base, (cx + ex, cy - 30), (26, 13), 0, 0, 360, (30, 28, 26), -1)
        canvas[mask > 0] = base[mask > 0]
        frames.append(canvas)
    return frames

def morph_images(path_a, path_b, alpha=0.5):
    """Face morph: aligned crops of two identities, alpha-blended."""
    ca, cb = aligned_crop(path_a), aligned_crop(path_b)
    if ca is None or cb is None:
        return None
    return cv2.addWeighted(ca, 1 - alpha, cb, alpha, 0)

# ---------------------------------------------------------------- defence harness

FRESH_CHALLENGES = [
    {"movements": ["left", "up"], "version": 1},
    {"movements": ["right", "down"], "version": 1},
    {"movements": ["up", "right"], "version": 1},
]

def run_defences(video_path, still_path=None, challenge=None, doc_path=OWNER_DOC):
    """Run the production defence legs on one artefact.
    Returns per-leg verdicts + combination outcome + signal readings."""
    challenge = challenge or FRESH_CHALLENGES[0]
    legs = {}
    if video_path:
        legs["liveness"] = LV.check_liveness(video_path, challenge)
        legs["deepfake"] = DF.check_deepfake(video_path, still_path or OWNER_SELFIE,
                                             {"track_label": "USB Camera"})
        legs["face_track"] = FT.check_face_track(video_path, [still_path] if still_path else [])
    frame_path = still_path
    frames = read_frames(video_path, 60) if video_path else []
    mid = mid_face_frame(frames) if frames else None
    if mid is not None:
        frame_path = save_img(mid, f"frame_{os.path.basename(video_path)}.jpg")
    signals = {}
    if frame_path and os.path.isfile(frame_path):
        try:
            signals["moire"] = AUTH.moire_signal(frame_path)
            signals["pixel_grid"] = AUTH.pixel_grid_signal(frame_path)
        except Exception as e:
            signals["error"] = str(e)[:120]
        if doc_path and os.path.isfile(doc_path):
            legs["face_match"] = FACE.check_face_match(doc_path, frame_path)
    check_results = {k: {"status": v["status"]} for k, v in legs.items()}
    if "face_track" not in check_results:
        check_results["face_track"] = {"status": "absent"}
    for k in ("liveness", "face_match"):
        check_results.setdefault(k, {"status": "absent"})
    check_results.setdefault("capture_quality", {"status": "pass"})
    ev = ENGINE.biometric_evidence(check_results,
                                   {"track_label": "USB Camera", "motion": {"samples": 50, "variance": 0.3}})
    rejected = any(v["status"] == "fail" for v in legs.values())
    return {
        "legs": {k: {"status": v["status"], "reason_codes": v.get("reason_codes", []),
                     "findings": _trim(v.get("findings", {}))} for k, v in legs.items()},
        "combination_all_passing": ev["all_passing"],
        "rejected": rejected,
        "blocked": (not rejected) and not ev["all_passing"],
        "signals": signals,
    }

_KEEP_FINDINGS = ("similarity", "presence_ratio", "identity_min_cosine", "face_ratio",
                  "artifact_score", "centre_range", "movements_made", "pulse")

def _trim(findings):
    out = {}
    for k in _KEEP_FINDINGS:
        if k in findings:
            v = findings[k]
            if k == "pulse" and isinstance(v, dict):
                v = {"present": v.get("present"), "method_used": v.get("method_used"),
                     "methods_present": v.get("methods_present"),
                     "pos": (v.get("pos") or {}).get("present"),
                     "green": (v.get("green") or {}).get("present")}
            out[k] = v
    return out

# ---------------------------------------------------------------- families

def fam_replay():
    """REAL artefacts: the owner's genuine videos replayed as-is.
    Each is judged against FRESH challenges (never its own stored
    one) — challenge freshness is the defence under test."""
    arts = []
    for label, path in (("owner_clean_take", OWNER_CLEAN), ("owner_hard_take", OWNER_HARD)):
        per_challenge = []
        for ch in FRESH_CHALLENGES:
            lv = LV.check_liveness(path, ch)
            per_challenge.append({"challenge": ch["movements"], "liveness": lv["status"],
                                  "reason_codes": lv.get("reason_codes", [])})
        passed = sum(1 for c in per_challenge if c["liveness"] == "pass")
        full = run_defences(path, OWNER_SELFIE, FRESH_CHALLENGES[0])
        arts.append({"artefact": label, "kind": "video_replay_real",
                     "liveness_under_fresh_challenges": per_challenge,
                     "liveness_passed_fresh": passed,
                     "caught_by_freshness": passed == 0,
                     "defences": full})
    return arts

def fam_print(lfw):
    arts = []
    sources = [("owner_selfie", OWNER_SELFIE)] + [(f"lfw_{i}", p[0]) for i, p in enumerate(lfw[:2])]
    for label, src in sources:
        img = cv2.imread(src)
        if img is None:
            continue
        printed = simulate_print(img)
        still = save_img(printed, f"print_{label}.jpg")
        # Stable seed (crc32): Python's hash() is per-process
        # randomised and made artefact jitter non-reproducible
        # between runs — caught in WS2 when the pulse leg's verdict
        # on identical artefacts flipped with the seed.
        seed = zlib.crc32(label.encode()) % 1000
        video = write_video(present_on_paper(printed, seed=seed), os.path.join(WORK, f"print_{label}.mp4"))
        arts.append({"artefact": label, "kind": "simulated_print_presented",
                     "still_signals": {"moire": AUTH.moire_signal(still), "pixel_grid": AUTH.pixel_grid_signal(still)},
                     "defences": run_defences(video, still)})
    return arts

def fam_screen():
    arts = []
    for label, src in (("owner_clean_take", OWNER_CLEAN), ("owner_hard_take", OWNER_HARD)):
        frames = read_frames(src, 160)
        if not frames:
            continue
        sim = [simulate_screen_frame(fr, t=i / FPS, strength=1.0) for i, fr in enumerate(frames)]
        video = write_video(sim, os.path.join(WORK, f"screen_{label}.mp4"))
        arts.append({"artefact": label, "kind": "simulated_screen_replay",
                     "defences": run_defences(video, OWNER_SELFIE)})
    return arts

def fam_mask(lfw):
    arts = []
    sources = [("owner_selfie", OWNER_SELFIE)] + [(f"lfw_{i}", p[0]) for i, p in enumerate(lfw[:1])]
    for label, src in sources:
        img = cv2.imread(src)
        if img is None:
            continue
        video = write_video(simulate_mask(img), os.path.join(WORK, f"mask_{label}.mp4"))
        arts.append({"artefact": label, "kind": "simulated_rigid_mask_proxy",
                     "defences": run_defences(video, src)})
    return arts

def fam_deepfake_sim(lfw):
    arts = []
    if not lfw:
        return arts
    # Morph stills: owner x LFW, LFW x LFW.
    for label, a, b in (("morph_owner_lfw", OWNER_SELFIE, lfw[0][0]),
                        ("morph_lfw_pair", lfw[0][0], lfw[1][0] if len(lfw) > 1 else lfw[0][1])):
        m = morph_images(a, b)
        if m is None:
            continue
        still = save_img(m, f"deepfake_{label}.jpg")
        match = FACE.check_face_match(OWNER_DOC, still)
        # The owner's session-1 document capture yields no YuNet face
        # (measured — see BIOMETRICS.md), so the production doc match
        # cannot score these stills; the same morph is ALSO matched
        # against the owner's selfie as the reference face, labelled
        # as a substituted reference, so the morph's match-evasion is
        # still measured rather than skipped.
        match_ref = FACE.check_face_match(OWNER_SELFIE, still)
        arts.append({"artefact": label, "kind": "simulated_face_morph_still",
                     "face_match_vs_owner_doc": {"status": match["status"],
                                                 "similarity": match["findings"].get("similarity")},
                     "face_match_vs_owner_selfie_reference": {"status": match_ref["status"],
                                                              "similarity": match_ref["findings"].get("similarity")}})
    # Morph-composited video: owner's clean take with the face region
    # replaced by the owner x LFW morph (identity diluted, motion real).
    m = morph_images(OWNER_SELFIE, lfw[0][0])
    frames = read_frames(OWNER_CLEAN, 160)
    if m is not None and frames:
        out_frames = []
        morph_big = cv2.resize(m, (220, 220))
        for fr in frames:
            f2 = fr.copy()
            row = FACE.largest_face(f2)
            if row is not None:
                x, y, w, h = [int(v) for v in row[:4]]
                patch = cv2.resize(m, (w, h))
                mask = np.zeros((h, w), np.float64)
                cv2.ellipse(mask, (w // 2, h // 2), (int(w * 0.46), int(h * 0.46)), 0, 0, 360, 1.0, -1)
                mask = cv2.GaussianBlur(mask, (31, 31), 0)[:, :, None]
                roi = f2[y:y + h, x:x + w].astype(np.float64)
                f2[y:y + h, x:x + w] = (patch.astype(np.float64) * mask + roi * (1 - mask)).astype(np.uint8)
            out_frames.append(f2)
        video = write_video(out_frames, os.path.join(WORK, "deepfake_morph_video.mp4"))
        arts.append({"artefact": "morph_composited_video", "kind": "simulated_morph_video",
                     "defences": run_defences(video, OWNER_SELFIE)})
    # Identity crossfade video: owner frames -> LFW identity frames.
    other = cv2.imread(lfw[0][0])
    if frames and other is not None:
        h, w = frames[0].shape[:2]
        other_r = cv2.resize(other, (w, h))
        swap = frames[:len(frames) // 2] + [other_r.copy() for _ in range(len(frames) // 2)]
        video = write_video(swap, os.path.join(WORK, "deepfake_crossfade_video.mp4"))
        arts.append({"artefact": "identity_crossfade_video", "kind": "simulated_identity_swap_video",
                     "defences": run_defences(video, OWNER_SELFIE)})
    return arts

def controls():
    out = []
    for label, path in (("owner_clean_take", OWNER_CLEAN), ("owner_hard_take", OWNER_HARD)):
        out.append({"artefact": label, "kind": "genuine_control",
                    "defences": run_defences(path, OWNER_SELFIE, OWNER_CHALLENGE)})
    m = FACE.check_face_match(OWNER_DOC, OWNER_SELFIE)
    out.append({"artefact": "owner_doc_vs_selfie", "kind": "genuine_control_still",
                "face_match": {"status": m["status"], "similarity": m["findings"].get("similarity")}})
    return out

# ---------------------------------------------------------------- summary

def _family_summary(arts, verdict_key="defences"):
    n = len(arts)
    rej = sum(1 for a in arts if a.get(verdict_key, {}).get("rejected"))
    blk = sum(1 for a in arts if a.get(verdict_key, {}).get("blocked"))
    return {"n": n, "rejected": rej, "blocked_not_rejected": blk,
            "catch_rate_rejected": (rej / n) if n else None,
            "blocked_or_rejected_rate": ((rej + blk) / n) if n else None}

def run(out_path=None):
    if cv2 is None or not FACE.models_present():
        raise SystemExit("opencv/models unavailable — attack suite cannot run (fail closed)")
    os.makedirs(WORK, exist_ok=True)
    lfw = lfw_faces(3)
    result = {"source_material": "owner's stored real captures + LFW faces",
              "families": {}, "controls": controls()}
    print("[attacks] controls done")
    result["families"]["replay"] = {"label": "REAL artefacts (genuine videos replayed vs fresh challenges)",
                                   "artefacts": fam_replay()}
    rp = result["families"]["replay"]["artefacts"]
    result["families"]["replay"]["summary"] = {
        "n": len(rp),
        "caught_by_freshness": sum(1 for a in rp if a["caught_by_freshness"]),
        "liveness_passed_fresh_total": sum(a["liveness_passed_fresh"] for a in rp),
        "liveness_fresh_evaluations": sum(len(a["liveness_under_fresh_challenges"]) for a in rp)}
    print("[attacks] replay done")
    for name, fn, label in (
            ("print", lambda: fam_print(lfw), "SIMULATED print (synthesised print texture on genuine photos)"),
            ("screen", fam_screen, "SIMULATED screen replay (synthesised moire/grid/flicker on genuine frames)"),
            ("mask", lambda: fam_mask(lfw), "SIMULATED rigid-mask proxy ONLY — physical masks UNMEASURED"),
            ("deepfake", lambda: fam_deepfake_sim(lfw), "SIMULATED morph/composite — DNN face-swap corpus UNMEASURED")):
        arts = fn()
        result["families"][name] = {"label": label, "artefacts": arts,
                                    "summary": _family_summary([a for a in arts if "defences" in a])}
        print(f"[attacks] {name} done: {result['families'][name]['summary']}")
    if out_path:
        with open(out_path, "w") as f:
            json.dump(result, f, indent=1, default=str)
    return result

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "benchmarks", "attacks.json"))
    args = ap.parse_args()
    run(args.out)
    print("[attacks] wrote", args.out)

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""PAD evaluation harness (Phase 4 WS8) — ISO/IEC 30107-3 style
metrics for the active-liveness check, computed two ways:

  1. FEATURE-LEVEL SYNTHETIC BATTERY (always runs): deterministic
     synthetic feature streams (bona-fide performances that follow
     the issued challenge; attack classes: static-photo replay,
     face-absent, partial/wrong-movement replay) are scored by the
     PRODUCTION liveness analysis (server.liveness.analyse_features).
     Metrics: APCER per attack class and overall, BPCER (split:
     rejected vs not-passed), ACER. This measures the DECISION
     LOGIC on synthetic features — it is NOT a laboratory PAD
     certification and must never be cited as one.
  2. VIDEO CORPUS (--corpus DIR): bona_fide/ and attack_<kind>/
     subdirectories of videos, each with a challenge.json beside
     it ({"movements": [...]}), scored end-to-end by
     check_liveness (YuNet + analysis). An accredited-lab
     evaluation (iBeta PAD L1/L2) needs physical artefacts and
     real subjects — this harness is the readiness step, not the
     certificate.

Writes benchmarks/PAD-EVAL.md. Exit 0 always (it reports; the
numbers are the result).
"""
import json, os, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server import liveness as LV

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRIALS = 40
FRAMES = 30


def _stream(rng, centres, pix_base=42.0, pix_jitter=6.0, face_ratio=1.0, frozen=False):
    feats = []
    for (cx, cy) in centres:
        face = rng.random() < face_ratio
        feats.append({"face": face, "cx": cx, "cy": cy, "size": 0.3,
                      "pix_std": pix_base if frozen else pix_base + rng.uniform(-pix_jitter, pix_jitter)})
    return feats


def bona_fide(rng, challenge, jitter=0.003, face_ratio=1.0):
    centres = []
    cx, cy = 0.50, 0.50
    per = FRAMES // (len(challenge["movements"]) + 1)
    centres += [(cx + rng.uniform(-jitter, jitter), cy + rng.uniform(-jitter, jitter)) for _ in range(per)]
    for d in challenge["movements"]:
        for i in range(per):
            t = (i + 1) / per
            dx = dy = 0.0
            if d == "left": dx = -0.10 * t
            if d == "right": dx = 0.10 * t
            if d == "up": dy = -0.10 * t
            if d == "down": dy = 0.10 * t
            centres.append((cx + dx + rng.uniform(-jitter, jitter),
                            cy + dy + rng.uniform(-jitter, jitter)))
        cx, cy = centres[-1]
    while len(centres) < FRAMES:
        centres.append((cx + rng.uniform(-jitter, jitter), cy + rng.uniform(-jitter, jitter)))
    return _stream(rng, centres[:FRAMES], face_ratio=face_ratio)


def attack_static(rng, challenge):
    return _stream(rng, [(0.50, 0.50)] * FRAMES, frozen=True)


def attack_absent(rng, challenge):
    return [{"face": False, "cx": 0.0, "cy": 0.0, "size": 0.0, "pix_std": 40.0 + i % 3} for i in range(FRAMES)]


def attack_partial(rng, challenge):
    """Performs only the FIRST challenged movement (a truncated
    replay): must not pass."""
    partial = {"movements": challenge["movements"][:1]}
    return bona_fide(rng, partial)


def compute_metrics(results):
    """results: {class_name: [status,...]} with 'bona_fide' the
    genuine class and every other class an attack class."""
    bf = results.get("bona_fide", [])
    bpcer_reject = (sum(1 for s in bf if s == "fail") / len(bf)) if bf else None
    bpcer_nonpass = (sum(1 for s in bf if s != "pass") / len(bf)) if bf else None
    apcer = {}
    total_attacks = total_passed = 0
    for cls, statuses in results.items():
        if cls == "bona_fide" or not statuses:
            continue
        passed = sum(1 for s in statuses if s == "pass")
        apcer[cls] = passed / len(statuses)
        total_attacks += len(statuses); total_passed += passed
    apcer_all = (total_passed / total_attacks) if total_attacks else None
    acer = None
    if apcer_all is not None and bpcer_reject is not None:
        acer = (apcer_all + bpcer_reject) / 2
    return {"apcer": apcer, "apcer_overall": apcer_all,
            "bpcer_reject": bpcer_reject, "bpcer_nonpass": bpcer_nonpass,
            "acer": acer, "counts": {k: len(v) for k, v in results.items()}}


def run_synthetic():
    rng = random.Random(20261027)
    results = {"bona_fide": [], "attack_static_photo": [], "attack_face_absent": [],
               "attack_partial_replay": [], "bona_fide_noisy": []}
    for _ in range(TRIALS):
        ch = LV.new_challenge(rng)
        results["bona_fide"].append(LV.analyse_features(bona_fide(rng, ch), ch)["status"])
        results["attack_static_photo"].append(LV.analyse_features(attack_static(rng, ch), ch)["status"])
        results["attack_face_absent"].append(LV.analyse_features(attack_absent(rng, ch), ch)["status"])
        results["attack_partial_replay"].append(LV.analyse_features(attack_partial(rng, ch), ch)["status"])
        ch2 = LV.new_challenge(rng)
        results["bona_fide_noisy"].append(
            LV.analyse_features(bona_fide(rng, ch2, jitter=0.008, face_ratio=0.9), ch2)["status"])
    # noisy bona-fides count toward BPCER too
    results["bona_fide"] += results.pop("bona_fide_noisy")
    return results


def run_corpus(corpus):
    results = {}
    for cls in sorted(os.listdir(corpus)):
        cdir = os.path.join(corpus, cls)
        if not os.path.isdir(cdir):
            continue
        key = "bona_fide" if cls == "bona_fide" else cls
        results[key] = []
        for f in sorted(os.listdir(cdir)):
            if not f.rsplit(".", 1)[-1].lower() in ("mp4", "webm", "mov", "mkv"):
                continue
            ch = {}
            cj = os.path.join(cdir, os.path.splitext(f)[0] + ".challenge.json")
            if os.path.exists(cj):
                ch = json.load(open(cj))
            res = LV.check_liveness(os.path.join(cdir, f), ch)
            results[key].append(res["status"])
    return results


def _pct(x):
    return "n/a" if x is None else f"{x * 100:.1f}%"


def main():
    corpus = None
    if "--corpus" in sys.argv:
        corpus = sys.argv[sys.argv.index("--corpus") + 1]
    lines = ["# PAD Evaluation — liveness (WS8 readiness)", "",
             "Metrics follow ISO/IEC 30107-3 definitions: **APCER** = attack "
             "presentations incorrectly passed; **BPCER** = bona-fide "
             "presentations incorrectly rejected; **ACER** = their mean. "
             "For this platform 'unclear' is NOT a pass (it routes to "
             "review), so an attack only succeeds on status 'pass'; BPCER is "
             "reported split (reject = 'fail' only; nonpass = fail+unclear).", ""]
    syn = compute_metrics(run_synthetic())
    lines += ["## Feature-level synthetic battery (production decision logic)", "",
              f"{TRIALS} trials per class, deterministic seed; bona-fide class "
              f"includes a noisy variant (heavy jitter, 90% face presence). "
              f"Counts: {json.dumps(syn['counts'])}", "",
              f"- APCER (overall): **{_pct(syn['apcer_overall'])}**",
              *[f"- APCER ({k}): {_pct(v)}" for k, v in sorted(syn["apcer"].items())],
              f"- BPCER (reject): **{_pct(syn['bpcer_reject'])}** · BPCER (nonpass): {_pct(syn['bpcer_nonpass'])}",
              f"- ACER: **{_pct(syn['acer'])}**", ""]
    if corpus and os.path.isdir(corpus):
        vid = compute_metrics(run_corpus(corpus))
        lines += ["## Video corpus (end-to-end)", "",
                  f"Corpus: `{corpus}` — counts: {json.dumps(vid['counts'])}", "",
                  f"- APCER (overall): **{_pct(vid['apcer_overall'])}**",
                  f"- BPCER (reject): **{_pct(vid['bpcer_reject'])}** · BPCER (nonpass): {_pct(vid['bpcer_nonpass'])}",
                  f"- ACER: **{_pct(vid['acer'])}**", ""]
    else:
        lines += ["## Video corpus (end-to-end)", "",
                  "No corpus supplied. A video-level evaluation needs recorded "
                  "bona-fide performances and attack artefacts (printed photo, "
                  "screen replay, mask) — none exist yet, so NO video-level "
                  "metric is claimed.", ""]
    lines += ["## What this is and is not", "",
              "- This harness measures the production decision logic on "
              "synthetic features, reproducibly. It is a READINESS step.",
              "- It is **not** an iBeta / ISO 30107-3 laboratory certification: "
              "that requires an accredited lab, physical attack artefacts and "
              "real subjects. No PAD certification is claimed anywhere until "
              "a lab report exists.",
              "- The WS2 face-match operating point (EER 1.07% @ 0.288 on the "
              "LFW protocol; FAR 0.10% / FRR 2.00% at the shipped 0.363 "
              "threshold) is the biometric claim backed by measurement; this "
              "document adds the liveness-logic numbers beside it.", ""]
    out = os.path.join(ROOT, "benchmarks", "PAD-EVAL.md")
    open(out, "w").write("\n".join(lines))
    print("\n".join(lines))
    print("written:", out)


if __name__ == "__main__":
    main()

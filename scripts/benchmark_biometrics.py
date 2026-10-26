#!/usr/bin/env python3
"""FAR/FRR benchmark for the production face-match pipeline
(Phase 4 WS2).

Dataset: Labeled Faces in the Wild (LFW), standard View-2 protocol —
the official pairs.txt (6,000 pairs: 10 folds x 300 same-person +
300 different-person), run against the DEEP-FUNNELED image release
(the alignment variant distributed by the dataset authors and used
by scikit-learn's fetch_lfw_people; image filenames/indices are the
same as the original release, so pairs.txt applies unchanged).

Pipeline under test: the PRODUCTION path — YuNet detection + SFace
embeddings via server/bioprovider.SFaceProvider (provider #1, which
wraps server/face.py). No side pipeline: if this harness has a bug
the numbers are wrong in the same way production would be, and the
embedding cache records exactly which images produced no face.

Metrics: FAR/FRR across a threshold sweep, EER (linear interpolation
of the FAR/FRR crossing), FAR + FRR + accuracy AT the production
threshold (cosine 0.363), and the standard-protocol accuracy (per
fold, threshold chosen on the other nine folds). Detection failures
(pairs where YuNet found no face in either image) are EXCLUDED from
the curves and reported as their own number — they are not silently
counted as rejects.

Condition slices: the same pairs with SIMULATED degradations applied
to the second image of each pair (darkening = low-light proxy,
downscale-upscale = low-resolution/device-tier proxy, Gaussian blur).
These are simulations on real faces, labelled as such everywhere the
numbers travel. LFW carries no demographic attributes, so NO
skin-tone/age slicing is reported — see benchmarks/BIOMETRICS.md.

Usage:
    python3 scripts/benchmark_biometrics.py [--folds 10]
        [--slice-folds 2] [--out benchmarks/biometrics.json]
"""
import argparse, json, os, sys, tarfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from server import bioprovider

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS = os.path.join(ROOT, "benchmarks", "corpus")
PAIRS_FILE = os.path.join(CORPUS, "pairs.txt")
ARCHIVE = os.path.join(CORPUS, "lfwfunneled.tgz")
IMAGES_DIR = os.path.join(CORPUS, "lfw_funneled")
PRODUCTION_THRESHOLD = 0.363  # face.DEFAULT_THRESHOLD, OpenCV-published SFace value

# ---------------------------------------------------------------- corpus

def ensure_corpus():
    """Extract the funneled archive if needed; return image root."""
    if os.path.isdir(IMAGES_DIR) and any(d for d in os.listdir(IMAGES_DIR)):
        # Normalise: images may sit one level deeper (lfw_funneled/lfw/...).
        subs = [os.path.join(IMAGES_DIR, d) for d in os.listdir(IMAGES_DIR)]
        person_dirs = [d for d in subs if os.path.isdir(d) and any(
            f.endswith(".jpg") for f in os.listdir(d))]
        if person_dirs:
            return IMAGES_DIR
        for d in subs:
            if os.path.isdir(d):
                inner = [os.path.join(d, x) for x in os.listdir(d)]
                if any(os.path.isdir(x) and any(f.endswith(".jpg") for f in os.listdir(x)) for x in inner):
                    return d
        return IMAGES_DIR
    if not os.path.isfile(ARCHIVE):
        raise SystemExit(f"LFW archive missing: {ARCHIVE} (see benchmarks/BIOMETRICS.md for sources)")
    with tarfile.open(ARCHIVE, "r:gz") as tf:
        tf.extractall(CORPUS, filter="data")  # data filter: no ownership/permission replay
    return ensure_corpus()

def image_relpath(person, idx):
    return f"{person}/{person}_{idx:04d}.jpg"

def load_pairs(pairs_file=PAIRS_FILE):
    """Parse the official pairs.txt -> list of dicts with fold info.
    Format: header '10\\t300'; each fold is 300 same lines
    (name, i, j) then 300 different lines (name1, i, name2, j)."""
    with open(pairs_file) as f:
        lines = [ln.rstrip("\n") for ln in f if ln.strip()]
    n_folds, per_fold = (int(x) for x in lines[0].split("\t"))
    pairs = []
    body = lines[1:]
    block = per_fold * 2
    for fold in range(n_folds):
        chunk = body[fold * block:(fold + 1) * block]
        for ln in chunk[:per_fold]:
            name, i, j = ln.split("\t")
            pairs.append({"a": image_relpath(name, int(i)), "b": image_relpath(name, int(j)),
                          "same": True, "fold": fold})
        for ln in chunk[per_fold:]:
            n1, i, n2, j = ln.split("\t")
            pairs.append({"a": image_relpath(n1, int(i)), "b": image_relpath(n2, int(j)),
                          "same": False, "fold": fold})
    return pairs

# ---------------------------------------------------------------- embeddings

class EmbeddingStore:
    """Embedding cache: manifest (relpath -> row) + matrix npz on disk.
    A relpath present with detected=False records a genuine YuNet
    no-face result — cached too, so re-runs never re-litigate it."""

    def __init__(self, cache_base, image_root):
        self.manifest_path = cache_base + ".manifest.json"
        self.matrix_path = cache_base + ".npz"
        self.image_root = image_root
        self.manifest = {}
        self.rows = []
        self.detected = []
        if os.path.isfile(self.manifest_path) and os.path.isfile(self.matrix_path):
            with open(self.manifest_path) as f:
                saved = json.load(f)
            self.manifest = {k: tuple(v) for k, v in saved.items()}
            z = np.load(self.matrix_path)
            self.rows = [r for r in z["rows"]]
            self.detected = [bool(d) for d in z["detected"]]
        self.provider = bioprovider.get_provider("own:sface")

    def get(self, relpath, transform=None):
        """-> embedding (np.array) or None (no face / error).
        transform: optional callable(img_bgr) -> img_bgr applied BEFORE
        embedding (degradation slices); cache keys include it."""
        key = relpath if transform is None else f"{transform}::{relpath}"
        if key in self.manifest:
            idx, det = self.manifest[key]
            return self.rows[idx] if det else None
        emb = None
        try:
            if transform is None:
                emb, marker = self.provider.embed(os.path.join(self.image_root, relpath))
            else:
                emb = self._embed_transformed(relpath, transform)
        except Exception:
            emb = None
        idx = len(self.rows)
        self.rows.append(np.asarray(emb, dtype=np.float64) if emb is not None else np.zeros(128))
        self.detected.append(emb is not None)
        self.manifest[key] = (idx, emb is not None)
        return np.asarray(emb, dtype=np.float64) if emb is not None else None

    def _embed_transformed(self, relpath, transform_name):
        import cv2
        img = cv2.imread(os.path.join(self.image_root, relpath))
        if img is None:
            return None
        img = DEGRADATIONS[transform_name](img)
        tmp = os.path.join(CORPUS, ".tmp_degraded.jpg")
        cv2.imwrite(tmp, img)
        emb, _marker = self.provider.embed(tmp)
        return emb

    def save(self):
        os.makedirs(os.path.dirname(self.manifest_path), exist_ok=True)
        with open(self.manifest_path, "w") as f:
            json.dump({k: list(v) for k, v in self.manifest.items()}, f)
        np.savez(self.matrix_path,
                 rows=np.asarray(self.rows, dtype=np.float64),
                 detected=np.asarray(self.detected, dtype=bool))

# ---------------------------------------------------------------- degradations (SIMULATED conditions)

def _degrade_dark(img):
    """Low-light proxy: brightness x0.45."""
    return np.clip(img.astype(np.float64) * 0.45, 0, 255).astype(np.uint8)

def _degrade_downscale(img):
    """Low-resolution / low-tier-device proxy: downscale to 25% then
    upscale back (the information is gone; the frame size is not)."""
    import cv2
    h, w = img.shape[:2]
    small = cv2.resize(img, (max(8, w // 4), max(8, h // 4)), interpolation=cv2.INTER_AREA)
    return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)

def _degrade_blur(img):
    """Defocus/motion-blur proxy: Gaussian blur, 9x9 kernel."""
    import cv2
    return cv2.GaussianBlur(img, (9, 9), 2.0)

DEGRADATIONS = {"dark": _degrade_dark, "downscale": _degrade_downscale, "blur": _degrade_blur}

# ---------------------------------------------------------------- metrics (pure)

def pair_scores(pairs, store, transform=None):
    """-> (records, detection_failures). Each record: (sim, same, fold).
    transform degrades image B of every pair (the 'probe')."""
    records, failures = [], 0
    for p in pairs:
        ea = store.get(p["a"])
        eb = store.get(p["b"], transform=transform)
        if ea is None or eb is None:
            failures += 1
            continue
        sim = float(np.dot(ea, eb) / ((np.linalg.norm(ea) or 1e-12) * (np.linalg.norm(eb) or 1e-12)))
        records.append((sim, p["same"], p["fold"]))
    return records, failures

def far_frr(records, threshold):
    same = [s for s, is_same, _ in records if is_same]
    diff = [s for s, is_same, _ in records if not is_same]
    frr = (sum(1 for s in same if s < threshold) / len(same)) if same else None
    far = (sum(1 for s in diff if s >= threshold) / len(diff)) if diff else None
    acc = None
    if same and diff:
        acc = (sum(1 for s in same if s >= threshold) + sum(1 for s in diff if s < threshold)) / len(records)
    return {"threshold": round(threshold, 4), "far": far, "frr": frr, "accuracy": acc}

def sweep_and_eer(records, steps=401):
    """Threshold sweep 0.0..1.0 + EER by linear interpolation of the
    FAR/FRR crossing."""
    curve = []
    for i in range(steps):
        t = i / (steps - 1)
        m = far_frr(records, t)
        curve.append({"t": round(t, 4), "far": m["far"], "frr": m["frr"]})
    eer, eer_t = None, None
    for a, b in zip(curve, curve[1:]):
        d1 = (a["far"] or 0) - (a["frr"] or 0)
        d2 = (b["far"] or 0) - (b["frr"] or 0)
        if d1 == 0:
            eer, eer_t = a["far"], a["t"]; break
        if d1 * d2 < 0:
            frac = abs(d1) / (abs(d1) + abs(d2))
            eer = a["far"] + frac * (b["far"] - a["far"])
            eer_t = a["t"] + frac * (b["t"] - a["t"])
            break
    if eer is None and curve:
        best = min(curve, key=lambda c: abs((c["far"] or 0) - (c["frr"] or 0)))
        eer, eer_t = (best["far"] + best["frr"]) / 2, best["t"]
    return curve, {"eer": eer, "eer_threshold": eer_t}

def protocol_accuracy(records):
    """Standard LFW reporting: for each fold, pick the threshold that
    maximises accuracy on the OTHER folds, apply it to this fold."""
    folds = sorted(set(f for _, _, f in records))
    accs = []
    for fold in folds:
        train = [r for r in records if r[2] != fold]
        test = [r for r in records if r[2] == fold]
        if not train or not test:
            continue
        best_t, best_acc = 0.0, -1.0
        for i in range(201):
            t = i / 200
            m = far_frr(train, t)
            if m["accuracy"] is not None and m["accuracy"] > best_acc:
                best_acc, best_t = m["accuracy"], t
        m = far_frr(test, best_t)
        if m["accuracy"] is not None:
            accs.append(m["accuracy"])
    if not accs:
        return {"mean": None, "std": None, "folds": 0}
    mean = sum(accs) / len(accs)
    var = sum((a - mean) ** 2 for a in accs) / len(accs)
    return {"mean": mean, "std": var ** 0.5, "folds": len(accs)}

def threshold_for_far(records, target_far):
    """Smallest swept threshold whose measured FAR <= target (the
    data-driven way to set a threshold for a use case), with the FRR
    paid for it. None when the target is unreachable in the sweep."""
    for i in range(1001):
        t = i / 1000
        m = far_frr(records, t)
        if m["far"] is not None and m["far"] <= target_far:
            return {"threshold": round(t, 3), "far": m["far"], "frr": m["frr"], "target_far": target_far}
    return {"threshold": None, "far": None, "frr": None, "target_far": target_far}

def summarise(records, failures, total_pairs):
    curve, eer = sweep_and_eer(records)
    at_prod = far_frr(records, PRODUCTION_THRESHOLD)
    return {
        "pairs_total": total_pairs,
        "pairs_scored": len(records),
        "detection_failure_pairs": failures,
        "detection_failure_rate": (failures / total_pairs) if total_pairs else None,
        "eer": eer["eer"], "eer_threshold": eer["eer_threshold"],
        "at_production_threshold": at_prod,
        "protocol_accuracy": protocol_accuracy(records),
        "curve": curve,
    }

# ---------------------------------------------------------------- main

def run(folds=10, slice_folds=2, out_path=None):
    image_root = ensure_corpus()
    all_pairs = load_pairs()
    pairs = [p for p in all_pairs if p["fold"] < folds]
    store = EmbeddingStore(os.path.join(CORPUS, "embeddings_clean"), image_root)
    uniques = sorted(set([p["a"] for p in pairs] + [p["b"] for p in pairs]))
    print(f"[bench] {len(pairs)} pairs, {len(uniques)} unique images to embed (clean)")
    for i, rel in enumerate(uniques):
        store.get(rel)
        if (i + 1) % 500 == 0:
            print(f"[bench] clean embeddings {i + 1}/{len(uniques)}")
            store.save()
    store.save()
    records, failures = pair_scores(pairs, store)
    result = {
        "dataset": "LFW deep-funneled (figshare/sklearn mirror), official pairs.txt View-2 protocol",
        "provider": "own:sface (server/bioprovider.py -> server/face.py YuNet+SFace)",
        "production_threshold": PRODUCTION_THRESHOLD,
        "clean": summarise(records, failures, len(pairs)),
        "threshold_analysis": {
            "auto_approve_candidate": threshold_for_far(records, 0.001),
            "high_assurance_candidate": threshold_for_far(records, 0.0001),
        },
        "slices_simulated": {},
    }
    slice_pairs = [p for p in all_pairs if p["fold"] < slice_folds]
    for name in DEGRADATIONS:
        srecords, sfail = pair_scores(slice_pairs, store, transform=name)
        s = summarise(srecords, sfail, len(slice_pairs))
        s.pop("curve", None)
        result["slices_simulated"][name] = s
        print(f"[bench] slice {name}: scored {len(srecords)}/{len(slice_pairs)} pairs")
    store.save()
    if out_path:
        with open(out_path, "w") as f:
            json.dump(result, f, indent=1)
    return result

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folds", type=int, default=10)
    ap.add_argument("--slice-folds", type=int, default=2)
    ap.add_argument("--out", default=os.path.join(ROOT, "benchmarks", "biometrics.json"))
    args = ap.parse_args()
    result = run(args.folds, args.slice_folds, args.out)
    c = result["clean"]
    print(f"[bench] pairs scored {c['pairs_scored']}/{c['pairs_total']} "
          f"(detection failures {c['detection_failure_pairs']})")
    print(f"[bench] EER {c['eer']} @ {c['eer_threshold']}")
    print(f"[bench] @ production {PRODUCTION_THRESHOLD}: {c['at_production_threshold']}")
    print(f"[bench] protocol accuracy: {c['protocol_accuracy']}")

if __name__ == "__main__":
    main()

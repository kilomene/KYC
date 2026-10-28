"""Face match (Phase 2): YuNet detection + SFace embeddings (OpenCV Zoo).

Models live in <repo>/models/ (gitignored, fetched by
scripts/fetch_models.py). If a model is absent, or OpenCV is unavailable,
the check returns status 'error' with reason 'model_missing' — NEVER a
fake pass (the Phase 1 fail-closed pattern).

Decision logic is a pure function of the cosine similarity so it is fully
unit-testable without the models:
  sim >= threshold + margin  -> pass
  sim >= threshold - margin  -> unclear (near threshold: a human looks)
  sim <  threshold - margin  -> fail (face_mismatch)
OpenCV's published SFace cosine threshold is 0.363; it is the default
`pass_threshold`, and both values are tenant-configurable (flow config).
YuNet landmarks from a detection row: [x, y, w, h, re_x, re_y, le_x, le_y,
nose_x, nose_y, rm_x, rm_y, lm_x, lm_y, score] — indices 4..13 are the
5 landmarks FaceRecognizerSF.alignCrop expects in the row's tail.
"""
import math, os

try:
    import cv2
    import numpy as np
except Exception:  # OpenCV missing -> face checks error, never pass
    cv2 = None
    np = None

MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")
YUNET_FILE = "face_detection_yunet_2023mar.onnx"
SFACE_FILE = "face_recognition_sface_2021dec.onnx"
DEFAULT_THRESHOLD = 0.363  # OpenCV's published SFace cosine threshold
DEFAULT_MARGIN = 0.05

_cache = {}

def models_present():
    return all(os.path.isfile(os.path.join(MODELS_DIR, f)) and os.path.getsize(os.path.join(MODELS_DIR, f)) > 100_000
               for f in (YUNET_FILE, SFACE_FILE))

def _detector(width, height):
    key = ("yunet", width, height)
    if key not in _cache:
        _cache[key] = cv2.FaceDetectorYN_create(os.path.join(MODELS_DIR, YUNET_FILE), "", (width, height), 0.6, 0.3, 5000)
    return _cache[key]

def _recognizer():
    if "sface" not in _cache:
        _cache["sface"] = cv2.FaceRecognizerSF_create(os.path.join(MODELS_DIR, SFACE_FILE), "")
    return _cache["sface"]

def cosine_similarity(a, b):
    """Pure cosine similarity of two embedding vectors (lists or arrays)."""
    if np is not None:
        a = np.asarray(a, dtype=np.float64).ravel(); b = np.asarray(b, dtype=np.float64).ravel()
        na, nb = float(np.linalg.norm(a)), float(np.linalg.norm(b))
        if na == 0 or nb == 0: return 0.0
        return float(np.dot(a, b) / (na * nb))
    na = math.sqrt(sum(float(x) ** 2 for x in a)); nb = math.sqrt(sum(float(x) ** 2 for x in b))
    if na == 0 or nb == 0: return 0.0
    return sum(float(x) * float(y) for x, y in zip(a, b)) / (na * nb)

def similarity_decision(sim, pass_threshold=DEFAULT_THRESHOLD, margin=DEFAULT_MARGIN):
    """Pure decision on a similarity score -> (status, reason_codes)."""
    if sim is None:
        return "error", ["face_compare_error"]
    if sim >= pass_threshold + margin:
        return "pass", []
    if sim >= pass_threshold - margin:
        return "unclear", ["face_match_near_threshold"]
    return "fail", ["face_mismatch"]

MAX_DETECT_DIM = 1024  # see below: YuNet degrades measurably above this

def detect_faces(img):
    """YuNet detection on a BGR image array. Returns list of face rows
    (largest first) or [] when no face is found.

    WS2 measurement (benchmarks/BIOMETRICS.md): on multi-megapixel
    stills YuNet's boxes shrink and drift as the input grows, and
    past ~1280px on the longest side the SFace alignment breaks —
    measured on the owner's real 2316x3088 selfie against his own
    liveness frame: cosine 0.435 at 512px, 0.390 at 1024, 0.205 at
    1280, -0.052 at 1600, and no face at all at full size in the
    pre-WS2 code. Detection therefore runs on a copy downscaled to
    MAX_DETECT_DIM and the returned boxes/landmarks are rescaled to
    the original coordinate frame for box consumers (portrait-region
    and ROI logic). Embedding consumers use work_image() space
    directly (extract_face_feature, facetrack) so their landmarks
    are native. Images at or below the cap take the exact original
    path — LFW (250px), video frames and flow captures are
    unaffected."""
    h, w = img.shape[:2]
    scale = 1.0
    work = img
    if max(h, w) > MAX_DETECT_DIM:
        scale = MAX_DETECT_DIM / float(max(h, w))
        work = cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))),
                          interpolation=cv2.INTER_AREA)
    wh, ww = work.shape[:2]
    det = _detector(ww, wh)
    _, faces = det.detect(work)
    if faces is None or len(faces) == 0:
        return []
    out = []
    for f in faces:
        f = [float(v) for v in f]
        if scale != 1.0:
            inv = 1.0 / scale
            for i in (0, 2, 4, 6, 8, 10, 12):  # x, w, landmark xs
                f[i] *= inv
            for i in (1, 3, 5, 7, 9, 11, 13):  # y, h, landmark ys
                f[i] *= inv
        out.append(np.array(f, dtype=np.float32) if np is not None else f)
    return sorted(out, key=lambda f: f[2] * f[3], reverse=True)

def largest_face(img):
    faces = detect_faces(img)
    return faces[0] if faces else None

_DNN_FACE_NET = None

def detect_face_box_any(img):
    """Portrait-presence fallback (2026-10-28 vision sharpening):
    YuNet first; when YuNet sees no face, a second, architecturally
    different detector (OpenCV DNN ResNet-10 SSD, models fetched
    alongside the YuNet/SFace pair) takes a turn. Returns
    (x, y, w, h) in image pixels or None. PRESENCE ONLY — the box
    carries no landmarks, so it must never feed SFace alignment or
    matching; its job is the document-portrait statistic that
    drives capture coaching (a portrait YuNet misses on a small or
    degraded print is exactly the weak-reference case)."""
    global _DNN_FACE_NET
    row = largest_face(img)
    if row is not None:
        return (float(row[0]), float(row[1]), float(row[2]), float(row[3]))
    if cv2 is None or not hasattr(cv2, "dnn"):
        return None
    proto = os.path.join(MODELS_DIR, "face_deploy.prototxt")
    model = os.path.join(MODELS_DIR, "face_res10.caffemodel")
    if not (os.path.exists(proto) and os.path.exists(model)):
        return None
    try:
        if _DNN_FACE_NET is None:
            _DNN_FACE_NET = cv2.dnn.readNetFromCaffe(proto, model)
        h, w = img.shape[:2]
        blob = cv2.dnn.blobFromImage(cv2.resize(img, (300, 300)), 1.0,
                                     (300, 300), (104.0, 177.0, 123.0))
        _DNN_FACE_NET.setInput(blob)
        dets = _DNN_FACE_NET.forward()
        best = None
        for i in range(dets.shape[2]):
            conf = float(dets[0, 0, i, 2])
            if conf < 0.5:
                continue
            x0, y0, x1, y1 = (int(dets[0, 0, i, 3] * w), int(dets[0, 0, i, 4] * h),
                              int(dets[0, 0, i, 5] * w), int(dets[0, 0, i, 6] * h))
            area = max(0, x1 - x0) * max(0, y1 - y0)
            if best is None or area > best[0]:
                best = (area, (float(x0), float(y0), float(x1 - x0), float(y1 - y0)))
        return best[1] if best else None
    except Exception:
        return None

def face_feature(img, face_row):
    """SFace 128-d embedding for an aligned face."""
    rec = _recognizer()
    aligned = rec.alignCrop(img, face_row)
    feat = rec.feature(aligned)
    return feat.ravel()

def work_image(img):
    """The image in detection/embedding space: downscaled to
    MAX_DETECT_DIM when larger. SFace normalises every aligned crop
    to 112x112, so embedding in this space loses nothing measurable
    (LFW operates at 250px) — while embedding at full phone-photo
    resolution measurably corrupts the result, because YuNet's box
    shrinks/drifts with input size (WS2 scale sweep in
    benchmarks/BIOMETRICS.md: same-face cosine vs a video frame
    falls from 0.435 at 512px to -0.05 at 1600px)."""
    h, w = img.shape[:2]
    if max(h, w) <= MAX_DETECT_DIM:
        return img
    scale = MAX_DETECT_DIM / float(max(h, w))
    return cv2.resize(img, (max(1, int(w * scale)), max(1, int(h * scale))),
                      interpolation=cv2.INTER_AREA)

def extract_face_feature(path):
    """-> (feature, face_row, error_dict). On success error_dict is
    None. Detection + embedding both run in work_image space so the
    landmarks alignCrop consumes are native to the image embedded."""
    img = cv2.imread(path)
    if img is None:
        return None, None, {"status": "unclear", "findings": {"error": "image_unreadable"}, "reason_codes": ["face_image_unreadable"]}
    work = work_image(img)
    face = largest_face(work)
    if face is None:
        return None, None, None  # no face found (distinct from an error)
    return face_feature(work, face), face, None

def _error(reason, detail):
    return {"status": "error", "findings": {"error": detail}, "reason_codes": [reason]}

def check_face_match(doc_path, selfie_path, pass_threshold=DEFAULT_THRESHOLD, margin=DEFAULT_MARGIN):
    """Compare the largest face in the document image with the selfie."""
    if cv2 is None:
        return _error("model_missing", "opencv_unavailable")
    if not models_present():
        return _error("model_missing", "face_models_not_fetched_run_scripts/fetch_models.py")
    if not doc_path or not selfie_path:
        return {"status": "not_run", "findings": {"reason": "document_or_selfie_missing"}, "reason_codes": ["face_match_not_run"]}
    try:
        doc_feat, doc_face, err = extract_face_feature(doc_path)
        if err: return err
        if doc_face is None:
            return {"status": "unclear", "findings": {"face_in_document": False}, "reason_codes": ["no_face_in_document"]}
        self_feat, self_face, err = extract_face_feature(selfie_path)
        if err: return err
        if self_face is None:
            return {"status": "unclear", "findings": {"face_in_document": True, "face_in_selfie": False}, "reason_codes": ["no_face_in_selfie"]}
        sim = cosine_similarity(doc_feat, self_feat)
    except Exception as e:
        return _error("face_compare_error", str(e)[:200])
    status, reasons = similarity_decision(sim, pass_threshold, margin)
    return {"status": status,
            "findings": {"similarity": round(float(sim), 4), "pass_threshold": pass_threshold, "margin": margin,
                         "method": "yunet+sface_cosine", "face_in_document": True, "face_in_selfie": True},
            "reason_codes": reasons}

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

def detect_faces(img):
    """YuNet detection on a BGR image array. Returns list of face rows
    (largest first) or [] when no face is found."""
    h, w = img.shape[:2]
    det = _detector(w, h)
    _, faces = det.detect(img)
    if faces is None or len(faces) == 0:
        return []
    return sorted([f for f in faces], key=lambda f: f[2] * f[3], reverse=True)

def largest_face(img):
    faces = detect_faces(img)
    return faces[0] if faces else None

def face_feature(img, face_row):
    """SFace 128-d embedding for an aligned face."""
    rec = _recognizer()
    aligned = rec.alignCrop(img, face_row)
    feat = rec.feature(aligned)
    return feat.ravel()

def extract_face_feature(path):
    """-> (feature, face_row, error_dict). On success error_dict is None."""
    img = cv2.imread(path)
    if img is None:
        return None, None, {"status": "unclear", "findings": {"error": "image_unreadable"}, "reason_codes": ["face_image_unreadable"]}
    face = largest_face(img)
    if face is None:
        return None, None, None  # no face found (distinct from an error)
    return face_feature(img, face), face, None

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

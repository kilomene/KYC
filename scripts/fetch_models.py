#!/usr/bin/env python3
"""Download the OpenCV Zoo face models used by Phase 2 face checks.

Models (from https://github.com/opencv/opencv_zoo, licences in that repo:
YuNet — MIT; SFace — Apache 2.0; the .onnx files are downloaded at setup
time, they are NOT committed to this repo — models/ is gitignored):

  * face_detection_yunet_2023mar.onnx   (YuNet face detector)
  * face_recognition_sface_2021dec.onnx (SFace face recogniser — this is
    the SFace model file opencv_zoo actually ships; there is no
    "2023dec" SFace file in that repo)

The .onnx files in opencv_zoo are Git LFS objects, so downloads go
through media.githubusercontent.com (a plain raw.githubusercontent fetch
returns the 131-byte LFS pointer, not the model).

Usage: python3 scripts/fetch_models.py
If a model is absent at runtime, the face checks return status 'error'
with reason 'model_missing' — never a fake pass.
"""
import os, sys, urllib.request

BASE = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models"
FILES = {
    "face_detection_yunet/face_detection_yunet_2023mar.onnx": "face_detection_yunet_2023mar.onnx",
    "face_recognition_sface/face_recognition_sface_2021dec.onnx": "face_recognition_sface_2021dec.onnx",
}
MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models")

def main():
    os.makedirs(MODELS_DIR, exist_ok=True)
    ok = True
    for src, name in FILES.items():
        dest = os.path.join(MODELS_DIR, name)
        if os.path.isfile(dest) and os.path.getsize(dest) > 100_000:
            print(f"[models] {name} already present ({os.path.getsize(dest)} bytes)")
            continue
        url = f"{BASE}/{src}"
        print(f"[models] downloading {url}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "kyc-fetch-models"})
            with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
                f.write(r.read())
            print(f"[models] {name}: {os.path.getsize(dest)} bytes")
            if os.path.getsize(dest) < 100_000:
                print(f"[models] WARNING: {name} looks too small — download may have failed"); ok = False
        except Exception as e:
            print(f"[models] FAILED {name}: {e}"); ok = False
    print("[models] OK" if ok else "[models] INCOMPLETE — face checks will report model_missing")
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())

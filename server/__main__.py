import argparse
from .app import serve

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="KYC Phase 1 local MVP")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--data-dir", default="data")
    a = ap.parse_args()
    serve(port=a.port, data_dir=a.data_dir)

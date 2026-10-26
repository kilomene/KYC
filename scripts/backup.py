#!/usr/bin/env python3
"""Backup + restore for the KYC data directory (Phase 4 WS3).

A backup is a directory containing:
    kyc.db              consistent SQLite snapshot (sqlite3 backup API,
                        never a raw copy of a live file)
    files/              the media tree, byte-for-byte (files stay in
                        their stored form — encrypted when WS3 media
                        encryption is on; the master key itself is
                        NEVER in the backup)
    platform_secret.key the credential-signing secret, when present
                        (without it, restored credentials cannot be
                        verified — it is part of the data, treat the
                        backup as secret material)
    lists/              screening lists, when present
    manifest.json       counts, sizes and SHA-256 checksums for the DB
                        and every file, plus the master-key FINGERPRINT
                        (a hash prefix — enough to verify a restore
                        holds the right key, useless for decryption)

Restore verifies every checksum and the restored table counts
against the manifest before reporting success; a mismatch aborts.

Usage:
    python3 scripts/backup.py --data-dir data --out backups/2026-10-26
    python3 scripts/backup.py --restore backups/2026-10-26 --dest data-restored
"""
import argparse, hashlib, json, os, shutil, sqlite3, sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TABLES = ["tenants", "api_keys", "applicants", "consents", "sessions", "documents",
          "biometric_captures", "checks", "decisions", "cases", "webhook_endpoints",
          "webhook_deliveries", "audit_log", "deletions", "flow_configs", "tenant_users",
          "screening_hits", "monitoring_alerts", "businesses", "business_people",
          "business_documents", "credentials", "ip_intel_cache"]

class BackupError(Exception):
    pass

def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 256), b""):
            h.update(chunk)
    return h.hexdigest()

def _table_counts(db_path):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES if t in existing}
    finally:
        conn.close()

def _tree_files(root):
    out = []
    for dirpath, _dirs, names in os.walk(root):
        for name in sorted(names):
            out.append(os.path.relpath(os.path.join(dirpath, name), root))
    return sorted(out)

def create_backup(data_dir, out_dir):
    db_path = os.path.join(data_dir, "kyc.db")
    if not os.path.isfile(db_path):
        raise BackupError(f"no database at {db_path}")
    if os.path.isdir(out_dir) and os.listdir(out_dir):
        raise BackupError(f"backup destination {out_dir} exists and is not empty — refusing to overwrite")
    os.makedirs(out_dir, exist_ok=True)
    # Consistent DB snapshot via the SQLite backup API.
    dst_path = os.path.join(out_dir, "kyc.db")
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(dst_path)
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()
    # Media tree + config files.
    files_meta = {}
    total_bytes = 0
    src_files = os.path.join(data_dir, "files")
    if os.path.isdir(src_files):
        for rel in _tree_files(src_files):
            target = os.path.join(out_dir, "files", rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(os.path.join(src_files, rel), target)
            files_meta[rel] = _sha256_file(target)
            total_bytes += os.path.getsize(target)
    extras = {}
    for name in ("platform_secret.key",):
        p = os.path.join(data_dir, name)
        if os.path.isfile(p):
            shutil.copy2(p, os.path.join(out_dir, name))
            extras[name] = _sha256_file(os.path.join(out_dir, name))
    lists_meta = {}
    src_lists = os.path.join(data_dir, "lists")
    if os.path.isdir(src_lists):
        for rel in _tree_files(src_lists):
            target = os.path.join(out_dir, "lists", rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(os.path.join(src_lists, rel), target)
            lists_meta[rel] = _sha256_file(target)
    fingerprint = None
    try:
        from server import storage as _storage
        fingerprint = _storage.key_fingerprint()
    except Exception:
        fingerprint = None
    manifest = {
        "format": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_dir_name": os.path.basename(os.path.abspath(data_dir)),
        "db_sha256": _sha256_file(dst_path),
        "db_bytes": os.path.getsize(dst_path),
        "tables": _table_counts(dst_path),
        "files": {"count": len(files_meta), "bytes": total_bytes, "sha256": files_meta},
        "lists": {"count": len(lists_meta), "sha256": lists_meta},
        "extras_sha256": extras,
        "encryption": {"master_key_fingerprint": fingerprint,
                       "note": "the master key is never in the backup; the fingerprint lets a restore verify it holds the same key"},
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    return manifest

def restore_backup(backup_dir, dest_dir):
    manifest_path = os.path.join(backup_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        raise BackupError(f"no manifest.json in {backup_dir}")
    with open(manifest_path) as f:
        manifest = json.load(f)
    if os.path.isdir(dest_dir) and os.listdir(dest_dir):
        raise BackupError(f"restore destination {dest_dir} exists and is not empty — refusing to overwrite")
    os.makedirs(dest_dir, exist_ok=True)
    src_db = os.path.join(backup_dir, "kyc.db")
    if _sha256_file(src_db) != manifest["db_sha256"]:
        raise BackupError("database checksum mismatch — backup is corrupt")
    shutil.copy2(src_db, os.path.join(dest_dir, "kyc.db"))
    verified_files = 0
    for rel, sha in (manifest["files"]["sha256"] or {}).items():
        src = os.path.join(backup_dir, "files", rel)
        if not os.path.isfile(src) or _sha256_file(src) != sha:
            raise BackupError(f"media file checksum mismatch: {rel}")
        target = os.path.join(dest_dir, "files", rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(src, target)
        verified_files += 1
    for rel, sha in (manifest.get("lists", {}).get("sha256") or {}).items():
        src = os.path.join(backup_dir, "lists", rel)
        if not os.path.isfile(src) or _sha256_file(src) != sha:
            raise BackupError(f"list file checksum mismatch: {rel}")
        target = os.path.join(dest_dir, "lists", rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(src, target)
    for name, sha in (manifest.get("extras_sha256") or {}).items():
        src = os.path.join(backup_dir, name)
        if not os.path.isfile(src) or _sha256_file(src) != sha:
            raise BackupError(f"config file checksum mismatch: {name}")
        shutil.copy2(src, os.path.join(dest_dir, name))
    counts = _table_counts(os.path.join(dest_dir, "kyc.db"))
    if counts != manifest["tables"]:
        raise BackupError(f"restored table counts differ from manifest: {counts} != {manifest['tables']}")
    return {"restored_to": dest_dir, "tables": counts, "files": verified_files, "verified": True}

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="KYC data-dir backup / restore")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("--out")
    ap.add_argument("--restore")
    ap.add_argument("--dest")
    a = ap.parse_args()
    try:
        if a.restore:
            if not a.dest:
                print("--dest is required with --restore", file=sys.stderr); sys.exit(2)
            print(json.dumps(restore_backup(a.restore, a.dest), indent=2))
        else:
            if not a.out:
                print("--out is required for backup", file=sys.stderr); sys.exit(2)
            m = create_backup(a.data_dir, a.out)
            print(json.dumps({"backup": a.out, "db_bytes": m["db_bytes"],
                              "files": m["files"]["count"], "file_bytes": m["files"]["bytes"],
                              "tables": m["tables"]}, indent=2))
    except BackupError as e:
        print(f"BackupError: {e}", file=sys.stderr)
        sys.exit(1)

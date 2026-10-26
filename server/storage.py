"""Encryption at rest for stored media (Phase 4 WS3).

Document images, selfies, liveness videos, burst frames, PoA documents
and KYB documents are written through this module. When a master key
is configured, every file is encrypted with AES-256-GCM
(`cryptography` package) using a fresh random per-file key; the file
key is itself wrapped (AES-256-GCM) under the master key and stored
in the file header — envelope encryption, so the master key never
touches bulk data and can be rotated by re-wrapping.

Wire format (all lengths bytes):
    magic "KYCENC01" (8) | wrap_nonce (12) | wrapped_file_key (48)
    | data_nonce (12) | ciphertext + GCM tag

Master key sources (never the DB, never the repo):
    KYC_MASTER_KEY        base64-encoded 32-byte key, or
    KYC_MASTER_KEY_FILE   path to a file containing that base64 text.

Behaviour matrix (fail closed):
  * key configured   -> writes are encrypted; reads decrypt
                        transparently; legacy plaintext files still
                        read (so migration can be incremental).
  * no key           -> writes stay plaintext (legacy mode, loudly
                        documented in docs/SECURITY.md); reading an
                        ENCRYPTED file raises StorageKeyMissing —
                        encrypted data is never silently mishandled.
  * wrong key/tamper -> decrypt raises StorageError. GCM is
                        authenticated: a flipped byte fails loudly.

`materialize()` gives the check pipeline (OCR/face/authenticity all
read filesystem paths) a plaintext path: the real path for plaintext
files, a temp copy under <data_dir>/.plain_tmp/ for encrypted ones.
Callers must delete temp copies (the HTTP layer does, per request).

Migration: `python3 -m server.storage --data-dir data migrate`
encrypts every plaintext file under <data_dir>/files/ in place and
verifies each one by decrypting and comparing SHA-256 against the
pre-migration hash. `status` reports counts without changing anything.
"""
import base64, binascii, hashlib, os, sys

MAGIC = b"KYCENC01"
_WRAP_NONCE_LEN = 12
_WRAPPED_KEY_LEN = 48  # 32-byte file key + 16-byte GCM tag
_DATA_NONCE_LEN = 12
_HEADER_LEN = len(MAGIC) + _WRAP_NONCE_LEN + _WRAPPED_KEY_LEN + _DATA_NONCE_LEN

class StorageError(Exception):
    """Decryption failed (wrong key, tampered file) or bad config."""

class StorageKeyMissing(StorageError):
    """An encrypted file was read with no master key configured."""

def master_key():
    """-> 32-byte master key, or None when not configured.
    Raises StorageError on a configured-but-malformed key."""
    raw = os.environ.get("KYC_MASTER_KEY", "").strip()
    if not raw:
        path = os.environ.get("KYC_MASTER_KEY_FILE", "").strip()
        if path:
            try:
                with open(path) as f:
                    raw = f.read().strip()
            except OSError as e:
                raise StorageError(f"KYC_MASTER_KEY_FILE unreadable: {e}")
    if not raw:
        return None
    try:
        key = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise StorageError("KYC_MASTER_KEY is not valid base64")
    if len(key) != 32:
        raise StorageError(f"KYC_MASTER_KEY must decode to 32 bytes (got {len(key)})")
    return key

def encryption_enabled():
    return master_key() is not None

def key_fingerprint():
    """Short non-secret identifier of the configured master key (for
    backup manifests: lets a restore verify it holds the same key)."""
    key = master_key()
    return hashlib.sha256(key).hexdigest()[:16] if key else None

def _aesgcm(key):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(key)

def encrypt_bytes(plain, key=None):
    key = key if key is not None else master_key()
    if key is None:
        raise StorageKeyMissing("no master key configured")
    file_key = os.urandom(32)
    wrap_nonce = os.urandom(_WRAP_NONCE_LEN)
    wrapped = _aesgcm(key).encrypt(wrap_nonce, file_key, MAGIC)
    data_nonce = os.urandom(_DATA_NONCE_LEN)
    ct = _aesgcm(file_key).encrypt(data_nonce, plain, MAGIC)
    return MAGIC + wrap_nonce + wrapped + data_nonce + ct

def is_encrypted(data):
    return isinstance(data, (bytes, bytearray)) and bytes(data[:len(MAGIC)]) == MAGIC

def decrypt_bytes(blob, key=None):
    if not is_encrypted(blob):
        raise StorageError("not an encrypted KYC file")
    key = key if key is not None else master_key()
    if key is None:
        raise StorageKeyMissing("encrypted file read with no master key configured")
    try:
        wrap_nonce = bytes(blob[len(MAGIC):len(MAGIC) + _WRAP_NONCE_LEN])
        wrapped = bytes(blob[len(MAGIC) + _WRAP_NONCE_LEN:len(MAGIC) + _WRAP_NONCE_LEN + _WRAPPED_KEY_LEN])
        data_nonce = bytes(blob[len(MAGIC) + _WRAP_NONCE_LEN + _WRAPPED_KEY_LEN:_HEADER_LEN])
        ct = bytes(blob[_HEADER_LEN:])
        file_key = _aesgcm(key).decrypt(wrap_nonce, wrapped, MAGIC)
        return _aesgcm(file_key).decrypt(data_nonce, ct, MAGIC)
    except StorageError:
        raise
    except Exception as e:
        raise StorageError(f"decryption failed (wrong key or tampered file): {type(e).__name__}")

# ---------------- file-level API used by the HTTP layer ----------------

def write_file(data_dir, rel, data):
    """Write `data` to <data_dir>/<rel>, encrypting when a master key
    is configured. Returns rel unchanged (the DB stores rel either
    way — the format is self-describing via the magic header)."""
    full = os.path.join(data_dir, rel)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    blob = encrypt_bytes(data) if encryption_enabled() else bytes(data)
    with open(full, "wb") as f:
        f.write(blob)
    return rel

def read_file(data_dir, rel):
    """Read <data_dir>/<rel> and return the PLAINTEXT bytes.
    Plaintext legacy files pass through; encrypted files decrypt.
    Raises StorageKeyMissing when an encrypted file meets no key."""
    with open(os.path.join(data_dir, rel), "rb") as f:
        blob = f.read()
    return decrypt_bytes(blob) if is_encrypted(blob) else blob

def materialize(data_dir, rel):
    """-> (path, is_temp). A filesystem path holding PLAINTEXT, for
    the path-based check pipeline. Plaintext files: their real path.
    Encrypted files: a decrypted temp copy the caller must delete."""
    full = os.path.join(data_dir, rel)
    with open(full, "rb") as f:
        head = f.read(len(MAGIC))
    if head != MAGIC:
        return full, False
    tmp_dir = os.path.join(data_dir, ".plain_tmp")
    os.makedirs(tmp_dir, exist_ok=True)
    digest = hashlib.sha256(rel.encode()).hexdigest()[:24]
    tmp = os.path.join(tmp_dir, digest + ".tmp")
    with open(tmp, "wb") as f:
        f.write(read_file(data_dir, rel))
    return tmp, True

# ---------------- migration ----------------

def iter_media_files(data_dir):
    root = os.path.join(data_dir, "files")
    for dirpath, _dirs, names in os.walk(root):
        for name in sorted(names):
            yield os.path.join(dirpath, name)

def storage_status(data_dir):
    total = encrypted = plaintext = 0
    for full in iter_media_files(data_dir):
        total += 1
        with open(full, "rb") as f:
            head = f.read(len(MAGIC))
        if head == MAGIC:
            encrypted += 1
        else:
            plaintext += 1
    return {"files": total, "encrypted": encrypted, "plaintext": plaintext,
            "encryption_enabled": encryption_enabled()}

def migrate(data_dir):
    """Encrypt every plaintext media file in place. Each file is
    verified after encryption by decrypting and comparing SHA-256
    with the pre-migration plaintext hash. Returns counts; raises
    StorageKeyMissing when no master key is configured."""
    if not encryption_enabled():
        raise StorageKeyMissing("migration requires KYC_MASTER_KEY (or KYC_MASTER_KEY_FILE)")
    out = {"scanned": 0, "migrated": 0, "already_encrypted": 0, "verified": 0, "errors": []}
    for full in iter_media_files(data_dir):
        out["scanned"] += 1
        with open(full, "rb") as f:
            blob = f.read()
        if is_encrypted(blob):
            out["already_encrypted"] += 1
            continue
        before = hashlib.sha256(blob).hexdigest()
        try:
            enc = encrypt_bytes(blob)
            with open(full, "wb") as f:
                f.write(enc)
            after = hashlib.sha256(decrypt_bytes(enc)).hexdigest()
            if after != before:
                out["errors"].append(f"{full}: verification hash mismatch")
                continue
            out["migrated"] += 1
            out["verified"] += 1
        except Exception as e:
            out["errors"].append(f"{full}: {type(e).__name__}: {e}")
    return out

if __name__ == "__main__":
    import argparse, json
    ap = argparse.ArgumentParser(description="KYC media storage: encryption status / migration")
    ap.add_argument("--data-dir", default="data")
    ap.add_argument("command", choices=("status", "migrate"))
    a = ap.parse_args()
    if a.command == "status":
        print(json.dumps(storage_status(a.data_dir), indent=2))
    else:
        try:
            print(json.dumps(migrate(a.data_dir), indent=2))
        except StorageKeyMissing as e:
            print(f"refused: {e}", file=sys.stderr)
            sys.exit(2)

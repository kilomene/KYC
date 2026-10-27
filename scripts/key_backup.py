#!/usr/bin/env python3
"""Master-key sealed backup (WS8 gap #6 / programme workstream).

The production master key (data/kyc-master.key) decrypts every
stored identity document. Until now it existed in exactly ONE
copy: lose the VM/disk, lose every document, permanently.

This tool SEALS the key: AES-256-GCM encryption under a key
derived from an operator passphrase with scrypt (n=2^15). The
sealed envelope is safe to store off-machine (including in the
git repo) — without the passphrase it is indistinguishable from
random. The passphrase is NEVER written to disk by this tool;
it is read from the KYC_KEY_BACKUP_PASSPHRASE environment
variable at run time only.

Usage:
  KYC_KEY_BACKUP_PASSPHRASE=... python3 scripts/key_backup.py seal \
      [--key-file data/kyc-master.key] [--out data/kyc-master.key.sealed]
  KYC_KEY_BACKUP_PASSPHRASE=... python3 scripts/key_backup.py unseal \
      [--sealed data/kyc-master.key.sealed] --out /path/to/restored.key
  python3 scripts/key_backup.py verify --sealed ... --key-file ...
      (checks a sealed envelope matches a live key file, given
      the passphrase in the environment)
"""
import argparse, base64, hashlib, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

SCRYPT = {"n": 2 ** 15, "r": 8, "p": 1, "dklen": 32}
FORMAT = "kyc-sealed-key-v1"


def _passphrase():
    pw = os.environ.get("KYC_KEY_BACKUP_PASSPHRASE", "")
    if len(pw) < 12:
        raise SystemExit("KYC_KEY_BACKUP_PASSPHRASE must be set (>= 12 chars) in the environment")
    return pw.encode()


def _derive(passphrase, salt):
    # maxmem must be stated explicitly: OpenSSL's default ceiling
    # rejects n=2^15 outright ("memory limit exceeded").
    return hashlib.scrypt(passphrase, salt=salt, maxmem=256 * 1024 * 1024, **SCRYPT)


def seal(key_bytes, passphrase):
    salt = os.urandom(16)
    nonce = os.urandom(12)
    dk = _derive(passphrase, salt)
    ct = AESGCM(dk).encrypt(nonce, key_bytes, FORMAT.encode())
    return {"format": FORMAT, "kdf": "scrypt", "scrypt": SCRYPT,
            "salt": base64.b64encode(salt).decode(),
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ct).decode()}


def unseal(envelope, passphrase):
    if envelope.get("format") != FORMAT:
        raise ValueError("unknown sealed format")
    salt = base64.b64decode(envelope["salt"])
    nonce = base64.b64decode(envelope["nonce"])
    ct = base64.b64decode(envelope["ciphertext"])
    dk = _derive(passphrase, salt)
    return AESGCM(dk).decrypt(nonce, ct, FORMAT.encode())  # raises on wrong passphrase


def _read_key(path):
    raw = open(path).read().strip()
    try:
        return base64.b64decode(raw)
    except Exception:
        return raw.encode()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("seal", "unseal", "verify"))
    ap.add_argument("--key-file", default="data/kyc-master.key")
    ap.add_argument("--sealed", default="data/kyc-master.key.sealed")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.cmd == "seal":
        key = _read_key(a.key_file)
        env = seal(key, _passphrase())
        out = a.out or a.sealed
        open(out, "w").write(json.dumps(env, indent=1))
        os.chmod(out, 0o600)
        print(f"sealed {len(key)}-byte key -> {out} (passphrase NOT stored)")
    elif a.cmd == "unseal":
        env = json.load(open(a.sealed))
        key = unseal(env, _passphrase())
        out = a.out
        if not out:
            raise SystemExit("--out is required for unseal")
        open(out, "w").write(base64.b64encode(key).decode())
        os.chmod(out, 0o600)
        print(f"unsealed -> {out} ({len(key)} bytes)")
    else:  # verify
        env = json.load(open(a.sealed))
        key = unseal(env, _passphrase())
        live = _read_key(a.key_file)
        print("MATCH" if key == live else "MISMATCH")
        return 0 if key == live else 1


if __name__ == "__main__":
    sys.exit(main() or 0)

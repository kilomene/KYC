#!/usr/bin/env python3
"""Backup/restore DRILL (Phase 4 WS3) — executed for real, not described.

Builds a scratch source instance (own data dir, own ports, media
encryption ON with a drill master key), creates a tenant + applicant,
drives a real flow (document + selfie uploads, submit, decision),
then:
  1. backs the data dir up with scripts/backup.py (timed, sized),
  2. restores into a fresh dir with scripts/backup.py (timed;
     checksums + table counts verified inside restore),
  3. boots a server on the RESTORED copy and smoke-tests it:
     /healthz, the known applicant readable with the original tenant
     key, the session status identical, and the stored document image
     readable and byte-identical to the upload (i.e. it decrypts),
  4. boots the restored copy WITHOUT the master key and proves the
     encrypted image read fails closed (503 storage_unavailable).
Writes the measured results to benchmarks/BACKUP-RESTORE.md and
prints a JSON summary. Exit code 0 only when every smoke check passes.
Nothing here touches the production data dir.
"""
import base64, io, json, os, socket, subprocess, sys, tempfile, time, urllib.request, urllib.error, uuid
from datetime import datetime, timezone

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
import backup as BACKUP

def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p

def http(port, method, path, body=None, headers=None, raw=False):
    h = {"Content-Type": "application/json"}
    h.update(headers or {})
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            b = r.read()
            return r.status, (b if raw else json.loads(b or b"{}"))
    except urllib.error.HTTPError as e:
        b = e.read()
        if raw:
            return e.code, b
        try:
            return e.code, json.loads(b or b"{}")
        except Exception:
            return e.code, {}

def multipart(port, path, fields, files, token):
    boundary = "----drill" + uuid.uuid4().hex
    buf = io.BytesIO()
    for k, v in fields.items():
        buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for k, (fn, data, ct) in files.items():
        buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fn}\"\r\nContent-Type: {ct}\r\n\r\n".encode())
        buf.write(data); buf.write(b"\r\n")
    buf.write(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=buf.getvalue(), method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}",
                                          "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except Exception:
            return e.code, {}

def boot(port, data_dir, env_extra):
    env = dict(os.environ)
    env.update(env_extra)
    proc = subprocess.Popen([sys.executable, "-m", "server", "--port", str(port), "--data-dir", data_dir],
                            cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.time() + 30
    while time.time() < deadline:
        try:
            st, _ = http(port, "GET", "/healthz")
            if st == 200:
                return proc
        except Exception:
            pass
        time.sleep(0.25)
    proc.kill()
    raise RuntimeError(f"server on port {port} did not become healthy")

def stop(proc):
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()

def document_bytes():
    from PIL import Image, ImageDraw, ImageFont
    from server.checks import mrz_check_digit
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 36)
        mono = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", 30)
    except Exception:
        font = mono = ImageFont.load_default()
    yy = lambda iso: iso[2:4] + iso[5:7] + iso[8:10]
    docnum, dob6, exp6 = "L898902C3", yy("1974-08-12"), yy("2032-04-15")
    l2 = (docnum + mrz_check_digit(docnum) + "UTO" + dob6 + mrz_check_digit(dob6) + "F"
          + exp6 + mrz_check_digit(exp6) + "<" * 14 + "<" + "0")
    l2 = l2[:43] + mrz_check_digit(l2[0:10] + l2[13:20] + l2[21:43])
    im = Image.new("RGB", (1240, 800), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([20, 20, 1220, 780], outline="black", width=4)
    d.text((60, 60), "PASSPORT", fill="black", font=font)
    d.text((60, 150), "ANNA ERIKSSON", fill="black", font=font)
    d.text((760, 150), docnum, fill="black", font=font)
    d.text((60, 230), "DOB 1974-08-12", fill="black", font=font)
    d.text((60, 300), "EXPIRY 2032-04-15", fill="black", font=font)
    d.text((60, 400), ("P<UTO" + "ERIKSSON" + "<<" + "ANNA").ljust(44, "<")[:44], fill="black", font=mono)
    d.text((60, 460), l2, fill="black", font=mono)
    out = io.BytesIO(); im.save(out, format="PNG")
    return out.getvalue()

def selfie_bytes():
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (640, 640), (210, 190, 170))
    d = ImageDraw.Draw(im)
    d.ellipse([220, 160, 420, 400], outline="black", width=4)
    out = io.BytesIO(); im.save(out, format="PNG")
    return out.getvalue()

def dir_size(path):
    total = 0
    for dirpath, _dirs, names in os.walk(path):
        for n in names:
            total += os.path.getsize(os.path.join(dirpath, n))
    return total

def main():
    started = datetime.now(timezone.utc)
    root = tempfile.mkdtemp(prefix="kyc-drill-", dir=os.path.join(REPO, ".tmp") if os.path.isdir(os.path.join(REPO, ".tmp")) else None)
    src_dir = os.path.join(root, "src-data")
    backup_dir = os.path.join(root, "backup")
    restored_dir = os.path.join(root, "restored-data")
    master_key = base64.b64encode(os.urandom(32)).decode()
    admin = "drill-platform-admin"
    base_env = {"KYC_PLATFORM_ADMIN_TOKEN": admin, "KYC_MASTER_KEY": master_key}
    checks = []
    def check(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": str(detail)})
        return ok

    doc = document_bytes()
    p1 = free_port()
    proc = boot(p1, src_dir, base_env)
    try:
        st, t = http(p1, "POST", "/v1/tenants", {"name": "Drill Tenant", "country": "NG"},
                     headers={"X-Platform-Admin": admin})
        assert st == 201, t
        key = t["keys"]["test"]["key"]
        st, app = http(p1, "POST", "/v1/applicants",
                       {"first_name": "Anna", "last_name": "Eriksson", "dob": "1974-08-12", "country": "NG"},
                       headers={"Authorization": f"Bearer {key}"})
        assert st == 201, app
        st, sess = http(p1, "POST", "/v1/sessions", {"applicant_id": app["id"], "level": 1},
                        headers={"Authorization": f"Bearer {key}"})
        assert st == 201, sess
        token = sess["flow_token"]
        st, r = http(p1, "POST", "/v1/flow/consent", {"text_version": "v2"},
                     headers={"Authorization": f"Bearer {token}"})
        assert st == 200, r
        st, up = multipart(p1, "/v1/flow/document",
                            {"kind": "passport", "issuing_country": "NG", "doc_first_name": "Anna",
                             "doc_last_name": "Eriksson", "doc_dob": "1974-08-12",
                             "doc_expiry": "2032-04-15", "doc_number": "L898902C3"},
                            {"front": ("front.png", doc, "image/png")}, token)
        assert st == 201, up
        doc_id = up["document_id"]
        st, r = multipart(p1, "/v1/flow/selfie", {}, {"selfie": ("selfie.png", selfie_bytes(), "image/png")}, token)
        assert st == 201, r
        st, view = http(p1, "POST", "/v1/flow/submit", {}, headers={"Authorization": f"Bearer {token}"})
        assert st == 200, view
        submit_status = view["status"]
        # The stored document must be ciphertext on disk (encryption on).
        db = BACKUP._table_counts(os.path.join(src_dir, "kyc.db"))
        import sqlite3
        conn = sqlite3.connect(os.path.join(src_dir, "kyc.db"))
        rel = conn.execute("SELECT storage_path FROM documents WHERE id=?", (doc_id,)).fetchone()[0]
        conn.close()
        with open(os.path.join(src_dir, rel), "rb") as f:
            on_disk = f.read()
        check("stored document is ciphertext at rest", on_disk[:8] == b"KYCENC01", f"first bytes {on_disk[:8]!r}")
    finally:
        stop(proc)
    source_counts = BACKUP._table_counts(os.path.join(src_dir, "kyc.db"))

    t0 = time.perf_counter()
    manifest = BACKUP.create_backup(src_dir, backup_dir)
    backup_secs = time.perf_counter() - t0
    backup_size = dir_size(backup_dir)
    check("backup manifest table counts match source DB", manifest["tables"] == source_counts)

    t0 = time.perf_counter()
    report = BACKUP.restore_backup(backup_dir, restored_dir)
    restore_secs = time.perf_counter() - t0
    check("restore checksums + counts verified", report["verified"] and report["tables"] == source_counts)

    p2 = free_port()
    proc = boot(p2, restored_dir, base_env)
    try:
        st, hz = http(p2, "GET", "/healthz")
        check("restored server healthz", st == 200 and hz.get("ok") is True)
        st, app2 = http(p2, "GET", f"/v1/applicants/{app['id']}", headers={"Authorization": f"Bearer {key}"})
        check("known applicant readable after restore",
              st == 200 and app2["first_name"] == "Anna" and app2["last_name"] == "Eriksson", f"status {st}")
        st, sess2 = http(p2, "GET", f"/v1/sessions/{sess['id']}", headers={"Authorization": f"Bearer {key}"})
        check("session status identical after restore", st == 200 and sess2["status"] == submit_status,
              f"{sess2.get('status')} vs {submit_status}")
        st, img = http(p2, "GET", f"/v1/documents/{doc_id}/image", headers={"Authorization": f"Bearer {key}"}, raw=True)
        check("document decrypts after restore (bytes identical)", st == 200 and img == doc,
              f"status {st}, {len(img) if isinstance(img, bytes) else '?'} bytes vs {len(doc)} uploaded")
    finally:
        stop(proc)

    p3 = free_port()
    proc = boot(p3, restored_dir, {"KYC_PLATFORM_ADMIN_TOKEN": admin})  # NO master key
    try:
        st, body = http(p3, "GET", f"/v1/documents/{doc_id}/image", headers={"Authorization": f"Bearer {key}"}, raw=True)
        check("encrypted image read without master key fails closed (503)",
              st == 503 and b"storage_unavailable" in body, f"status {st}")
    finally:
        stop(proc)

    ok = all(c["ok"] for c in checks)
    summary = {"drill": "backup-restore", "at": started.isoformat(), "ok": ok,
               "scratch_dir": root, "backup_bytes": backup_size,
               "backup_seconds": round(backup_secs, 3), "restore_seconds": round(restore_secs, 3),
               "source_tables": source_counts, "submit_status_before_backup": submit_status,
               "checks": checks}
    lines = ["# Backup / Restore Drill — measured results (Phase 4 WS3)", "",
             f"Run: {started.strftime('%Y-%m-%d %H:%M UTC')} by `scripts/restore_drill.py` against a scratch",
             "instance (media encryption ON). Nothing touched the production data dir.", "",
             "## Measured", "",
             f"- Backup size: **{backup_size} bytes** (DB {manifest['db_bytes']} bytes, "
             f"{manifest['files']['count']} media files, {manifest['files']['bytes']} media bytes)",
             f"- Backup wall time: **{backup_secs:.3f}s** · Restore wall time: **{restore_secs:.3f}s**",
             f"- Session decision before backup: `{submit_status}`",
             "", "## Record counts (source DB = backup manifest = restored DB)", "",
             "| Table | Records |", "|---|---:|"]
    for tname in sorted(source_counts):
        lines.append(f"| {tname} | {source_counts[tname]} |")
    lines += ["", "## Smoke checks on the restored copy", ""]
    for c in checks:
        lines.append(f"- [{'PASS' if c['ok'] else 'FAIL'}] {c['check']}" + (f" — {c['detail']}" if c["detail"] else ""))
    lines += ["", "## Honest limits", "",
              "- The drill restores to the same host/filesystem; it proves the backup is complete,",
              "  checksummed and bootable — it is not a cross-site disaster-recovery exercise.",
              "- The master key is NOT in the backup (by design): a restore without the key serves",
              "  metadata but encrypted media reads fail closed (proven above). Key custody is an",
              "  operator responsibility, recorded in the manifest only as a SHA-256 fingerprint.",
              "- platform_secret.key IS in the backup (restored credentials must stay verifiable);",
              "  treat backup directories as secret material.", ""]
    out_path = os.path.join(REPO, "benchmarks", "BACKUP-RESTORE.md")
    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    print(json.dumps(summary, indent=2))
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())

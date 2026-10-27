#!/usr/bin/env python3
"""Seed the STAGING environment with synthetic data only (WS5).

Targets a running staging server (default http://127.0.0.1:8792,
deploy/systemd/kyc-staging.service, data dir data-staging/). It:

  1. reads the staging operator token from
     data-staging/platform-admin.env,
  2. creates a tenant "Staging Synthetic Tenant" via the API,
  3. runs two fully synthetic verifications with the test
     fixtures (invented passport identity + invented slip
     identity — no real person's data ever enters staging),
  4. prints the tenant TEST key for operator use.

Re-running creates another tenant; staging is disposable by
design. Nothing here touches the production data dir or keys.
"""
import json, os, sys, urllib.request, urllib.error

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tests"))
BASE = os.environ.get("KYC_STAGING_URL", "http://127.0.0.1:8792")


def _admin_token():
    path = os.path.join(REPO, "data-staging", "platform-admin.env")
    for line in open(path):
        if line.startswith("KYC_PLATFORM_ADMIN_TOKEN="):
            return line.strip().split("=", 1)[1]
    raise SystemExit("staging operator token not found in " + path)


def call(method, path, body=None, key=None, token=None, admin=None, timeout=240):
    headers = {"Content-Type": "application/json"}
    data = None
    if key:
        headers["Authorization"] = "Bearer " + key
    if token:
        headers["Authorization"] = "Bearer " + token
    if admin:
        headers["X-Platform-Admin"] = admin
    if body is not None:
        data = json.dumps(body).encode()
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")


def main():
    admin = _admin_token()
    st, t = call("POST", "/v1/tenants", {"name": "Staging Synthetic Tenant"}, admin=admin)
    assert st == 201, t
    key = t["keys"]["test"]["key"]
    print("tenant:", t["tenant"]["id"])
    print("test key:", key)
    from helpers import selfie_bytes, id_image_bytes
    from test_identity_from_document import _document_session, _upload_doc
    import helpers

    class _Srv:  # minimal adapter for the test helpers
        base = BASE

    for label in ("passport",):
        app, sess, token = _document_session(_Srv(), key, level=1)
        _upload_doc(_Srv(), token, id_image_bytes(), label)
        # selfie + submit through raw multipart helper
        import io, uuid, urllib.request as ur
        boundary = "----staging" + uuid.uuid4().hex
        parts = []
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"selfie\"; filename=\"selfie.png\"\r\nContent-Type: image/png\r\n\r\n".encode() + selfie_bytes() + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode())
        req = ur.Request(BASE + "/v1/flow/selfie", data=b"".join(parts), method="POST",
                         headers={"Authorization": "Bearer " + token,
                                  "Content-Type": f"multipart/form-data; boundary={boundary}"})
        with ur.urlopen(req, timeout=120) as r:
            assert r.status == 201, r.status
        st, view = call("POST", "/v1/flow/submit", {}, token=token)
        print(label, "session:", view.get("status"), view.get("id") or sess["id"])
    print("STAGING_SEED_DONE")


if __name__ == "__main__":
    main()

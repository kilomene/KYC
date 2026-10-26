"""Shared test helpers: in-process server on an ephemeral port + HTTP client."""
import io, json, os, sys, tempfile, threading, urllib.request, urllib.error, uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PIL import Image, ImageDraw, ImageFilter, ImageFont

def _font(size, mono=False):
    """Real TrueType font at a legible size. PIL's tiny default bitmap font
    is not OCR-legible — using it made tesseract read the test image as
    gibberish even though the same image 'looked' fine (caught in
    verification, 2026-10-26)."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf" if mono else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf" if mono else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        try: return ImageFont.truetype(path, size)
        except Exception: pass
    return ImageFont.load_default(size)
from server.db import DB
from server.app import make_handler
from http.server import ThreadingHTTPServer

class Server:
    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="kyc-test-")
        self.data_dir = os.path.join(self.tmp, "data")
        db = DB(self.data_dir)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(db, self.data_dir))
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.port}"
        return self
    def __exit__(self, *a):
        self.httpd.shutdown(); self.httpd.server_close()

def call(srv, method, path, body=None, key=None, token=None, raw_headers=None):
    headers = {"Content-Type": "application/json"}
    if key: headers["Authorization"] = f"Bearer {key}"
    if token: headers["Authorization"] = f"Bearer {token}"
    if raw_headers: headers.update(raw_headers)
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(srv.base + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read() or b"{}")
        except Exception: return e.code, {}

def multipart(srv, path, fields, files, token):
    """files: {name: (filename, bytes, content_type)}"""
    boundary = "----kyc" + uuid.uuid4().hex
    buf = io.BytesIO()
    for k, v in fields.items():
        buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    for k, (fn, data, ct) in files.items():
        buf.write(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"; filename=\"{fn}\"\r\nContent-Type: {ct}\r\n\r\n".encode())
        buf.write(data); buf.write(b"\r\n")
    buf.write(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(srv.base + path, data=buf.getvalue(), method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read() or b"{}")
        except Exception: return e.code, {}

def make_tenant(srv, name="Test Tenant"):
    st, r = call(srv, "POST", "/v1/tenants", {"name": name, "country": "NG"})
    assert st == 201, r
    return r["tenant"]["id"], r["keys"]["test"]["key"], r["keys"]["live"]["key"]

def id_image_bytes(first="ANNA", last="ERIKSSON", dob="1974-08-12", expiry="2032-04-15", blur=False, size=(1240, 800)):
    im = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(im)
    d.rectangle([20, 20, size[0]-20, size[1]-20], outline="black", width=4)
    d.text((60, 60), "PASSPORT", fill="black", font=_font(44))
    d.text((60, 150), f"{first} {last}", fill="black", font=_font(40))
    d.text((60, 230), f"DOB {dob}", fill="black", font=_font(36))
    d.text((60, 300), f"EXPIRY {expiry}", fill="black", font=_font(36))
    d.text((60, 400), "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<", fill="black", font=_font(30, mono=True))
    d.text((60, 460), "L898902C36UTO7408122F1204159ZE184226B<<<<<10", fill="black", font=_font(30, mono=True))
    # add high-frequency detail so sharpness score is meaningfully high
    for x in range(60, size[0]-60, 18):
        d.line([(x, 560), (x+9, 640)], fill="black", width=2)
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(radius=6))
    out = io.BytesIO(); im.save(out, format="PNG"); return out.getvalue()

def selfie_bytes():
    im = Image.new("RGB", (640, 640), (210, 190, 170))
    d = ImageDraw.Draw(im)
    d.ellipse([220, 160, 420, 400], outline="black", width=4)
    d.text((240, 480), "SELFIE", fill="black", font=_font(36))
    out = io.BytesIO(); im.save(out, format="PNG"); return out.getvalue()

def drive_flow(srv, key, level=2, first="Anna", last="Eriksson", dob="1974-08-12",
               doc_fields=None, doc_bytes=None, country="NG", kind="passport"):
    """Create applicant+session and drive consent/document/selfie. Returns dict."""
    st, app = call(srv, "POST", "/v1/applicants",
                   {"first_name": first, "last_name": last, "dob": dob, "country": "NG", "email": "a@example.com"}, key=key)
    assert st == 201, app
    st, sess = call(srv, "POST", "/v1/sessions", {"applicant_id": app["id"], "level": level}, key=key)
    assert st == 201, sess
    token = sess["flow_token"]
    st, r = call(srv, "POST", "/v1/flow/consent", {"text_version": "v1"}, token=token); assert st == 200, r
    fields = {"kind": kind, "issuing_country": country, "doc_first_name": first, "doc_last_name": last,
              "doc_dob": dob, "doc_expiry": "2032-04-15", "doc_number": "L898902C3"}
    if doc_fields: fields.update(doc_fields)
    st, r = multipart(srv, "/v1/flow/document", fields,
                      {"front": ("front.png", doc_bytes if doc_bytes is not None else id_image_bytes(first=first.upper(), last=last.upper(), dob=dob), "image/png")}, token)
    assert st == 201, r
    st, r = multipart(srv, "/v1/flow/selfie", {}, {"selfie": ("selfie.png", selfie_bytes(), "image/png")}, token)
    assert st == 201, r
    return {"applicant": app, "session": sess, "token": token}

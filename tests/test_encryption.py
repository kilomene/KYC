"""WS3 encryption at rest: AES-256-GCM envelope storage, authorized
reads returning original bytes, wrong/missing key failing closed,
and the verifiable migration of plaintext files."""
import base64, io, json, os, sys, tempfile, threading, unittest, urllib.request, urllib.error
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from http.server import ThreadingHTTPServer
from PIL import Image
from helpers import Server, call, multipart, make_tenant, id_image_bytes, selfie_bytes
from server import storage as STORAGE
from server.db import DB
from server.app import make_handler

KEY_A = base64.b64encode(os.urandom(32)).decode()
KEY_B = base64.b64encode(os.urandom(32)).decode()

def raw_get(port, path, key=None):
    h = {"Authorization": f"Bearer {key}"} if key else {}
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method="GET", headers=h)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()

class KeyEnvCase(unittest.TestCase):
    KEY = KEY_A
    def setUp(self):
        self._saved = os.environ.get("KYC_MASTER_KEY")
        if self.KEY is None:
            os.environ.pop("KYC_MASTER_KEY", None)
        else:
            os.environ["KYC_MASTER_KEY"] = self.KEY
    def tearDown(self):
        if self._saved is None:
            os.environ.pop("KYC_MASTER_KEY", None)
        else:
            os.environ["KYC_MASTER_KEY"] = self._saved

class TestStoragePrimitives(KeyEnvCase):
    def test_roundtrip_and_detection(self):
        blob = STORAGE.encrypt_bytes(b"secret image bytes")
        self.assertTrue(STORAGE.is_encrypted(blob))
        self.assertFalse(STORAGE.is_encrypted(b"plain bytes"))
        self.assertEqual(STORAGE.decrypt_bytes(blob), b"secret image bytes")

    def test_wrong_key_and_tamper_fail(self):
        blob = STORAGE.encrypt_bytes(b"payload")
        wrong = base64.b64decode(KEY_B)
        with self.assertRaises(STORAGE.StorageError):
            STORAGE.decrypt_bytes(blob, key=wrong)
        tampered = bytearray(blob)
        tampered[-1] ^= 0x01
        with self.assertRaises(STORAGE.StorageError):
            STORAGE.decrypt_bytes(bytes(tampered))

    def test_write_read_file_and_materialize(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = os.path.join(tmp, "data")
            rel = os.path.join("files", "t1", "s1", "doc.png")
            STORAGE.write_file(data_dir, rel, b"PNGDATA")
            with open(os.path.join(data_dir, rel), "rb") as f:
                on_disk = f.read()
            self.assertTrue(on_disk.startswith(STORAGE.MAGIC))
            self.assertNotIn(b"PNGDATA", on_disk)
            self.assertEqual(STORAGE.read_file(data_dir, rel), b"PNGDATA")
            path, is_temp = STORAGE.materialize(data_dir, rel)
            self.assertTrue(is_temp)
            with open(path, "rb") as f:
                self.assertEqual(f.read(), b"PNGDATA")
            os.remove(path)

class TestMissingKeyFailsClosed(KeyEnvCase):
    KEY = None
    def test_encrypted_file_without_key_raises(self):
        os.environ["KYC_MASTER_KEY"] = KEY_A
        blob = STORAGE.encrypt_bytes(b"payload")
        os.environ.pop("KYC_MASTER_KEY", None)
        with self.assertRaises(STORAGE.StorageKeyMissing):
            STORAGE.decrypt_bytes(blob)
        # Plaintext legacy files still read fine without a key.
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = os.path.join(tmp, "data")
            os.makedirs(os.path.join(data_dir, "files"))
            with open(os.path.join(data_dir, "files", "x.bin"), "wb") as f:
                f.write(b"legacy")
            self.assertEqual(STORAGE.read_file(data_dir, os.path.join("files", "x.bin")), b"legacy")

class TestMigration(KeyEnvCase):
    def _make_tree(self, tmp):
        data_dir = os.path.join(tmp, "data")
        files = {}
        for name, content in (("a.png", b"image-a"), ("b.jpg", b"image-b")):
            rel = os.path.join("files", "t1", "s1", name)
            os.makedirs(os.path.dirname(os.path.join(data_dir, rel)), exist_ok=True)
            with open(os.path.join(data_dir, rel), "wb") as f:
                f.write(content)
            files[rel] = content
        rel = os.path.join("files", "t1", "s1", "c.png")
        with open(os.path.join(data_dir, rel), "wb") as f:
            f.write(STORAGE.encrypt_bytes(b"image-c"))
        files[rel] = b"image-c"
        return data_dir, files

    def test_migration_encrypts_and_verifies(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, files = self._make_tree(tmp)
            st = STORAGE.storage_status(data_dir)
            self.assertEqual((st["files"], st["encrypted"], st["plaintext"]), (3, 1, 2))
            out = STORAGE.migrate(data_dir)
            self.assertEqual(out["scanned"], 3)
            self.assertEqual(out["migrated"], 2)
            self.assertEqual(out["already_encrypted"], 1)
            self.assertEqual(out["verified"], 2)
            self.assertEqual(out["errors"], [])
            for rel, content in files.items():
                self.assertEqual(STORAGE.read_file(data_dir, rel), content)
            out2 = STORAGE.migrate(data_dir)  # idempotent
            self.assertEqual((out2["migrated"], out2["already_encrypted"]), (0, 3))

    def test_migration_requires_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            data_dir, _ = self._make_tree(tmp)
            os.environ.pop("KYC_MASTER_KEY", None)
            with self.assertRaises(STORAGE.StorageKeyMissing):
                STORAGE.migrate(data_dir)

class TestEncryptedServer(KeyEnvCase):
    def test_upload_encrypted_on_disk_reads_back_and_pipeline_runs(self):
        doc_bytes = id_image_bytes()
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            st, app = call(srv, "POST", "/v1/applicants",
                           {"first_name": "Anna", "last_name": "Eriksson", "dob": "1974-08-12", "country": "NG"}, key=key)
            st, sess = call(srv, "POST", "/v1/sessions", {"applicant_id": app["id"], "level": 1}, key=key)
            token = sess["flow_token"]
            st, r = call(srv, "POST", "/v1/flow/consent", {"text_version": "v2"}, token=token)
            self.assertEqual(st, 200, r)
            st, up = multipart(srv, "/v1/flow/document",
                               {"kind": "passport", "issuing_country": "NG", "doc_first_name": "Anna",
                                "doc_last_name": "Eriksson", "doc_dob": "1974-08-12",
                                "doc_expiry": "2032-04-15", "doc_number": "L898902C3"},
                               {"front": ("front.png", doc_bytes, "image/png")}, token)
            self.assertEqual(st, 201, up)
            doc_id = up["document_id"]
            st, r = multipart(srv, "/v1/flow/selfie", {}, {"selfie": ("selfie.png", selfie_bytes(), "image/png")}, token)
            self.assertEqual(st, 201, r)
            # On disk: ciphertext, not a readable image.
            db = DB(srv.data_dir)
            rel = db.one("SELECT storage_path FROM documents WHERE id=?", (doc_id,))["storage_path"]
            with open(os.path.join(srv.data_dir, rel), "rb") as f:
                on_disk = f.read()
            self.assertTrue(on_disk.startswith(STORAGE.MAGIC))
            with self.assertRaises(Exception):
                Image.open(io.BytesIO(on_disk)).verify()
            # The authorized read path returns the original bytes.
            st, body = raw_get(srv.port, f"/v1/documents/{doc_id}/image", key=key)
            self.assertEqual(st, 200)
            self.assertEqual(body, doc_bytes)
            # The submit pipeline runs on decrypted materializations.
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=token)
            self.assertEqual(st, 200, view)
            self.assertIn("status", view)
            data_dir = srv.data_dir
        # The same data dir served WITHOUT the master key: the image
        # read fails closed (503), never plaintext, never a fake 200.
        os.environ.pop("KYC_MASTER_KEY", None)
        db2 = DB(data_dir)
        httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(db2, data_dir))
        port = httpd.server_address[1]
        th = threading.Thread(target=httpd.serve_forever, daemon=True)
        th.start()
        try:
            st, body = raw_get(port, f"/v1/documents/{doc_id}/image", key=key)
            self.assertEqual(st, 503, body[:200])
            self.assertIn(b"storage_unavailable", body)
        finally:
            httpd.shutdown(); httpd.server_close()

if __name__ == "__main__":
    unittest.main()

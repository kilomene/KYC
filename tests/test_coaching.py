"""Liveness coaching (2026-10-27): the presence endpoint answers
with the production detector (nothing stored), guidance maps
from the face geometry, and the read-back carries portrait
stats for the small-portrait coaching note."""
import io, os, sys, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image
from helpers import Server, call, multipart, make_tenant
from server import face as FACE


def _jpeg(rgb=(200, 200, 200), size=(480, 480)):
    buf = io.BytesIO()
    Image.new("RGB", size, rgb).save(buf, "JPEG")
    return buf.getvalue()


def _flow(srv, key):
    st, app = call(srv, "POST", "/v1/applicants",
                   {"identity_source": "document", "country": "NG"}, key=key)
    assert st == 201, app
    st, sess = call(srv, "POST", "/v1/sessions",
                    {"applicant_id": app["id"], "level": 1}, key=key)
    assert st == 201, sess
    token = sess["flow_token"]
    st, r = call(srv, "POST", "/v1/flow/consent", {"consent": True}, token=token)
    assert st in (200, 201), r
    return token


def _probe(srv, token, data=None):
    return multipart(srv, "/v1/flow/presence", {},
                     {"frame": ("frame.jpg", data or _jpeg(), "image/jpeg")}, token)


class TestPresence(unittest.TestCase):
    def test_blank_frame_no_face(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            token = _flow(srv, key)
            st, r = _probe(srv, token)
            self.assertEqual(st, 200, r)
            self.assertFalse(r["face_present"])
            self.assertEqual(r["guidance"], "no_face_seen")

    def test_guidance_from_geometry(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            token = _flow(srv, key)
            # centred, large -> ok (box x,y,w,h on a 480px frame)
            with mock.patch.object(FACE, "largest_face", return_value=(144, 120, 192, 200)):
                st, r = _probe(srv, token)
                self.assertTrue(r["face_present"]); self.assertEqual(r["guidance"], "ok")
            # centred but small -> move_closer
            with mock.patch.object(FACE, "largest_face", return_value=(200, 190, 60, 70)):
                st, r = _probe(srv, token)
                self.assertEqual(r["guidance"], "move_closer")
            # large but off-centre -> centre_your_face
            with mock.patch.object(FACE, "largest_face", return_value=(0, 120, 190, 200)):
                st, r = _probe(srv, token)
                self.assertEqual(r["guidance"], "centre_your_face")

    def test_presence_stores_nothing(self):
        import sqlite3
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            token = _flow(srv, key)
            _probe(srv, token)
            conn = sqlite3.connect(os.path.join(srv.data_dir, "kyc.db"))
            n = conn.execute("SELECT COUNT(*) FROM biometric_captures").fetchone()[0]
            self.assertEqual(n, 0)


class TestPortraitStats(unittest.TestCase):
    def test_process_payload_carries_portrait(self):
        from helpers import id_image_bytes
        from test_identity_from_document import _document_session, _upload_doc
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            app, sess, token = _document_session(srv, key, level=1)
            did = _upload_doc(srv, token, id_image_bytes(), "passport")["document_id"]
            st, r = call(srv, "POST", "/v1/flow/document/process",
                         {"document_id": did}, token=token)
            self.assertEqual(st, 200, r)
            self.assertIn("portrait", r)
            self.assertIn("found", r["portrait"])
            self.assertIn("size_frac", r["portrait"])


if __name__ == "__main__":
    unittest.main()

"""WS3 backup/restore: checksummed backup of a live test instance,
restore into a scratch dir, count + content verification, and
corruption detection. (The full boot-the-restored-server drill is
scripts/restore_drill.py; its measured output is
benchmarks/BACKUP-RESTORE.md.)"""
import importlib.util, os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import Server, call, multipart, make_tenant, id_image_bytes, selfie_bytes

_spec = importlib.util.spec_from_file_location("kyc_backup", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts", "backup.py"))
BACKUP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BACKUP)
from server.db import DB

class TestBackupRestore(unittest.TestCase):
    def test_backup_restore_roundtrip_and_tamper_detection(self):
        doc_bytes = id_image_bytes()
        with Server() as srv, tempfile.TemporaryDirectory() as tmp:
            _, key, _ = make_tenant(srv)
            st, app = call(srv, "POST", "/v1/applicants",
                           {"first_name": "Backup", "last_name": "Person", "dob": "1990-05-05", "country": "NG"}, key=key)
            st, sess = call(srv, "POST", "/v1/sessions", {"applicant_id": app["id"], "level": 1}, key=key)
            token = sess["flow_token"]
            call(srv, "POST", "/v1/flow/consent", {"text_version": "v2"}, token=token)
            st, up = multipart(srv, "/v1/flow/document",
                               {"kind": "passport", "issuing_country": "NG"},
                               {"front": ("front.png", doc_bytes, "image/png")}, token)
            self.assertEqual(st, 201, up)
            st, r = multipart(srv, "/v1/flow/selfie", {}, {"selfie": ("selfie.png", selfie_bytes(), "image/png")}, token)
            self.assertEqual(st, 201, r)
            doc_id = up["document_id"]
            backup_dir = os.path.join(tmp, "backup")
            manifest = BACKUP.create_backup(srv.data_dir, backup_dir)
            self.assertEqual(manifest["tables"]["tenants"], 1)
            self.assertEqual(manifest["tables"]["applicants"], 1)
            self.assertEqual(manifest["tables"]["documents"], 1)
            self.assertEqual(manifest["files"]["count"], 2)
            self.assertTrue(manifest["db_sha256"])
            # Restoring onto an occupied destination is refused.
            with self.assertRaises(BACKUP.BackupError):
                BACKUP.restore_backup(backup_dir, srv.data_dir)
            restored = os.path.join(tmp, "restored")
            report = BACKUP.restore_backup(backup_dir, restored)
            self.assertTrue(report["verified"])
            self.assertEqual(report["tables"], manifest["tables"])
            self.assertEqual(report["files"], 2)
            db = DB(restored)
            row = db.one("SELECT storage_path FROM documents WHERE id=?", (doc_id,))
            self.assertIsNotNone(row)
            with open(os.path.join(restored, row["storage_path"]), "rb") as f:
                self.assertEqual(f.read(), doc_bytes)  # byte-identical media
            # Corrupt one backed-up media file: restore must refuse.
            victim = os.path.join(backup_dir, row["storage_path"])  # storage_path already starts with files/
            with open(victim, "ab") as f:
                f.write(b"x")
            with self.assertRaises(BACKUP.BackupError):
                BACKUP.restore_backup(backup_dir, os.path.join(tmp, "restored2"))
            # Double backup onto the same destination is refused too.
            with self.assertRaises(BACKUP.BackupError):
                BACKUP.create_backup(srv.data_dir, backup_dir)

if __name__ == "__main__":
    unittest.main()

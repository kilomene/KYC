"""Sealed key backup: roundtrip restores the exact key; a wrong
passphrase fails closed; the envelope carries no key material."""
import importlib.util, os, unittest
spec = importlib.util.spec_from_file_location(
    "key_backup", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                               "scripts", "key_backup.py"))
kb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kb)


class TestSealedKeyBackup(unittest.TestCase):
    def test_roundtrip(self):
        key = os.urandom(32)
        env = kb.seal(key, b"a strong operator passphrase")
        self.assertEqual(kb.unseal(env, b"a strong operator passphrase"), key)

    def test_wrong_passphrase_fails(self):
        env = kb.seal(os.urandom(32), b"a strong operator passphrase")
        with self.assertRaises(Exception):
            kb.unseal(env, b"the wrong passphrase entirely")

    def test_envelope_has_no_plaintext(self):
        import base64, json
        key = base64.b64encode(b"K" * 32)
        env = kb.seal(base64.b64decode(key), b"a strong operator passphrase")
        blob = json.dumps(env)
        self.assertNotIn(key.decode(), blob)
        self.assertEqual(env["format"], "kyc-sealed-key-v1")


if __name__ == "__main__":
    unittest.main()

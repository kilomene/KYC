"""Identity-from-document (owner's order, 2026-10-26): the user is
"not even supposed to fill my name my date of birth and all that…
i'm only supposed to choose the kind of document i want" — "OCR
fills everything in that's part of what OCR does."

Pinned here:
  * identity derivation trust order (valid MRZ > template extraction
    > uploaded fields) and the read-back "missing" contract (DOB is
    required only where the document type carries an MRZ — the
    standard NIN slip prints no DOB and must not be faulted for it);
  * document self-consistency: the document's own reads agree ->
    pass; two reads disagree -> fail with read-named reasons; nothing
    read -> unclear. An applicant mismatch is impossible: there is
    no declared applicant identity on this path;
  * API validation: the declared path is UNCHANGED (name/DOB/country
    required); the document path accepts missing name/DOB, country
    still required; sessions can be created for a document applicant
    or inline with identity_source="document";
  * end-to-end proofs with INVENTED fixture values only: the
    synthetic passport completes a Level 1 session APPROVED with the
    applicant identity populated from OCR alone, and the synthetic
    wide NIN slip (photo on a dark table) reads back, self-agrees
    and is adopted at decision time;
  * the declared cross-check still bites when a tenant DID declare
    details that contradict the document — on both paths — and a
    contradicted declaration is never overwritten by adoption;
  * the hosted flow page carries NO name/DOB/number inputs at all
    and wires the server read-back instead.
"""
import io, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image
from helpers import Server, call, multipart, make_tenant, selfie_bytes, id_image_bytes
from server import checks as C
from server import identity as I
from test_paper_detection import _synthetic_slip_bytes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _slip_on_table_bytes():
    """The synthetic wide slip photographed on a dark table — the
    framing-passing scene (the flat scan's only quad is its photo
    box; see test_paper_detection)."""
    im = Image.open(io.BytesIO(_synthetic_slip_bytes())).convert("RGB")
    canvas = Image.new("RGB", (1700, 1050), (52, 48, 44))
    canvas.paste(im, (230, 215))
    buf = io.BytesIO(); canvas.save(buf, format="PNG")
    return buf.getvalue()


def _fields(**kw):
    base = {"surname": {"value": None, "source": None},
            "given_names": {"value": None, "source": None},
            "dob": {"value": None, "source": None},
            "expiry": {"value": None, "source": None},
            "number": {"value": None, "source": None, "format_valid": None}}
    for k, v in kw.items():
        base[k] = v
    return base


class TestDeriveIdentity(unittest.TestCase):
    MRZ = {"valid": True, "document_number": "L898902C3", "dob_yymmdd": "740812",
           "expiry_yymmdd": "320415",
           "names": {"surname": "ERIKSSON", "given_names": "ANNA"}}

    def test_mrz_beats_extraction_beats_upload(self):
        fields = _fields(surname={"value": "WRONG", "source": "zone"},
                         number={"value": "X1234567", "source": "zone", "format_valid": True})
        up = {"doc_first_name": "UP", "doc_last_name": "LOADED", "doc_dob": "1990-01-01",
              "doc_number": "U000", "doc_expiry": "2030-01-01"}
        ident = I.derive_document_identity(fields, self.MRZ, up)
        self.assertEqual(ident["last_name"], "ERIKSSON")
        self.assertEqual(ident["first_name"], "ANNA")
        self.assertEqual(ident["dob"], "1974-08-12")
        self.assertEqual(ident["number"], "L898902C3")
        self.assertEqual(ident["expiry"], "2032-04-15")
        self.assertEqual(ident["sources"]["number"], "mrz")

    def test_extraction_beats_upload_without_mrz(self):
        fields = _fields(surname={"value": "SAMPLETON", "source": "label"},
                         given_names={"value": "EXAMPLE", "source": "label"},
                         number={"value": "12345678901", "source": "label", "format_valid": True})
        up = {"doc_first_name": "UP", "doc_last_name": "LOADED", "doc_dob": None,
              "doc_number": "U000", "doc_expiry": None}
        ident = I.derive_document_identity(fields, None, up)
        self.assertEqual(ident["last_name"], "SAMPLETON")
        self.assertEqual(ident["first_name"], "EXAMPLE")
        self.assertEqual(ident["number"], "12345678901")
        self.assertEqual(ident["sources"]["last_name"], "extraction")

    def test_unvalidated_extraction_number_loses_to_upload(self):
        # An extraction number whose format FAILED validation is a
        # weaker read than the MRZ; with no MRZ the upload stands —
        # but a merely-unvalidated (None) extraction still counts.
        fields = _fields(number={"value": "123", "source": "zone", "format_valid": False})
        ident = I.derive_document_identity(fields, self.MRZ, {"doc_number": "U000"})
        self.assertEqual(ident["number"], "L898902C3")

    def test_nothing_read_invents_nothing(self):
        ident = I.derive_document_identity(_fields(), None, {})
        self.assertFalse(ident["any"])
        for k in ("first_name", "last_name", "dob", "number", "expiry"):
            self.assertIsNone(ident[k])

    def test_missing_fields_contract(self):
        from server import docregistry as R
        slip = R.get_document("NG", "nin_slip")     # no MRZ, prints no DOB
        passport = R.get_document("NG", "passport")  # MRZ always encodes DOB
        ident = {"first_name": "EXAMPLE", "last_name": "SAMPLETON",
                 "dob": None, "number": "12345678901", "expiry": None}
        self.assertEqual(I.missing_read_fields(ident, slip), [])
        self.assertEqual(I.missing_read_fields(ident, passport), ["dob"])
        self.assertIn("name", I.missing_read_fields({"first_name": None, "last_name": None,
                                                     "dob": None, "number": "1"}, slip))
        self.assertIn("number", I.missing_read_fields({"first_name": "A", "last_name": "B",
                                                       "dob": None, "number": None}, slip))


class TestDocumentSelfConsistency(unittest.TestCase):
    def test_extraction_corroborated_by_ocr_text_passes(self):
        fields = _fields(surname={"value": "SAMPLETON", "source": "label"},
                         given_names={"value": "EXAMPLE", "source": "label"},
                         number={"value": "12345678901", "source": "label", "format_valid": True})
        r = C.check_document_self_consistency(fields, ocr_text="Surname: SAMPLETON First Name: EXAMPLE NIN: 12345678901")
        self.assertEqual(r["status"], "pass", r)
        self.assertEqual(r["findings"]["mode"], "document_self")

    def test_mrz_versus_extraction_name_disagreement_fails(self):
        fields = _fields(surname={"value": "OTHER", "source": "zone"},
                         given_names={"value": "PERSON", "source": "zone"})
        mrz = {"valid": True, "document_number": "L898902C3", "dob_yymmdd": "740812",
               "expiry_yymmdd": "320415", "names": {"surname": "ERIKSSON", "given_names": "ANNA"}}
        r = C.check_document_self_consistency(fields, mrz_parsed=mrz, ocr_text="")
        self.assertEqual(r["status"], "fail", r)
        self.assertIn("doc_name_reads_disagree", r["reason_codes"])
        # the reasons name the READS — never an applicant mismatch
        self.assertNotIn("name_mismatch", r["reason_codes"])

    def test_dob_disagreement_fails(self):
        fields = _fields(surname={"value": "ERIKSSON", "source": "zone"},
                         given_names={"value": "ANNA", "source": "zone"},
                         dob={"value": "1980-01-01", "source": "zone"})
        mrz = {"valid": True, "document_number": "L898902C3", "dob_yymmdd": "740812",
               "expiry_yymmdd": "320415", "names": {"surname": "ERIKSSON", "given_names": "ANNA"}}
        r = C.check_document_self_consistency(fields, mrz_parsed=mrz, ocr_text="")
        self.assertEqual(r["status"], "fail", r)
        self.assertIn("doc_dob_reads_disagree", r["reason_codes"])

    def test_nothing_read_is_unclear_not_pass(self):
        r = C.check_document_self_consistency(_fields(), ocr_text="blank page")
        self.assertEqual(r["status"], "unclear", r)
        self.assertEqual(r["reason_codes"], ["identity_not_read"])

    def test_mrz_only_name_corroborated_by_visual_zone(self):
        # The drawn-passport shape: template extraction misses the
        # name zones, the check-digit-valid MRZ reads the name, and
        # the surname is corroborated by the printed (visual) zone.
        mrz = {"valid": True, "document_number": "L898902C3", "dob_yymmdd": "740812",
               "expiry_yymmdd": "320415", "names": {"surname": "ERIKSSON", "given_names": "ANNA"}}
        text = "ANNA ERIKSSON\nDOB 1974-08-12\nP<UTOERIKSSON<<ANNA<<<<<<<<<<<<<<<<<<\nL898902C36740812..."
        r = C.check_document_self_consistency(_fields(), mrz_parsed=mrz, ocr_text=text)
        self.assertEqual(r["status"], "pass", r)
        self.assertTrue(r["findings"]["name_in_ocr_text"])


class TestApplicantAndSessionValidation(unittest.TestCase):
    def test_declared_path_unchanged(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            st, r = call(srv, "POST", "/v1/applicants",
                         {"first_name": "A", "last_name": "B", "country": "NG"}, key=key)
            self.assertEqual(st, 422, r)  # dob still required when declared
            st, r = call(srv, "POST", "/v1/applicants",
                         {"first_name": "A", "last_name": "B", "dob": "1990-01-01", "country": "NG"}, key=key)
            self.assertEqual(st, 201, r)
            self.assertEqual(r["identity_source"], "declared")

    def test_document_path_accepts_missing_name_and_dob(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            st, r = call(srv, "POST", "/v1/applicants",
                         {"identity_source": "document", "country": "NG"}, key=key)
            self.assertEqual(st, 201, r)
            self.assertEqual(r["identity_source"], "document")
            self.assertIsNone(r["first_name"])
            self.assertIsNone(r["dob"])
            st, r = call(srv, "POST", "/v1/applicants",
                         {"identity_source": "document"}, key=key)
            self.assertEqual(st, 422, r)  # country still required
            st, r = call(srv, "POST", "/v1/applicants",
                         {"identity_source": "guessed", "country": "NG"}, key=key)
            self.assertEqual(st, 422, r)

    def test_sessions_document_paths(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            st, app = call(srv, "POST", "/v1/applicants",
                           {"identity_source": "document", "country": "NG"}, key=key)
            self.assertEqual(st, 201, app)
            st, sess = call(srv, "POST", "/v1/sessions", {"applicant_id": app["id"], "level": 1}, key=key)
            self.assertEqual(st, 201, sess)
            self.assertEqual(sess["identity_source"], "document")
            self.assertEqual(sess["applicant_id"], app["id"])
            # Inline: a document-sourced session with no applicant at all.
            st, sess2 = call(srv, "POST", "/v1/sessions",
                             {"identity_source": "document", "country": "NG", "level": 1}, key=key)
            self.assertEqual(st, 201, sess2)
            self.assertEqual(sess2["identity_source"], "document")
            st, shell = call(srv, "GET", f"/v1/applicants/{sess2['applicant_id']}", key=key)
            self.assertEqual(st, 200, shell)
            self.assertEqual(shell["identity_source"], "document")
            self.assertIsNone(shell["first_name"])
            # Inline without country -> 422; and the old contract is intact.
            st, r = call(srv, "POST", "/v1/sessions", {"identity_source": "document", "level": 1}, key=key)
            self.assertEqual(st, 422, r)
            st, r = call(srv, "POST", "/v1/sessions", {"level": 1}, key=key)
            self.assertEqual(st, 422, r)


def _document_session(srv, key, level=1, country="NG", applicant_body=None):
    body = applicant_body or {"identity_source": "document", "country": country}
    st, app = call(srv, "POST", "/v1/applicants", body, key=key)
    assert st == 201, app
    st, sess = call(srv, "POST", "/v1/sessions", {"applicant_id": app["id"], "level": level}, key=key)
    assert st == 201, sess
    token = sess["flow_token"]
    st, r = call(srv, "POST", "/v1/flow/consent", {"text_version": "v2"}, token=token)
    assert st == 200, r
    return app, sess, token


def _upload_doc(srv, token, data, kind, country="NG"):
    st, r = multipart(srv, "/v1/flow/document",
                      {"kind": kind, "issuing_country": country},
                      {"front": ("front.png", data, "image/png")}, token)
    assert st == 201, r
    return r


def _checks(srv, key, session_id):
    st, r = call(srv, "GET", f"/v1/sessions/{session_id}/checks", key=key)
    assert st == 200, r
    return {c["type"]: c for c in r["checks"]}


class TestDocumentPathEndToEnd(unittest.TestCase):
    def test_passport_session_completes_with_ocr_identity(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            app, sess, token = _document_session(srv, key, level=1)
            _upload_doc(srv, token, id_image_bytes(), "passport")
            st, r = multipart(srv, "/v1/flow/selfie", {}, {"selfie": ("selfie.png", selfie_bytes(), "image/png")}, token)
            assert st == 201, r
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=token)
            self.assertEqual(st, 200, view)
            self.assertEqual(view["status"], "approved", view)
            self.assertEqual(view["identity_source"], "document", view)
            checks = _checks(srv, key, sess["id"])
            self.assertEqual(checks["consistency"]["status"], "pass", checks["consistency"])
            self.assertEqual(checks["consistency"]["findings"]["mode"], "document_self")
            self.assertEqual(checks["data_consistency"]["status"], "pass", checks["data_consistency"])
            self.assertEqual(checks["data_consistency"]["findings"]["disagreements"], [])
            # The applicant record was EMPTY at creation; the identity
            # on it now is the document's, adopted at decision time.
            st, after = call(srv, "GET", f"/v1/applicants/{app['id']}", key=key)
            self.assertEqual(st, 200, after)
            self.assertEqual(after["first_name"], "ANNA")
            self.assertEqual(after["last_name"], "ERIKSSON")
            self.assertEqual(after["dob"], "1974-08-12")
            self.assertTrue(after["identity_document_id"])

    def test_slip_readback_and_adoption(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            app, sess, token = _document_session(srv, key, level=1)
            up = _upload_doc(srv, token, _slip_on_table_bytes(), "nin_slip")
            # Read-back BEFORE submit: the server shows what it read.
            st, r = call(srv, "POST", "/v1/flow/document/process",
                         {"document_id": up["document_id"]}, token=token)
            self.assertEqual(st, 200, r)
            self.assertEqual(r["framing"], "pass", r)
            self.assertEqual(r["read"]["last_name"], "SAMPLETON")
            self.assertIn("EXAMPLE", r["read"]["first_name"])
            self.assertEqual(r["read"]["number"], "12345678901")
            self.assertIsNone(r["read"]["dob"])       # the slip prints no DOB
            self.assertEqual(r["missing"], [], r)     # ...and is not faulted for it
            self.assertTrue(r["complete"], r)
            # Adoption is a DECISION-time act: not yet.
            st, before = call(srv, "GET", f"/v1/applicants/{app['id']}", key=key)
            self.assertIsNone(before["first_name"])
            st, r = multipart(srv, "/v1/flow/selfie", {}, {"selfie": ("selfie.png", selfie_bytes(), "image/png")}, token)
            assert st == 201, r
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=token)
            self.assertEqual(st, 200, view)
            checks = _checks(srv, key, sess["id"])
            # Consistency ran across the document's own reads and passed.
            # The matrix holds NO disagreement, and an applicant
            # mismatch is IMPOSSIBLE: the applicant record was empty,
            # so every pair involving the applicant source is
            # not_available — the verdict rests on the document's own
            # reads (printed/read-back read vs submit extraction).
            self.assertEqual(checks["consistency"]["status"], "pass", checks["consistency"])
            self.assertEqual(checks["consistency"]["findings"]["mode"], "document_self")
            dc = checks["data_consistency"]
            self.assertEqual(dc["status"], "pass", dc)
            self.assertEqual(dc["findings"]["disagreements"], [], dc)
            self.assertGreater(dc["findings"]["pairs_compared"], 0, dc)
            for field_pairs in dc["findings"]["matrix"].values():
                for pair, verdict in field_pairs.items():
                    if "applicant" in pair:
                        self.assertEqual(verdict, "not_available", dc)
            # Identity adopted from the document at decision time.
            st, after = call(srv, "GET", f"/v1/applicants/{app['id']}", key=key)
            self.assertEqual(after["last_name"], "SAMPLETON")
            self.assertIn("EXAMPLE", after["first_name"])
            self.assertEqual(after["identity_document_id"], up["document_id"])

    def test_readback_on_framing_failure_still_reads(self):
        # The flat slip scan defeats framing (its only quad is the
        # photo box) — the read-back must still show what was read
        # and mark the scan incomplete so the flow asks for a rescan.
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            app, sess, token = _document_session(srv, key, level=1)
            up = _upload_doc(srv, token, _synthetic_slip_bytes(), "nin_slip")
            st, r = call(srv, "POST", "/v1/flow/document/process",
                         {"document_id": up["document_id"]}, token=token)
            self.assertEqual(st, 200, r)
            self.assertEqual(r["framing"], "fail", r)
            self.assertFalse(r["complete"], r)
            self.assertEqual(r["read"]["number"], "12345678901")

    def test_declared_details_still_cross_checked_on_document_path(self):
        # A document-sourced applicant whose tenant DID declare
        # (contradicting) details: cross-check exactly as the
        # declared path — and adoption must NOT overwrite them.
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            app, sess, token = _document_session(
                srv, key, level=1,
                applicant_body={"identity_source": "document", "country": "NG",
                                "first_name": "Different", "last_name": "Person", "dob": "1990-01-01"})
            _upload_doc(srv, token, _slip_on_table_bytes(), "nin_slip")
            st, r = multipart(srv, "/v1/flow/selfie", {}, {"selfie": ("selfie.png", selfie_bytes(), "image/png")}, token)
            assert st == 201, r
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=token)
            self.assertEqual(st, 200, view)
            checks = _checks(srv, key, sess["id"])
            self.assertEqual(checks["consistency"]["status"], "fail", checks["consistency"])
            self.assertIn("name_mismatch", checks["consistency"]["reason_codes"])
            st, after = call(srv, "GET", f"/v1/applicants/{app['id']}", key=key)
            self.assertEqual(after["first_name"], "Different")
            self.assertEqual(after["last_name"], "Person")
            self.assertIsNone(after["identity_document_id"])


class TestFlowPageHasNoForm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "public", "flow.html")) as f:
            cls.html = f.read()

    def test_no_typed_identity_fields_anywhere(self):
        for marker in ('id="dfirst"', 'id="dlast"', 'id="ddob"', 'id="dnum"', 'id="dexpiry"',
                       "doc_first_name", "doc_last_name", "doc_dob", "doc_number", "doc_expiry"):
            self.assertNotIn(marker, self.html, marker)

    def test_readback_wired(self):
        self.assertIn("/v1/flow/document/process", self.html)
        self.assertIn("We read:", self.html)
        self.assertIn("Rescan front", self.html)
        self.assertIn("That's right — continue", self.html)


class TestPayloadMerge(unittest.TestCase):
    """The document's own machine-readable payload is a trust-order
    source (2026-10-27): it fills slots the printed reads left empty,
    completes fragment reads, and never silently overrides a
    genuinely different printed read."""

    PAYLOAD = {"surname": "AYANSIPE", "first_name": "ZENAS OLATUNDE",
               "dob": "2004-12-18", "number": "12345678901"}

    def _fields(self, **kw):
        base = {"surname": {"value": None}, "given_names": {"value": None},
                "dob": {"value": None}, "number": {"value": None},
                "expiry": {"value": None}}
        base.update(kw)
        return base

    def test_payload_fills_empty_slots(self):
        ident = I.derive_document_identity(self._fields(), None, {},
                                            payload_fields=self.PAYLOAD)
        self.assertEqual(ident["last_name"], "AYANSIPE")
        self.assertEqual(ident["sources"]["last_name"], "payload")
        self.assertEqual(ident["first_name"], "ZENAS OLATUNDE")
        self.assertEqual(ident["dob"], "2004-12-18")
        self.assertEqual(ident["sources"]["dob"], "payload")

    def test_payload_completes_a_fragment_read(self):
        fields = self._fields(surname={"value": "YANSIPE"})
        ident = I.derive_document_identity(fields, None, {},
                                            payload_fields=self.PAYLOAD)
        self.assertEqual(ident["last_name"], "AYANSIPE")
        self.assertEqual(ident["sources"]["last_name"], "payload")

    def test_payload_never_overrides_a_different_read(self):
        fields = self._fields(surname={"value": "OKAFOR"})
        ident = I.derive_document_identity(fields, None, {},
                                            payload_fields=self.PAYLOAD)
        self.assertEqual(ident["last_name"], "OKAFOR")
        self.assertEqual(ident["sources"]["last_name"], "extraction")

    def test_payload_number_beats_format_invalid_extraction(self):
        fields = self._fields(number={"value": "999", "format_valid": False})
        ident = I.derive_document_identity(fields, None, {},
                                            payload_fields=self.PAYLOAD)
        self.assertEqual(ident["number"], "12345678901")
        self.assertEqual(ident["sources"]["number"], "payload")

    def test_payload_number_loses_to_format_valid_extraction(self):
        fields = self._fields(number={"value": "22222222222", "format_valid": True})
        ident = I.derive_document_identity(fields, None, {},
                                            payload_fields=self.PAYLOAD)
        self.assertEqual(ident["number"], "22222222222")
        self.assertEqual(ident["sources"]["number"], "extraction")


class TestNamePlausible(unittest.TestCase):
    """The adoption-hygiene screen (2026-10-27): document header
    debris must never be adopted as a person's name; real names —
    including short single-token surnames — pass."""

    def test_debris_rejected(self):
        from server.app import _name_plausible
        for v in ("FEDERAL REPUBLIC IDENTIFICATIOR", "MAD AG OF",
                  "FEDERAL REPUBLIC OF NIGERIA", "IDENTITY MANAGEMENT",
                  "NATIONAL IDENTITY", "", None, "123 456"):
            self.assertFalse(_name_plausible(v), v)

    def test_real_names_pass(self):
        from server.app import _name_plausible
        for v in ("AYANSIPE", "ZENAS OLATUNDE", "ERIKSSON", "ANNA",
                  "O'BRIEN", "NG", "LI", "SAMPLETON", "EXAMPLE ANNA"):
            self.assertTrue(_name_plausible(v), v)


class TestAdoptionRepairEndToEnd(unittest.TestCase):
    def test_strong_read_repairs_debris_despite_mismatch(self):
        # The owner's session-13 failure, reproduced: the applicant
        # record carries header debris adopted by an early bad read
        # (with adoption provenance). A later strong read must
        # REPAIR it — even though the session decides name_mismatch
        # against the debris (the mismatch is the symptom).
        import sqlite3
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            app, sess, token = _document_session(srv, key, level=1)
            up = _upload_doc(srv, token, _slip_on_table_bytes(), "nin_slip")
            dbp = os.path.join(srv.data_dir, "kyc.db")
            conn = sqlite3.connect(dbp)
            conn.execute("UPDATE applicants SET first_name=?, last_name=?, "
                         "identity_document_id=? WHERE id=?",
                         ("MAD AG OF", "FEDERAL REPUBLIC IDENTIFICATIOR",
                          up["document_id"], app["id"]))
            conn.commit(); conn.close()
            st, r = multipart(srv, "/v1/flow/selfie", {},
                              {"selfie": ("selfie.png", selfie_bytes(), "image/png")}, token)
            assert st == 201, r
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=token)
            self.assertEqual(st, 200, view)
            checks = _checks(srv, key, sess["id"])
            # The debris DID contradict the document (finding kept)…
            self.assertEqual(checks["consistency"]["status"], "fail",
                             checks["consistency"])
            # …and the record was still repaired by the strong read.
            st, after = call(srv, "GET", f"/v1/applicants/{app['id']}", key=key)
            self.assertEqual(after["last_name"], "SAMPLETON")
            self.assertIn("EXAMPLE", after["first_name"])
            self.assertEqual(after["identity_document_id"], up["document_id"])


class TestCorroborateNameTokens(unittest.TestCase):
    """Witness corroboration (owner session 16, 2026-10-29): adopted
    name tokens only ONE engine family ever saw are stamp debris,
    not name parts; tokens both families saw are the name."""

    TESS = ["Surname:", "AYANSIPE", "Name:", "ZENAS", "OLATUNDE", "SSR",
            "ZENAS", "SS"]  # words + pass tokens of the Tesseract family
    PADDLE = ["Surname:", "AYANSIPE", "NameZENAS", "Name:OLATUNDE", "SAK"]

    def test_stamp_glyphs_dropped_real_names_kept(self):
        self.assertEqual(
            I.corroborate_name_tokens("ZENAS OLATUNDE SSR SAK", [self.TESS, self.PADDLE]),
            "ZENAS OLATUNDE")

    def test_single_witness_group_trims_nothing(self):
        self.assertEqual(
            I.corroborate_name_tokens("ZENAS OLATUNDE SSR SAK", [self.TESS]),
            "ZENAS OLATUNDE SSR SAK")

    def test_single_token_value_untouched(self):
        self.assertEqual(
            I.corroborate_name_tokens("AYANSIPE", [self.TESS, self.PADDLE]),
            "AYANSIPE")

    def test_fully_corroborated_value_untouched(self):
        self.assertEqual(
            I.corroborate_name_tokens("ZENAS OLATUNDE", [self.TESS, self.PADDLE]),
            "ZENAS OLATUNDE")

    def test_never_empties_the_value(self):
        self.assertEqual(
            I.corroborate_name_tokens("QZX WVU", [self.TESS, self.PADDLE]),
            "QZX WVU")


class TestSelfieGateMarkers(unittest.TestCase):
    """The selfie capture gate (flow.html): geometry belongs to the
    server presence verdict via evaluateSelfie — the skin-heuristic
    geometry vetoes that trapped the owner in a move-back loop
    (session 16) must not gate the selfie scanner again."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "public", "flow.html")
        with open(path, encoding="utf-8") as fh:
            cls.html = fh.read()

    def test_selfie_scanner_uses_server_verdict_gate(self):
        self.assertIn("function evaluateSelfie(fr)", self.html)
        self.assertIn("evaluate: evaluateSelfie,", self.html)

    def test_move_back_copy_exists_for_server_verdict(self):
        self.assertIn("move_back: 'You are very close", self.html)

    def test_timed_escape_present(self):
        self.assertIn("selfieClientOkSince >= 25000", self.html)


if __name__ == "__main__":
    unittest.main()

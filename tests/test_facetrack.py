"""Continuous face tracking + the biometric combination gate
(Addition 8, 2026-10-26).

build_track is pure, so identity continuity is tested on synthetic
embeddings: a mid-stream identity swap must break the track
(face_track_identity_break); a consistent track passes and yields the
aggregate embedding the face match uses. The combination test then
drives a full L2 session with the biometric engines stubbed to pass
(they are unit-tested elsewhere; no real-face fixtures exist for the
drawn media) and proves the GATE: all components present + passing ->
auto-approve; device signals absent -> NOT auto-approved."""
import random, unittest
from unittest import mock

from helpers import Server, call, multipart, make_tenant, drive_flow
from server import facetrack as FT
from server import face as FACE
from server import liveness as LV
from server import deepfake as DEEPFAKE

def _emb(dim_axis, seed):
    rng = random.Random(seed)
    v = [rng.gauss(0, 0.02) for _ in range(128)]
    v[dim_axis] += 1.0
    return v

def _frames(axis, n, seed0=0):
    return [{"centre": (0.5, 0.5), "size": 0.3, "embedding": _emb(axis, seed0 + i)} for i in range(n)]

class TestBuildTrack(unittest.TestCase):
    def test_consistent_track_passes_with_aggregate(self):
        res, agg = FT.build_track(_frames(0, 12))
        self.assertEqual(res["status"], "pass", res)
        self.assertIsNotNone(agg)
        self.assertEqual(res["findings"]["presence_ratio"], 1.0)
        self.assertGreater(res["findings"]["identity_min_cosine"], 0.9)

    def test_mid_stream_identity_swap_breaks_track(self):
        frames = _frames(0, 6) + _frames(1, 6, seed0=100)
        res, _ = FT.build_track(frames)
        self.assertEqual(res["status"], "fail", res)
        self.assertIn("face_track_identity_break", res["reason_codes"])

    def test_too_few_frames_is_unclear_never_pass(self):
        res, agg = FT.build_track(_frames(0, 3))
        self.assertEqual(res["status"], "unclear", res)
        self.assertIn("face_track_insufficient", res["reason_codes"])
        self.assertIsNone(agg)

    def test_low_presence_is_unclear(self):
        frames = _frames(0, 6) + [None] * 5   # 6/11 present < 0.8
        res, _ = FT.build_track(frames)
        self.assertEqual(res["status"], "unclear", res)
        self.assertIn("face_track_low_presence", res["reason_codes"])

AGG = [1.0] + [0.0] * 127

def _drive_l2(srv, key, with_signals):
    ctx = drive_flow(srv, key, level=2)
    token = ctx["token"]
    st, ch = call(srv, "POST", "/v1/flow/liveness/challenge", {}, token=token)
    assert st == 201, ch
    meta = {"method": "live_camera"}
    if with_signals:
        meta["client_signals"] = {"track_label": "FaceTime HD Camera",
                                  "motion": {"sensor_present": True, "samples": 140, "variance": 0.31}}
    import json
    st, r = multipart(srv, "/v1/flow/liveness", {"capture_meta": json.dumps(meta)},
                      {"video": ("liveness.webm", b"\x1a\x45\xdf\xa3" + b"\x00" * 64, "video/webm")}, token)
    assert st == 201, r
    return ctx

class TestCombinationGate(unittest.TestCase):
    def _patched_submit(self, srv, key, with_signals):
        ctx = _drive_l2(srv, key, with_signals)
        ok = lambda *a, **k: {"status": "pass", "findings": {}, "reason_codes": []}
        track = lambda *a, **k: {"status": "pass", "findings": {"frames_with_face": 20},
                                 "reason_codes": [], "aggregate_embedding": AGG}
        with mock.patch.object(LV, "check_liveness", side_effect=ok), \
             mock.patch.object(DEEPFAKE, "check_deepfake", side_effect=ok), \
             mock.patch.object(FT, "check_face_track", side_effect=track), \
             mock.patch.object(FACE, "extract_face_feature", return_value=(AGG, object(), None)):
            # The synchronous submit runs the full document pipeline;
            # its budget is 60s (the 15s harness default was a Phase-1
            # leftover and flaked under full-suite CPU load, 2026-10-26).
            # Async processing is the production answer (Phase 4, WS5).
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=ctx["token"], timeout=60)
        assert st == 200, view
        return view

    def test_all_components_passing_auto_approves(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            view = self._patched_submit(srv, key, with_signals=True)
            self.assertEqual(view["status"], "approved", view)
            self.assertEqual(view["checks_summary"]["face_track"], "pass", view)
            self.assertEqual(view["checks_summary"]["biometric_evidence"], "pass", view)

    def test_absent_device_signals_block_auto_approval(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            view = self._patched_submit(srv, key, with_signals=False)
            self.assertNotEqual(view["status"], "approved", view)
            self.assertEqual(view["status"], "needs_review", view)
            self.assertIn("biometric_evidence_incomplete", view["decision"]["reason_codes"], view)
            self.assertEqual(view["checks_summary"]["biometric_evidence"], "unclear", view)

if __name__ == "__main__":
    unittest.main()

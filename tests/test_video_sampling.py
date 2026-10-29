"""Video sampling + liveness presence semantics + weak-reference
face-match gate (2026-10-28, owner session 14).

Field failures pinned here:
  * MediaRecorder WebM frame-count metadata is garbage, and the old
    first-N sampling judged a 9 s performance on its first second.
    video_frames must spread samples across the FULL clip.
  * A real face at a steep angle / backlight scores 0.31-0.38 with
    YuNet — present but not measurable at the production threshold.
    Liveness presence may count consistency-anchored relaxed
    sightings; movement is judged on strict sightings alone.
  * A face-match FAIL against a sub-80px printed portrait (the
    owner's NIN slip: 56px) is a weak reference, not a mismatch.
"""
import os
import tempfile
import unittest
from unittest import mock

import numpy as np

from helpers import Server, make_tenant, call, drive_flow
from server import face as FACE
from server import liveness as LV
from server import facetrack as FT
from server import deepfake as DEEPFAKE

cv2 = FACE.cv2


def _write_video(path, n=90, size=(320, 240)):
    wr = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), 30, (size[0], size[1]))
    assert wr.isOpened()
    for i in range(n):
        wr.write(np.full((size[1], size[0], 3), min(255, i * 2), np.uint8))
    wr.release()


class TestVideoFrames(unittest.TestCase):
    def test_samples_spread_across_full_duration(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "clip.mp4")
            _write_video(p, n=90)
            frames, info = FACE.video_frames(p, 30)
            self.assertEqual(info["total_frames"], 90)
            self.assertEqual(len(frames), 30)
            means = [float(f.mean()) for f in frames]
            self.assertLess(means[0], 10.0)          # starts at frame ~0
            self.assertGreater(means[-1], 160.0)     # ends near frame 89
            self.assertEqual(means, sorted(means))   # monotonic spread

    def test_unreadable_video_raises(self):
        with self.assertRaises(ValueError):
            FACE.video_frames("/nonexistent/nope.webm", 30)

    def test_video_frames_memoised_per_file(self):
        # One submit runs liveness + face track (+ deepfake) over
        # the same clip; the decode + rotation vote is paid once.
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "clip.mp4")
            _write_video(p, n=30)
            frames1, info1 = FACE.video_frames(p, 10)
            frames2, info2 = FACE.video_frames(p, 10)
            self.assertIs(frames1, frames2)
            self.assertEqual(info1, info2)

    @unittest.skipUnless(FACE.models_present(), "face models not fetched")
    def test_face_box_stats_none_on_blank(self):
        img = np.zeros((240, 320, 3), np.uint8)
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "blank.png")
            cv2.imwrite(p, img)
            self.assertIsNone(FACE.face_box_stats(p))


def _feat(face=True, strict=True, cx=0.5, cy=0.5, pix=10.0, sharp=None):
    return {"face": face, "strict": strict, "cx": cx, "cy": cy,
            "size": 0.3, "pix_std": pix, "sharp": sharp}


class TestAnalyseWeakPresence(unittest.TestCase):
    def test_weak_presence_is_not_absent_but_movement_needs_strict(self):
        # 3 strict + 6 anchored-weak + 1 none: present (0.9) but too
        # few strict sightings to judge the challenge movements.
        # (Centres/pixel noise drift slightly so the static-replay
        # leg — correctly — stays out of this test's way.)
        feats = ([_feat(True, True, cx=0.50 + 0.01 * i, pix=9.0 + i) for i in range(3)]
                 + [_feat(True, False, cx=0.53 + 0.01 * i, pix=12.0 + i) for i in range(6)]
                 + [_feat(False, False)])
        r = LV.analyse_features(feats, {"movements": ["left", "up"]})
        self.assertEqual(r["status"], "unclear", r)
        self.assertIn("liveness_challenge_incomplete", r["reason_codes"])
        self.assertEqual(r["findings"]["movement_basis"], "insufficient_strict_frames")
        self.assertAlmostEqual(r["findings"]["face_ratio"], 0.9)
        self.assertAlmostEqual(r["findings"]["strict_face_ratio"], 0.3)

    def test_movement_judged_on_strict_centres_passes(self):
        strict = [_feat(True, True, cx=0.5), _feat(True, True, cx=0.4),
                  _feat(True, True, cx=0.3), _feat(True, True, cx=0.3, cy=0.4),
                  _feat(True, True, cx=0.3, cy=0.3)]
        weak = [_feat(True, False, cx=0.9, cy=0.9)] * 5   # noisy weak boxes
        r = LV.analyse_features(strict + weak, {"movements": ["left", "up"]})
        self.assertEqual(r["status"], "pass", r)
        self.assertAlmostEqual(r["findings"]["strict_face_ratio"], 0.5)

    def test_sparse_faces_still_fail_absent(self):
        feats = [_feat(True, True)] + [_feat(True, False)] * 2 + [_feat(False, False)] * 7
        r = LV.analyse_features(feats, {"movements": ["left"]})
        self.assertEqual(r["status"], "fail", r)
        self.assertIn("liveness_face_absent", r["reason_codes"])

    def test_degraded_sparse_faces_are_unmeasurable_not_absent(self):
        # Owner session 17 (2026-10-29): the take's frames median
        # sharpness 6.0 — objectively degraded — and the detector
        # found a face in ~3% of frames. "Absent" is a fraud-grade
        # claim this evidence cannot carry; the verdict is unclear.
        feats = ([_feat(True, True, sharp=6.0)]
                 + [_feat(False, False, sharp=5.0)] * 9)
        r = LV.analyse_features(feats, {"movements": ["left", "up"]})
        self.assertEqual(r["status"], "unclear", r)
        self.assertIn("liveness_video_unmeasurable", r["reason_codes"])
        self.assertEqual(r["findings"]["frame_sharpness_median"], 5.0)

    def test_sharp_sparse_faces_still_fail_absent(self):
        # A SHARP faceless video (a wall, a ceiling) has measurable
        # detail and no face in it: absent stands.
        feats = ([_feat(True, True, sharp=120.0)]
                 + [_feat(False, False, sharp=140.0)] * 9)
        r = LV.analyse_features(feats, {"movements": ["left"]})
        self.assertEqual(r["status"], "fail", r)
        self.assertIn("liveness_face_absent", r["reason_codes"])
        self.assertEqual(r["findings"]["frame_sharpness_median"], 140.0)

    def test_vertical_movement_uses_vertical_threshold(self):
        # The session-15 shape: a genuine look-UP moves the centre
        # only ~0.029 (pitch rotates more than it translates), well
        # under the 0.045 horizontal bar but ~10x the detector jitter.
        # Centres: settle, turn left (cx -0.06), then look up.
        cs = ([(0.50, 0.50)] * 2
              + [(0.47, 0.49), (0.44, 0.49), (0.44, 0.49)]
              + [(0.44, 0.48), (0.44, 0.466), (0.44, 0.461), (0.44, 0.463)]
              + [(0.44, 0.47)] * 3)
        feats = [_feat(True, True, cx=x, cy=y, pix=9.0 + i) for i, (x, y) in enumerate(cs)]
        r = LV.analyse_features(feats, {"movements": ["left", "up"]})
        self.assertEqual(r["status"], "pass", r)
        self.assertEqual(r["findings"]["movements_made"], ["left", "up"])

    def test_tiny_vertical_dip_still_incomplete(self):
        cs = ([(0.50, 0.50)] * 2
              + [(0.47, 0.49), (0.44, 0.49), (0.44, 0.49)]
              + [(0.44, 0.485), (0.44, 0.48), (0.44, 0.482)]
              + [(0.44, 0.485)] * 3)
        feats = [_feat(True, True, cx=x, cy=y, pix=9.0 + i) for i, (x, y) in enumerate(cs)]
        r = LV.analyse_features(feats, {"movements": ["left", "up"]})
        self.assertEqual(r["status"], "unclear", r)
        self.assertEqual(r["findings"]["movements_made"], ["left"])

    def test_legacy_features_without_strict_flag_count_as_strict(self):
        feats = [{"face": True, "cx": 0.5 - 0.02 * i, "cy": 0.5, "size": 0.3,
                  "pix_std": 10.0} for i in range(6)]
        r = LV.analyse_features(feats, {"movements": ["left"]})
        self.assertAlmostEqual(r["findings"]["strict_face_ratio"],
                               r["findings"]["face_ratio"])


class TestExtractAnchoring(unittest.TestCase):
    """Anchoring semantics of the relaxed-presence rescue, with the
    detector mocked: a relaxed sighting counts only when anchored to
    a strict sighting through an unbroken chain of sightings."""

    def _run(self, strict_at, relaxed_at, n=8):
        frames = []
        for i in range(n):
            fr = np.zeros((48, 64, 3), np.uint8)
            fr[0, 0, 0] = i          # frame index in pixel 0
            frames.append(fr)
        row = [10, 10, 20, 20] + [0.0] * 10 + [0.9]

        def fake_largest(img, thr=FACE.PRODUCTION_THRESHOLD):
            idx = int(img[0, 0, 0])
            if thr >= FACE.PRODUCTION_THRESHOLD:
                return np.array(row, dtype=np.float32) if idx in strict_at else None
            return np.array(row, dtype=np.float32) if idx in relaxed_at else None

        with mock.patch.object(FACE, "video_frames",
                               return_value=(frames, {"total_frames": n, "rotation_degrees": 0})), \
             mock.patch.object(FACE, "largest_face", side_effect=fake_largest):
            return LV.extract_features("ignored.webm", max_frames=n)

    def test_chain_from_strict_anchor_counts(self):
        feats = self._run(strict_at={0}, relaxed_at={1, 2})
        self.assertTrue(feats[0]["face"] and feats[0]["strict"])
        self.assertTrue(feats[1]["face"] and not feats[1]["strict"])
        self.assertTrue(feats[2]["face"] and not feats[2]["strict"])
        self.assertFalse(feats[3]["face"])

    def test_gap_breaks_the_chain(self):
        feats = self._run(strict_at={0}, relaxed_at={2, 3})
        self.assertFalse(feats[2]["face"])
        self.assertFalse(feats[3]["face"])

    def test_no_strict_anchor_no_weak_counts(self):
        feats = self._run(strict_at=set(), relaxed_at={1, 2, 3})
        self.assertTrue(all(not f["face"] for f in feats))


AGG = [1.0] + [0.0] * 127


class TestWeakReferenceGate(unittest.TestCase):
    """App-level: a face-match fail against a weak printed reference
    is recorded unclear (document_portrait_weak_reference); against a
    strong reference the fail stands."""

    def _submit(self, srv, key, stats):
        ctx = drive_flow(srv, key, level=2)
        token = ctx["token"]
        st, ch = call(srv, "POST", "/v1/flow/liveness/challenge", {}, token=token)
        assert st == 201, ch
        import json
        st, r = __import__("helpers").multipart(
            srv, "/v1/flow/liveness",
            {"capture_meta": json.dumps({"method": "live_camera",
                                         "client_signals": {"track_label": "FaceTime HD Camera",
                                                            "motion": {"sensor_present": True, "samples": 140, "variance": 0.31}}})},
            {"video": ("liveness.webm", b"\x1a\x45\xdf\xa3" + b"\x00" * 64, "video/webm")}, token)
        assert st == 201, r
        ok = lambda *a, **k: {"status": "pass", "findings": {}, "reason_codes": []}
        track = lambda *a, **k: {"status": "pass", "findings": {"frames_with_face": 20},
                                 "reason_codes": [], "aggregate_embedding": AGG}
        with mock.patch.object(LV, "check_liveness", side_effect=ok), \
             mock.patch.object(DEEPFAKE, "check_deepfake", side_effect=ok), \
             mock.patch.object(FT, "check_face_track", side_effect=track), \
             mock.patch.object(FACE, "extract_face_feature", return_value=(AGG, object(), None)), \
             mock.patch.object(FACE, "cosine_similarity", return_value=0.10), \
             mock.patch.object(FACE, "face_box_stats", return_value=stats):
            st, view = call(srv, "POST", "/v1/flow/submit", {}, token=token, timeout=60)
        assert st == 200, view
        return view

    def test_weak_reference_fail_becomes_unclear(self):
        # The CHECK stops asserting a mismatch it cannot support:
        # unclear + the weak-reference reason, and the risk engine
        # charges it as an unclear (8 pts), not a mismatch (45). The
        # session outcome follows the engine's standing standard-path
        # rule — an inconclusive required check is rejected with
        # rescan guidance, never parked for review — so the status is
        # rejected, but for the honest reason.
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            view = self._submit(srv, key, (56.0, 0.055, 0.909))
            self.assertEqual(view["checks_summary"]["face_match"], "unclear", view)
            self.assertIn("document_portrait_weak_reference", view["decision"]["reason_codes"], view)
            self.assertNotIn("face_mismatch", view["decision"]["reason_codes"], view)
            self.assertEqual(view["status"], "rejected", view)
            fm_risk = [c for c in view["decision"]["risk_contributions"]
                       if c["source"] == "face_match"]
            self.assertTrue(fm_risk and fm_risk[0]["points"] < 45, view)

    def test_strong_reference_fail_stands(self):
        with Server() as srv:
            _, key, _ = make_tenant(srv)
            view = self._submit(srv, key, (150.0, 0.20, 0.95))
            self.assertEqual(view["checks_summary"]["face_match"], "fail", view)
            self.assertIn("face_mismatch", view["decision"]["reason_codes"], view)
            self.assertEqual(view["status"], "rejected", view)


if __name__ == "__main__":
    unittest.main()

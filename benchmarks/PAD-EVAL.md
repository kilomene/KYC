# PAD Evaluation — liveness (WS8 readiness)

Metrics follow ISO/IEC 30107-3 definitions: **APCER** = attack presentations incorrectly passed; **BPCER** = bona-fide presentations incorrectly rejected; **ACER** = their mean. For this platform 'unclear' is NOT a pass (it routes to review), so an attack only succeeds on status 'pass'; BPCER is reported split (reject = 'fail' only; nonpass = fail+unclear).

## Feature-level synthetic battery (production decision logic)

40 trials per class, deterministic seed; bona-fide class includes a noisy variant (heavy jitter, 90% face presence). Counts: {"bona_fide": 80, "attack_static_photo": 40, "attack_face_absent": 40, "attack_partial_replay": 40}

- APCER (overall): **0.0%**
- APCER (attack_face_absent): 0.0%
- APCER (attack_partial_replay): 0.0%
- APCER (attack_static_photo): 0.0%
- BPCER (reject): **0.0%** · BPCER (nonpass): 2.5%
- ACER: **0.0%**

## Video corpus (end-to-end)

No corpus supplied. A video-level evaluation needs recorded bona-fide performances and attack artefacts (printed photo, screen replay, mask) — none exist yet, so NO video-level metric is claimed.

## What this is and is not

- This harness measures the production decision logic on synthetic features, reproducibly. It is a READINESS step.
- It is **not** an iBeta / ISO 30107-3 laboratory certification: that requires an accredited lab, physical attack artefacts and real subjects. No PAD certification is claimed anywhere until a lab report exists.
- The WS2 face-match operating point (EER 1.07% @ 0.288 on the LFW protocol; FAR 0.10% / FRR 2.00% at the shipped 0.363 threshold) is the biometric claim backed by measurement; this document adds the liveness-logic numbers beside it.

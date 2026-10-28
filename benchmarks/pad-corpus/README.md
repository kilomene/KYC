# PAD video corpus — recording protocol (WS8 follow-on)

The PAD harness (`scripts/pad_eval.py --corpus DIR`) scores
recorded videos end-to-end. This protocol produces a corpus a
laboratory-style evaluation can stand on. **Recordings contain
real people's faces: they are biometric data. The corpus lives
ONLY under `benchmarks/corpus/` (excluded from the repo push),
is never committed, and every subject signs the consent note
below before recording.**

## Layout (what the harness reads)

```
benchmarks/corpus/
  bona_fide/            subject performs the issued challenge
    subj01_take1.mp4
    subj01_take1.challenge.json   {"movements": ["left", "up"]}
  attack_printed_photo/ a printed photo of the subject, held/waved
  attack_screen_replay/ the subject's selfie/liveness video played
                        on a phone/tablet screen to the camera
  attack_video_replay/  a recorded liveness attempt replayed
```

Every video needs its `<name>.challenge.json` beside it with the
movements that were issued for that take.

## Bona-fide protocol

1. Consenting subject, phone at arm's length, normal indoor
   light. Issue a fresh challenge from the live flow (or
   `liveness.new_challenge()`), show it to the subject.
2. Record ~9s at the best quality the device offers: face in
   frame throughout, movements performed in order, slowly.
3. Minimum useful corpus: 10 subjects × 2 takes. Record
   failures honestly — a bona-fide take the subject botched is
   still bona-fide data (it informs BPCER, the genuine-user
   cost).

## Attack protocol (PAI — presentation attack instruments)

- **Printed photo**: colour print of the subject's portrait at
  life size; present it (a) flat and still, (b) with slight
  movement. The static detector must fail both.
- **Screen replay**: display the subject's photo AND a recorded
  liveness video on a second device, full-screen, brightness
  high; present to the camera for the full window.
- **Video replay**: replay a previous bona-fide take — it
  performs the WRONG challenge for the new session, and its
  pixel/motion statistics differ from a live capture.
- Minimum: 5 subjects × 2 takes per attack kind.

## Scoring

```
python3 scripts/pad_eval.py --corpus benchmarks/corpus
```

Writes benchmarks/PAD-EVAL.md (video-corpus section). Report
APCER per attack kind, BPCER (split reject/nonpass), ACER —
and state the corpus size beside every number. A small corpus
produces indicative numbers, not a certification; the iBeta /
ISO 30107-3 laboratory path (accredited lab, their artefacts,
their subjects) remains the only route to a PAD claim, per
docs/SOC2-READINESS.md.

## Consent note (per subject, kept with the corpus, offline)

"I agree to be recorded for liveness-evaluation purposes. The
recordings stay on the operator's machine, are never published
or committed to any repository, are used only to measure the
verification system's attack resistance, and are deleted on my
request." — name, signature, date.

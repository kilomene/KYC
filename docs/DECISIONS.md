# KYC — Decisions

*The build does not guess these. Answered decisions are facts, with dates.*

## SETTLED — 2026-10-26, by the owner: "Approve it — go with the recommendations and start Phase 1"

### D1. Brand home — SETTLED: Nova Inc product
KYC is a **Nova Inc** product. It inherits the Nova Inc brand lock
unchanged (company name; shared company mail sends under the display name
"Nova Inc"; ecosystem listing as a Nova Inc product). Payments and
Exchange are natural first tenants.

### D2. First customer — SETTLED: internal first (explained 2026-10-26)
"Internal first" means: the **first businesses to use KYC are our own
Nova Inc platforms** (Nova Payments, Agent Exchange) verifying their own
users. Outside companies cannot sign up as tenants yet in Phase 1.
"External in Phase 2" means: once it is proven on our own platforms,
outside businesses can sign up, get API keys, and pay to verify their
users. Same product, same build — the only difference is *who is allowed
to be a tenant, and when*. (Owner asked what this meant on 2026-10-26;
explanation given, he can flip it to external-from-launch with one word.)

### D3. Launch coverage — SETTLED, EXPANDED by the owner 2026-10-26
Owner corrected the original 3-country proposal: coverage is **worldwide
in scope, not three countries**. Named by the owner: **Nigeria, United
Kingdom, United States, Canada, Australia, Germany, Ghana**, plus more
African countries, more Asian countries, and countries across the world.
Filled in by us (owner can strike/add any): Africa — Ghana, Kenya, South
Africa; Asia — India, Philippines, Singapore, United Arab Emirates;
Europe — France, Netherlands, Ireland; plus the named set above.
How this works honestly: **passports are accepted from every country in
the launch list (and the MRZ format is a worldwide standard)**, while
driver's licence / national ID support starts with the named countries
and expands country by country with tests. Only tested documents get
listed as supported.

### D4. Stack — SETTLED, clarified by the owner 2026-10-26
**Built local-first. Not on Supabase and not on Cloudflare yet.**
Phase 1 runs on our own machine (local data + local storage behind the
API contract in docs/API.md). The normal production home **will be
Cloudflare** (see D6 for which account) — hosting moves there when the
owner is ready to deploy; it is not hosted on this computer as a final
state. The data layer is kept portable so that move is a deployment
step, not a rewrite.

*Implementation status (WS0 audit, 2026-10-26): the service IS deployed
— live at kyc.novamail.store, running on the Nova origin service and
reached through a Cloudflare tunnel on the owner's account (D6). The
final Cloudflare-native hosting move remains Phase 4 WS5.*

### D5. Face match / liveness (Phase 2) — SETTLED
Plug an evaluated provider first behind our check interface; evaluate own
models in parallel against the same acceptance tests; swap only on
evidence. No provider named until the evaluation runs.

*Implementation status (WS0 audit, 2026-10-26): Phase 2 shipped the
own-model track first (YuNet + SFace, local) behind the check interface;
no external provider has been evaluated yet. The provider-adapter
benchmark this decision calls for is Phase 4 WS2 — the divergence is
recorded here rather than silently rewritten.*

### D6. Domain & Cloudflare account — SETTLED, clarified 2026-10-26
**`kyc.novamail.store`** (subdomain only, per the owner's root-domain
rule), created when Phase 1 is ready to deploy — not before.
The domain lives on **the owner's existing Cloudflare account — the one
he already gave access to and used to log in for novamail.store** — not
a separate new account. If a different Cloudflare account is ever to be
used for KYC, the owner will provide that account's API token himself at
that time; until then, the existing account is the one.

### D7. Pricing — SETTLED (shape; prices deferred on purpose)
Per-verification by level, free sandbox, no charge for expired-untouched
or our-error sessions. Actual prices are set once Phase 1 check costs are
measured — pricing before measuring would be guessing.

## STILL OPEN

### D8. Repo visibility
Repo is public now per the owner's instruction and may go private later.
The blueprint is safe public. **With Phase 1 code now landing, the owner
should say if he wants it flipped private** — until he does, it stays
public per his original instruction; no secrets, keys, or provider
credentials ever land in the repo either way.

### D9. NIN slip exception — upload + typed-number tally (owner's order, 2026-10-26)
The live-camera-only rule stands for every document type **except the
Nigerian NIN slip**. The slip is laminated paper and defeats live
scanning (glare, bow, weak borders — measured repeatedly on the
owner's own slip). For `nin_slip` only:

- the user **uploads** a photo of the slip (no live document scan);
- the user **types their NIN** (11 digits) — a claim, never an
  identity source: the slip remains the source of truth for every
  field, the typed number included;
- the decision carries a `number_tally` check: the number read off
  the slip must equal the typed number. Mismatch — or no typed
  number at all — is a hard fail (`nin_number_mismatch`,
  `nin_number_not_provided`) and rejects automatically;
- the **live selfie + liveness are unchanged**, and the portrait
  printed on the slip is face-matched against the live selfie by the
  ordinary pipeline;
- all server checks (framing, classification, forgery/screen,
  extraction, consistency) run on the upload exactly as on a scan.

Scope enforcement is mechanical, not conventional: the API refuses a
typed number for any other kind (422), the claim-correction endpoint
refuses non-slip documents (422), and the hosted flow renders the
upload panel only when the selected type is `nin_slip`.

**Orientation + read-recovery addendum (owner's order, same evening —
"it can be portrait, it can be in landscape no matter how"):** his own
first upload was a portrait photo holding the landscape slip sideways,
and the reader — which assumed the document's long axis horizontal —
read a scrambled mosaic and no number at all. Two platform-level
fixes, proven on his actual uploaded photo before shipping:

- **Orientation normalization at ingest** (uploaded images only):
  the stored artifact is the document upright, so every downstream
  check consumes it as printed. The decider is two-layered, because
  each layer is blind where the other sees: tesseract's orientation
  detection (OSD) names the rotation outright on clean documents
  (confidence ≥2.5) but is blind on noisy laminated photos (the
  owner's slip: 0.15); there, a four-rotation OCR-score competition
  decides (bonused when framing finds the document quad inside the
  type's aspect range), and a rotation is applied only when it beats
  the as-is read by ≥1.5× — an upright image is never gratuitously
  rotated. The correction is recorded in the document's capture
  metadata.
- **Corroborated digit-zone recovery** (field extraction): when the
  number resolves missing or format-invalid for a fixed-length digit
  format, a dedicated pass crops the number's own location from the
  ORIGINAL image (located by the field's LABEL — large bold print
  that survives at resolutions where the digits do not — or by the
  primary read's digit word boxes, mapped through the framing quad —
  never the double-resampled warp) and votes across independent
  variants (scales × {plain, Otsu, median+Otsu} × two page modes;
  reads longer than the number contribute their windows, junk bled
  in from neighbouring columns included). A candidate is adopted
  only on a decisive vote (≥3 reads, ≥2× the runner-up) that also
  agrees with the primary partial read on ≥75% of the overlapping
  prefix. On the owner's slip this recovered the full 11 digits the
  general passes had truncated at 8, where they cross the watermark.
  The same session's LOW-resolution rendition (647px — the phone
  handed over a reduced copy of the same photo) measured the honest
  floor of this discipline: the recovery's vote split 9–6 between two
  readings differing in exactly one digit, no decisive winner
  existed, and nothing was adopted — an unreadable digit stays
  unreadable rather than becoming a wrong number that the tally
  would reject.
- **Tiled word fallback** (vision): when the full-page word pass
  yields <60 words — its near-blind zone on small print — the
  reading image is re-read in overlapping quadrant tiles and the
  word sets merged, duplicates resolved by box overlap in favour of
  the higher-confidence read. On the owner's low-resolution upload
  this took the word yield from 47 (no labels, no values) to a set
  carrying 'NIN:' at conf 96, the surname clean, and the given name —
  the fields the read-back needed.
- **Lossless storage of corrected uploads**: a rotated upload is
  stored as PNG, never a second lossy JPEG generation; the flow also
  warns before upload when the picked copy is small (<1500px long
  side) and, on an incomplete slip read, directs the user to the
  ORIGINAL photo rather than a screenshot or forwarded copy.
- **Portrait orientation decider** (third in the chain, after OSD
  and the OCR-score competition): tesseract's page segmentation
  auto-rotates sideways text internally, which can erase the score
  evidence entirely (a sideways slip on a table measured 27.9k as-is
  vs 27.8k corrected — a tie neither decider may break). When the
  document type carries a printed portrait, YuNet is run on the
  four rotations of the document region: a face is detectable only
  upright (landmark order eyes → nose → mouth confirms), so a
  single decisive qualifying rotation names the correction. Proven
  on composed scenes at all four rotations, silent on faceless
  images, and on the owner's real sideways photo it independently
  returns the same 270° the score path chose.

# ADR: privacy boundary Company Card v2 / public H2

Status: accepted for implementation planning only

Scope: H2/v3 only; H1 and v1/v2 remain unchanged

## Decision

Public H2 is default-deny. Raw provider payloads, credentials, contact data,
private identifiers, raw natural-person names, internal case keys, HMAC tokens,
URLs containing identifiers and AI raw responses are prohibited from DTO, SSR,
embedded state, logs, telemetry and public artifacts. A closed public DTO and
recursive allowlist are required before publication.

H1 POST/publication lifecycle remains its existing one. H2 uses a separate
immutable presentation assignment and pin lifecycle; it is never selected by a
client request field, cookie, frontend flag or URL guess. H2 GET/SSR is
read-only: it must not call a provider, Gateway or AI, create a report/job/pin,
or mutate a database.

## Private opponent identity and HMAC

Private input is NFC-normalized, Unicode whitespace-trimmed and rejected when
empty or control-containing. A verified INN has priority over a verified OGRN;
conflict means distinct values of one kind or an invalid party association.
Names, identifier length and provider arrival order never resolve identity.

```text
OpponentEntityClassV1 = "masked_natural" | "masked_unknown"
SourceRoleCollectionV1 =
  "plaintiffs" | "respondents" | "applicants" | "creditors" |
  "creditors_current_payments" | "debtors" |
  "interested_persons" | "third_parties" | "others"

OpponentHmacIdentityV1:
  identity_version: literal "OpponentHmacIdentityV1"
  domain: literal "company-card-v2:opponent:v1"
  report_id: lowercase UUID
  entity_class: OpponentEntityClassV1
  identifier: StableOpponentIdentifierV1 | CasePositionIdentifierV1

StableOpponentIdentifierV1:
  kind: "inn" | "ogrn"
  value: exact normalized verified source value

CasePositionIdentifierV1:
  kind: literal "case_position"
  case_key: NFC nonblank private case key
  source_role_collection: SourceRoleCollectionV1
  zero_based_ordinal: integer >= 0
```

Unknown keys are forbidden. The private token is full 32-byte HMAC-SHA-256,
encoded as 64 lowercase hex, over
`UTF-8(CJSON_company_public_h2_cjson_v1(OpponentHmacIdentityV1))`. The worker
resolves a secret of at least 32 bytes using nonsecret `mask_key_id` matching
`[a-z][a-z0-9_]{0,31}`. Delimiter concatenation, implicit encoding, base64,
token truncation, plain SHA, name hash, random ordinal and unkeyed fallback are
forbidden. Secret, source identifier, raw natural name and private token are
not persisted in public facts or emitted to any public sink.

## Exact public identifiers

```text
CasePublicOrderIdentityV1:
  identity_version: literal "CasePublicOrderIdentityV1"
  report_id: lowercase UUID
  case_key: NFC nonblank private case key

OpponentPublicOrderIdentityV1:
  identity_version: literal "OpponentPublicOrderIdentityV1"
  report_id: lowercase UUID
  display_kind: "legal" | "state" | "masked_natural" | "masked_unknown"
  private_identity_kind:
    "stable_inn" | "stable_ogrn" | "masked_hmac" | "case_position_hmac"
  private_identity_value: exact private identifier or full 64-hex HMAC
```

Cases sort by UTF-8 CJSON `CasePublicOrderIdentityV1` bytes, receive indices
`1..1000`, then emit `case_` plus six zero-padded digits. Opponents sort by
display-kind rank `legal,state,masked_natural,masked_unknown`, then UTF-8 CJSON
`OpponentPublicOrderIdentityV1` bytes, receive indices `1..20000`, then emit
`opponent_` plus six zero-padded digits. Exact patterns are `case_[0-9]{6}` and
`opponent_[0-9]{6}`; zero, overflow or duplicate index invalidates projection.
No public ID embeds a provider key, HMAC material or source ordinal.

The scanner-safe golden uses the 43-byte ASCII key
`iteration-nineteen-hmac-vector-key-material` and exact CJSON:

```text
{"domain":"company-card-v2:opponent:v1","entity_class":"masked_unknown","identifier":{"case_key":"case-alpha","kind":"case_position","source_role_collection":"respondents","zero_based_ordinal":0},"identity_version":"OpponentHmacIdentityV1","report_id":"a1b2c3d4-e5f6-4a7b-8c9d-a1b2c3d4e5f6"}
```

Expected lowercase HMAC-SHA-256:
`21d8c54c7052e3112c6c748f3ae5fa545c121d23b37ca02561b2978b9f767220`.
The case-order golden maps `case-alpha,case-beta,case-zeta` to
`case_000001,case_000002,case_000003`; opponent-order maps to
`opponent_000001,opponent_000002`. Its same report UUID is
`a1b2c3d4-e5f6-4a7b-8c9d-a1b2c3d4e5f6`; both identities use
`display_kind="masked_unknown"` and `private_identity_kind="masked_hmac"`.
The exact synthetic `private_identity_value` strings are
`aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa` and
`bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb`; their
exact CJSON bytes are:

```text
{"display_kind":"masked_unknown","identity_version":"OpponentPublicOrderIdentityV1","private_identity_kind":"masked_hmac","private_identity_value":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","report_id":"a1b2c3d4-e5f6-4a7b-8c9d-a1b2c3d4e5f6"}
{"display_kind":"masked_unknown","identity_version":"OpponentPublicOrderIdentityV1","private_identity_kind":"masked_hmac","private_identity_value":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","report_id":"a1b2c3d4-e5f6-4a7b-8c9d-a1b2c3d4e5f6"}
```

They order a then b. Private values never appear in the DTO.

## Arbitration calendar and safe rendering

Collection completeness is independent of calendar completeness. Persisted
`ArbitrationCollectionV1`, derived `ArbitrationCalendarFactsV1` (part of
`chart_facts_hash`) and `PublicArbitrationSummary` carry separate
`collection_complete`, `calendar_complete`, `calendar_scope` limited to
`unverified|all_time|bounded_interval`, `calendar_evidence_version`,
calendar/observed bounds, `unknown_year_count` and `zero_years_proven`.
Collection completeness alone does not assert a calendar absence or create a
synthetic zero bucket.

Court labels are safe-normalized, unique and Unicode-scalar sorted before the
first 10. Opponents are capped at 20 only after exact identity ordering. Their
overflow limitations are explicit. Natural/unknown names are never aliases;
legal/state aliases require the separately verified exact identifier policy.

## AI and universal deterministic fallback

The AI envelope excludes company identity, address, manager/owner values,
case/party identifiers, names, amounts, currencies and raw values. Automatic
schema/evidence/unit/privacy/policy validation chooses an immutable fallback
for invalid, ambiguous, missing or stale artifacts; there is no human
moderation, repair call or second AI validator in this contract.

`fallback_catalog_version` is non-null in `GenerationIdentityV1` and thus in
`generation_key`. Catalog `company_card_h2_fallback_catalog_v1` has exactly one
immutable, universal entry `fallback_profile_any_v1`: its NFC-normalized output
is the exact 691-Unicode-scalar literal in the normative spec. It accepts no
facts, limitations, coverage or profile input and performs no padding or
truncation. A new catalog version creates a new immutable generation.

```text
FallbackIdentityV1:
  identity_version: literal "FallbackIdentityV1"
  generation_key: 64 lowercase hex
  fallback_catalog_version: literal "company_card_h2_fallback_catalog_v1"
  fallback_profile_id: literal "fallback_profile_any_v1"
  renderer_version: literal "company_card_h2_fallback_renderer_v1"
  rendered_output_bytes_sha256: 64 lowercase hex
```

`fallback_identity` is SHA-256 over the UTF-8 CJSON of this exact named object.
Missing or invalid fallback binding fails publication closed.

## Monetary source transport

`company_card_source_decimal_v1` applies to every v3 monetary source leaf:
finance, arbitration amount and charter-capital amount. Ordinary `response.json()`
coercion does not prove a source number lexeme. The three independent gates
`finance_decimal_transport`, `arbitration_decimal_transport` and
`charter_capital_decimal_transport` therefore remain `UNVERIFIED/BLOCKED`
until lexical ingestion and finite/precision negative tests pass. A4 amount
display/geometry and public charter capital stay blocked; H1/v1/v2 are unchanged.

## SSR, telemetry and verification

H2 has one strict, script-safe embedded DTO and a per-response nonce. Failure
to parse, validate path/schema or verify digest preserves SSR facts and blocks
mount, refetch, lifecycle, provider, AI and telemetry work. Dedicated H2 shell
does not include Webvisor, session replay or third-party analytics. Telemetry
is default-off and may use only closed aggregate enums, never URL, DOM text,
DTO, identifier, narrative, amount or private data.

Required tests cover recursive denylist/allowlist, every public sink, missing
or rotated key failure, HMAC/CJSON/full-digest and ordering goldens, calendar
versus collection completeness, synthetic-zero prohibition, universal
691-scalar fallback identity, one-state/CSP/XSS behavior and no-read-side
effects.

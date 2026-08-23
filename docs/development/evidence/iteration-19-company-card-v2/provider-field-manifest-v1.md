# Provider field manifest v1 - Company Card v2

Artifact ID: `company_card_v2_provider_field_manifest_v1`

Public contract target: `company_public_h2_v1`

Evidence date: `2026-08-23`

Status: `reviewed_local_evidence_only`

Live-stage authorization: `not_granted`

## 1. Purpose and decision rule

This artifact binds every provider-backed Company Card v2 content field to an
observed source shape, gate state, public transformation, and deterministic
missing behavior. It does not activate runtime behavior. A path marked
`NOT_VERIFIED` is a final instruction to omit the field and expose the linked
limitation; it is not permission to select a plausible leaf at implementation
time.

The artifact uses the gate vocabularies fixed by iteration 19:

- `schema_gate`: `unverified | verified | rejected`;
- `semantic_gate`: `unverified | verified | rejected`;
- `privacy_gate`: `unreviewed | approved_transform | prohibited`;
- `operational_gate`: `disabled | approved`;
- `implementation_state`: `blocked | planned | implemented`.

A public field is eligible only when all required gates are satisfied and its
feature gate is enabled. A feature flag cannot override evidence.

## 2. Provenance and evidence classes

No network request, production database access, paid AI call, report refresh,
or backfill was performed for this artifact.

| Evidence ID | Source | Permitted conclusion | Explicit limitation |
|---|---|---|---|
| `R-CODE-20260823` | Current normalizers and models at base `c3805dd1fbb8cdac38b1aa315e1f1e94597e7537` | Parser behavior and currently retained fields | Not a vendor schema or semantic guarantee |
| `R-FIX-20260823` | Tracked synthetic fixtures under `services/product_api/tests_unit/fixtures/datanewton/` | Parser-shape expectations only | Synthetic values do not prove production availability, scale, scope, dates, or identity semantics |
| `O-SHAPE-20260822` | Owner-supplied ignored local evidence batch, inspected read-only | Observed key/type/cardinality for one local sample | Not tracked, not a vendor contract, not unit proof, and not proof of multi-page behavior |
| `UX-SPEC-20260822` | Local chart technical specification and page/CTA references | Desired view fields, formulas, order, and presentation states | Not provider evidence |
| `H1-EVIDENCE-V1` | Existing tracked H1 evidence registry | Reuse of already approved core identity/address behavior | Does not activate dormant H2 fields |

No value, company or party name, identifier, case number, amount, contact,
provider free text, request header, or identifier-bearing URL from local owner
evidence is reproduced here.

## 3. Locator notation

`$.balances..{code="1210"}.sum["<year>"]` means the deterministic recursive
locator already used by the finance normalizer: within the named form, find an
object whose exact sibling `code` is the literal code and read that object's
exact sibling `sum` member for the exact year key. It is not a claim that the
vendor promises one fixed array position. Conflicting matches remain
`conflict`; the builder never chooses one arbitrarily.

For compact table rows, `R-CODE`, `R-FIX`, `O-SHAPE`, and `H1-EVIDENCE-V1`
refer exactly to `R-CODE-20260823`, `R-FIX-20260823`,
`O-SHAPE-20260822`, and `H1-EVIDENCE-V1` from section 2. `I20`, `I23`, and
`I24` identify future implementation ownership, not current implementation.

## 4. Current capability gate summary

| Capability | Schema | Semantics | Privacy | Operations | Current public decision |
|---|---|---|---|---|---|
| Core identity and approved address subset | verified | verified under existing H1 contract | approved_transform | approved | Reuse exact H1-safe transformation |
| Status and effective date | unverified | unverified | approved_transform | disabled | Hidden with field limitation |
| Legal form, capital, tax modes, activities, owners, employees, tax authority | unverified | unverified | mixed; see rows | disabled | Hidden with field limitation |
| Manager safe composition | verified observed shape | unverified provider scope | approved_transform | disabled | Hidden until semantic gate closes |
| Contacts and personal identifiers | irrelevant to publication | irrelevant | prohibited | disabled | Not requested and never emitted |
| Finance series values | verified parser shape | unit unverified | approved_transform | disabled for H2 money | No ruble label, scale, or monetary Chart Facts |
| Arbitration single-page shape | verified observed shape | full envelope semantics unverified | transformation pending | disabled for H2 | No collection or chart publication |
| Arbitration outcome/entity type/currency/link semantics | unverified | unverified | transformation pending | disabled | Corresponding public leaves omitted |

## 5. Counterparty fields

| Field ID | Dataset / endpoint | Exact path or `NOT_VERIFIED` | JSON type; cardinality; nullability | Subject scope | Effective/reference date | Identity semantics | Observed source/date | Schema | Semantic | Privacy | Operational | Public transformation | Missing/conflict behavior | Future owner |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `identity.legal_full_name` | counterparty / `GET /v1/counterparty` | `$.company.company_names.full_name` | string; 0..1; nullable | target organization | report source receipt only | exact target record after target-INN equality | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified | verified under H1 core | approved_transform | approved | NFC/trim, bounded public company name | missing => identity ineligible; conflicting target => fail closed | I20 |
| `identity.short_name` | counterparty | `$.company.company_names.short_name` | string; 0..1; nullable | target organization | report source receipt only | same target record | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified | verified under H1 core | approved_transform | approved | NFC/trim or null | missing => null; never synthesize abbreviation | I20 |
| `identity.display_name` | counterparty | closed precedence over `$.company.company_names.short_name` and `$.company.company_names.full_name` | derived string; exactly 1 | target organization | report source receipt only | same exact target record | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified | verified under H1 core | approved_transform | approved | first valid allowlisted name by closed precedence | both missing/conflicting => identity ineligible; never invent a label | I20 |
| `identity.inn` | counterparty | `$.inn`, fallback `$.company.inn` | string; exactly one valid target required | target organization | identity, not temporal | normalized value must exactly equal requested target | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified | verified under H1 identity | approved_transform | approved | normalized public company INN only | absent/mismatch/conflict => report not eligible | I20 |
| `identity.ogrn` | counterparty | `$.ogrn`, fallback `$.company.ogrn` | string; 0..1; nullable | target organization | identity, not temporal | exact normalized target attribute; not an INN substitute | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified | verified under H1 core | approved_transform | approved | normalized company OGRN/OGRNIP or null | conflicting root/nested values => null plus limitation | I20 |
| `identity.kpp` | counterparty | `$.company.kpp` | string; 0..1; nullable | target organization | source receipt only | company requisite; never used to match cases | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified | verified under H1 core | approved_transform | approved | normalized KPP or null | invalid/missing => null | I20 |
| `identity.registration_date` | counterparty | `$.company.registration_date` | ISO-date string; 0..1; nullable | target organization | date carried by field | none beyond target binding | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified | verified under H1 core | approved_transform | approved | validated ISO date | malformed/missing => null plus limitation when material | I20 |
| `identity.dissolution_date` | counterparty | `$.company.dissolved_date` | ISO-date string; 0..1; nullable | target organization | date carried by field | does not independently prove current status | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified | verified as date only | approved_transform | approved | validated ISO date | malformed/missing => null; never infer active/inactive | I20 |
| `requisites.address.display` | counterparty | `$.company.address.line_address` | string; 0..1; nullable | target organization | source receipt only | exact address block of target | `R-CODE`, `R-FIX`, `O-SHAPE`, `H1-EVIDENCE-V1` / 2026-08-23 | verified | verified under approved H1 address subset | approved_transform | approved | bounded public address string | missing/invalid requested block => null plus coverage limitation | I20 |
| `requisites.address.region` | counterparty | `$.company.address.region` | string; 0..1; nullable | target organization | source receipt only | same address block | `R-CODE`, `R-FIX`, `O-SHAPE`, `H1-EVIDENCE-V1` / 2026-08-23 | verified | verified under H1 subset | approved_transform | approved | bounded region label | missing => null; never derive from address text | I20 |
| `requisites.address.is_inaccuracy` | counterparty | `$.company.address.is_inaccuracy` | boolean; 0..1; nullable | target organization | source receipt only; no effective-date claim | same address block | `R-CODE`, `R-FIX`, `O-SHAPE`, `H1-EVIDENCE-V1` / 2026-08-23 | verified | verified only as exact boolean | approved_transform | approved | exact boolean or null | missing => unknown, not false | I20 |
| `identity.status.state` | counterparty | `$.company.status.active_status` | boolean candidate; 0..1; nullable | target organization | `NOT_VERIFIED` | candidate status only; no current-time inference | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed shape | unverified catalog/scope/date | approved_transform | disabled | hidden; `counterparty_status_gate_closed` | absent/conflict => null and limitation | I20 + future evidence |
| `identity.status.code` | counterparty | `$.company.status.code_egr` | string candidate; 0..1; nullable | target organization | `NOT_VERIFIED` | closed status catalog not bound | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed shape | unverified | approved_transform | disabled | hidden with same status limitation | unknown code never passed through | I20 + future evidence |
| `identity.status.label` | counterparty | `$.company.status.status_rus_short`, candidate fallback `$.company.status.status_egr` | string candidate; 0..1; nullable | target organization | `NOT_VERIFIED` | provider free text cannot define public state | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed shape | unverified closed mapping | approved_transform | disabled | hidden until mapped through closed catalog | missing/unknown => null; raw text never emitted | I20 + future evidence |
| `identity.status.effective_date` | counterparty | `NOT_VERIFIED` | unknown; 0..1; nullable | target organization | exact date semantics required | must refer to the chosen status fact | candidate leaves observed but not bound / 2026-08-23 | unverified | unverified | approved_transform | disabled | null plus `counterparty_status_effective_date_unverified` | never substitute report, receipt, registration, or dissolution date | Future evidence |
| `requisites.legal_form` | counterparty | `$.company.opf` | string candidate; 0..1; nullable | target organization | source receipt only | organization form requires closed code/label mapping | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed scalar | unverified dictionary | approved_transform | disabled | null plus `legal_form_dictionary_unverified` | raw label never passed through | I20 + future evidence |
| `requisites.charter_capital.amount` | counterparty | `$.company.charter_capital` | number/string Decimal candidate; 0..1; nullable | target organization | `NOT_VERIFIED` reference date | target organization fact | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified parser shape | unverified scope/unit | approved_transform | disabled | hidden with `charter_capital_unit_unverified` | missing/conflict => null; not zero | Future evidence |
| `requisites.charter_capital.decimal_transport` | counterparty response bytes | `NOT_VERIFIED`; current `response.json()` is post-coercion only | source number lexeme or JSON string required by `company_card_source_decimal_v1` | charter-capital amount only | exact source amount | binds lexical value before Decimal conversion | `R-CODE` / 2026-08-23 | unverified | unverified | approved_transform | disabled | charter capital blocked | float/post-coercion input => `decimal_transport_lossy`; no fallback | I20 lexical-ingestion evidence |
| `requisites.charter_capital.unit` | counterparty | `NOT_VERIFIED` | unknown; 0..1; nullable | target organization | same as capital amount | must bind exact amount scale/currency | no verified source / 2026-08-23 | unverified | unverified | approved_transform | disabled | no symbol/scaling | finance-unit policy must not be reused | Future evidence |
| `requisites.tax_modes[*]` | counterparty | boolean candidates under `$.company.tax_mode_info.{common_mode,usn_sign,ausn_sign,envd_sign,eshn_sign,npd_sign,psn_sign,srp_sign}`; date candidate `$.company.tax_mode_info.publication_date` | object source; 0..8 true modes; nullable leaves | target organization | publication/effective scope unverified | closed mode ID/label required | `R-CODE`, `R-FIX` / 2026-08-23 | verified observed root/leaves | unverified boolean scope and date | approved_transform | disabled | empty public list plus `tax_modes_semantics_unverified` | absent is unknown/not requested, never false; conflicting flags => field conflict | I20 + future evidence |
| `requisites.primary_activity` | counterparty | `NOT_VERIFIED` within observed root `$.company.okveds` | unknown leaf object; 0..1; nullable | target organization | exact effective date required or null by contract | exact code, label, and primary flag required | empty synthetic root only / 2026-08-23 | unverified | unverified | approved_transform | disabled | null plus `okved_leaf_schema_unverified` | never infer primary from order | Future evidence |
| `requisites.additional_activities[*]` | counterparty | `NOT_VERIFIED` within observed root `$.company.okveds` | unknown leaf object; 0..20 public cap | target organization | exact effective date required or null by contract | exact code/label/primary flag | empty synthetic root only / 2026-08-23 | unverified | unverified | approved_transform | disabled | empty plus same limitation | no arbitrary truncation before validation/sort | Future evidence |
| `requisites.activities[*].code` | counterparty | `NOT_VERIFIED` | unknown scalar; exactly 1 per eligible activity | one activity of target | activity effective date separate | exact OKVED code, not parsed from label | no approved nonempty leaf / 2026-08-23 | unverified | unverified | approved_transform | disabled | hidden until exact leaf bind | missing code => activity row ineligible | Future evidence |
| `requisites.activities[*].label` | counterparty | `NOT_VERIFIED` | unknown scalar; exactly 1 per eligible activity | one activity of target | activity effective date separate | label bound to exact code | no approved nonempty leaf / 2026-08-23 | unverified | unverified | approved_transform | disabled | bounded safe label after catalog/scope gate | raw unknown label not emitted | Future evidence |
| `requisites.activities[*].is_primary` | counterparty | `NOT_VERIFIED` | unknown boolean; exactly 1 per eligible activity | one activity of target | activity effective date separate | determines primary/additional placement only | no approved nonempty leaf / 2026-08-23 | unverified | unverified | approved_transform | disabled | exact boolean only | missing/conflict => do not guess from position | Future evidence |
| `requisites.activities[*].effective_date` | counterparty | `NOT_VERIFIED` | unknown date; 0..1 per activity | one activity of target | exact field semantics required | bound to exact activity row | no approved nonempty leaf / 2026-08-23 | unverified | unverified | approved_transform | disabled | null until exact leaf bind | never substitute report/source receipt date | Future evidence |
| `requisites.managers[*].name` | counterparty | `$.company.managers[*].fio`, candidate fallback `full_name` | string; 0..N source, public cap 20; nullable leaf | target management composition | appointed date is separate | manager role only; never an opposing-party entity classifier | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed shape | unverified provider role/scope | approved_transform | disabled | safe NFC name only after semantic gate | missing name => manager row ineligible | I20 + future evidence |
| `requisites.managers[*].role` | counterparty | `$.company.managers[*].position` | string; 0..1 per manager; nullable | target management composition | appointed date separate | approved closed role composition required | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed shape | unverified role catalog | approved_transform | disabled | closed safe role label | raw unknown role not emitted | I20 + future evidence |
| `requisites.managers[*].appointed_at` | counterparty | `$.company.managers[*].date`, candidate fallback `appointed_at` | ISO-date string; 0..1 per manager; nullable | manager appointment | field date only | bound to exact manager row | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed shape | unverified scope | approved_transform | disabled | validated date or null | malformed/missing => null | I20 + future evidence |
| `requisites.managers[*].is_inaccuracy` | counterparty | `$.company.managers[*].is_inaccuracy` | boolean; 0..1 per manager; nullable | manager record | source receipt only | bound to manager row | `R-CODE`, `R-FIX` / 2026-08-23 | verified observed shape | unverified provider semantics | approved_transform | disabled | exact boolean or null | missing is unknown, not false | I20 + future evidence |
| `manager_personal_identifier` | counterparty | `$.company.managers[*].innfl` | string; 0..1 per manager; nullable | private natural-person identity | not public | private identity only | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed shape | not needed for public content | prohibited | disabled | discard/hide; never DTO/SSR/AI/telemetry | any presence is removed before public projection | I20 privacy tests |
| `requisites.owners[*]` | counterparty | `NOT_VERIFIED` within observed root `$.company.owners` | root object/list candidate; public cap 50 | ownership composition | exact ownership effective date required | owner type/name/share must bind to one row | root status only; no tracked nonempty leaf fixture / 2026-08-23 | unverified | unverified | approved_transform for safe composition only | disabled | empty plus `owner_leaf_schema_unverified` | no leaf guessing, no name-derived type | Future evidence |
| `requisites.owners[*].display_name` | counterparty | `NOT_VERIFIED` | unknown scalar; exactly 1 per eligible owner | ownership composition | effective date separate | safe display only; never owner identity key | no approved nonempty leaf / 2026-08-23 | unverified | unverified | approved_transform | disabled | bounded safe composition name | missing/name conflict => owner row hidden | Future evidence |
| `requisites.owners[*].owner_type` | counterparty | `NOT_VERIFIED` | unknown enum candidate; exactly 1 per eligible owner | ownership composition | effective date separate | exact person/organization/state classification | no approved nonempty leaf / 2026-08-23 | unverified | unverified | approved_transform | disabled | closed public enum only | never infer from name, OPF, or identifier length | Future evidence |
| `requisites.owners[*].share_percent_decimal` | counterparty | `NOT_VERIFIED` | unknown Decimal candidate; 0..1 per owner | ownership composition | effective date separate | exact share bound to owner row | no approved nonempty leaf / 2026-08-23 | unverified | unverified unit/basis | approved_transform | disabled | canonical Decimal only after gate | missing/conflict => null; not zero | Future evidence |
| `requisites.owners[*].share_display` | counterparty | derived only from verified exact share | derived string; 0..1 per owner | ownership composition | same as share | not a provider free-text field | no approved share leaf / 2026-08-23 | unverified input | unverified | approved_transform | disabled | backend deterministic formatting | null when exact share unavailable | I20 after evidence |
| `requisites.owners[*].effective_date` | counterparty | `NOT_VERIFIED` | unknown date; 0..1 per owner | ownership composition | exact ownership effective date | bound to exact owner/share row | no approved nonempty leaf / 2026-08-23 | unverified | unverified | approved_transform | disabled | validated date or null | never substitute report/source date | Future evidence |
| `owner_identifiers_contacts` | counterparty | `NOT_VERIFIED` | unknown | private owner identity/contact | not public | never needed for public grouping | no approved evidence / 2026-08-23 | unverified | not needed | prohibited | disabled | hidden/discarded | unknown nested keys rejected from public DTO | I20 privacy tests |
| `requisites.employees` | counterparty | `NOT_VERIFIED` within observed root `$.company.workers_count` | observed root may be integer/object/list; 0..1 public fact | target organization | exact period and effective date required | organization aggregate only | `R-CODE`, null synthetic leaf / 2026-08-23 | unverified | unverified count/scope/period | approved_transform | disabled | null plus `employees_scope_unverified` | missing is unknown, never zero | Future evidence |
| `requisites.employees.count` | counterparty | `NOT_VERIFIED` | unknown integer candidate; exactly 1 per eligible fact | target organization | period/effective date separate | aggregate count only | null synthetic leaf / 2026-08-23 | unverified | unverified | approved_transform | disabled | bounded nonnegative integer | missing is unknown, never zero | Future evidence |
| `requisites.employees.period` | counterparty | `NOT_VERIFIED` | unknown scalar; exactly 1 per eligible fact | target organization | exact reference period | bound to count | no approved leaf / 2026-08-23 | unverified | unverified | approved_transform | disabled | closed/bounded period label | absent period makes count ineligible | Future evidence |
| `requisites.employees.effective_date` | counterparty | `NOT_VERIFIED` | unknown date; 0..1 | target organization | exact effective/reference date | bound to count and period | no approved leaf / 2026-08-23 | unverified | unverified | approved_transform | disabled | validated date or null | never substitute report/source date | Future evidence |
| `requisites.tax_authority` | counterparty | `NOT_VERIFIED` | unknown object; 0..1 | target organization | exact effective/reference date required | exact authority code/label | no approved source / 2026-08-23 | unverified | unverified | approved_transform | disabled | null plus `tax_authority_unverified` | no extraction from address/free text | Future evidence |
| `requisites.tax_authority.code` | counterparty | `NOT_VERIFIED` | unknown scalar; exactly 1 per eligible authority | target organization | effective date separate | exact authority identity code | no approved source / 2026-08-23 | unverified | unverified | approved_transform | disabled | closed code only | missing/conflict => authority hidden | Future evidence |
| `requisites.tax_authority.label` | counterparty | `NOT_VERIFIED` | unknown scalar; exactly 1 per eligible authority | target organization | effective date separate | label bound to exact authority code | no approved source / 2026-08-23 | unverified | unverified | approved_transform | disabled | bounded safe label | no free-text/address inference | Future evidence |
| `requisites.tax_authority.effective_date` | counterparty | `NOT_VERIFIED` | unknown date; 0..1 | target organization | exact authority effective date | bound to authority record | no approved source / 2026-08-23 | unverified | unverified | approved_transform | disabled | validated date or null | never substitute report/source date | Future evidence |
| `contacts` | counterparty | `$.company.contacts` root is observed; no public leaf mapping | object/list candidate; any cardinality; nullable | target organization/contact persons | irrelevant | contact identifiers are not public Card-v2 facts | `R-CODE`, null synthetic root / 2026-08-23 | unverified leaves | not needed | prohibited | disabled | do not request for Card v2; never store in sanitized public facts or emit | presence is discarded, not summarized | I20 privacy tests |

## 6. Finance fields

The twelve code rows below are parser-shape evidence only. They do not prove
the DataNewton unit. Source names are not public labels; H2 uses a fixed local
metric catalog. All monetary rows remain operationally disabled until the
separate finance evidence artifact activates the exact endpoint/filter/shape
policy.

The current `response.json()` path also does not prove lossless source Decimal
transport: it may already have coerced a JSON number to binary float.
`company_card_source_decimal_v1` is universal for finance, arbitration amount
and charter-capital monetary leaves. The independent
`finance_decimal_transport`, `arbitration_decimal_transport` and
`charter_capital_decimal_transport` gates are each `UNVERIFIED / BLOCKED`.
V3 accepts only a validated source-byte number lexeme or JSON string; passing
the OKEI/unit matrix alone cannot enable monetary Chart Facts.

| Field ID | Dataset / endpoint | Exact path or `NOT_VERIFIED` | JSON type; cardinality; nullability | Subject scope | Effective/reference date | Identity semantics | Observed source/date | Schema | Semantic | Privacy | Operational | Public transformation | Missing/conflict behavior | Future owner |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `finance.balance.1210` | finance / `GET /v1/finance` | `$.balances..{code="1210"}.sum["<year>"]` | number/string Decimal; 0..N matches per year; nullable | target organization statement | exact year key | `(form,code,year)` | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified parser shape | unit unverified | approved_transform | disabled | fixed label `Запасы`; money only after unit gate | absent/null => missing; explicit zero preserved; unequal duplicates => conflict | I20/I23 |
| `finance.balance.1230` | finance | `$.balances..{code="1230"}.sum["<year>"]` | number/string Decimal; 0..N; nullable | target statement | exact year key | `(form,code,year)` | same / 2026-08-23 | verified parser shape | unit unverified | approved_transform | disabled | fixed label `Долги покупателей` | same deterministic rules | I20/I23 |
| `finance.balance.1240` | finance | `$.balances..{code="1240"}.sum["<year>"]` | number/string Decimal; 0..N; nullable | target statement | exact year key | `(form,code,year)` | `R-CODE`, `O-SHAPE`; tracked fixture lacks this code / 2026-08-23 | verified walker capability; tracked code fixture incomplete | unit unverified | approved_transform | disabled | fixed label `Финансовые вложения` | same; absence is not zero | I20/I23 |
| `finance.balance.1250` | finance | `$.balances..{code="1250"}.sum["<year>"]` | number/string Decimal; 0..N; nullable | target statement | exact year key | `(form,code,year)` | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified parser shape | unit unverified | approved_transform | disabled | fixed label `Деньги на счетах` | same deterministic rules | I20/I23 |
| `finance.balance.1300` | finance | `$.balances..{code="1300"}.sum["<year>"]` | number/string Decimal; 0..N; nullable | target statement | exact year key | `(form,code,year)` | same / 2026-08-23 | verified parser shape | unit unverified | approved_transform | disabled | fixed label `Свои средства` | same deterministic rules | I20/I23 |
| `finance.balance.1400` | finance | `$.balances..{code="1400"}.sum["<year>"]` | number/string Decimal; 0..N; nullable | target statement | exact year key | `(form,code,year)` | same / 2026-08-23 | verified parser shape | unit unverified | approved_transform | disabled | fixed long-liability metric label | same deterministic rules | I20/I23 |
| `finance.balance.1500` | finance | `$.balances..{code="1500"}.sum["<year>"]` | number/string Decimal; 0..N; nullable | target statement | exact year key | `(form,code,year)` | same / 2026-08-23 | verified parser shape | unit unverified | approved_transform | disabled | fixed label `Ближайшие обязательства` | same deterministic rules | I20/I23 |
| `finance.balance.1600` | finance | `$.balances..{code="1600"}.sum["<year>"]` | number/string Decimal; 0..N; nullable | target statement | exact year key | `(form,code,year)` | same / 2026-08-23 | verified parser shape | unit unverified | approved_transform | disabled | fixed label `Всё имущество` | same deterministic rules | I20/I23 |
| `finance.results.2100` | finance | `$.fin_results..{code="2100"}.sum["<year>"]` | number/string Decimal; 0..N; nullable | target statement | exact year key | `(form,code,year)` | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified parser shape | unit unverified | approved_transform | disabled | fixed gross-profit metric | same deterministic rules | I20/I23 |
| `finance.results.2110` | finance | `$.fin_results..{code="2110"}.sum["<year>"]` | number/string Decimal; 0..N; nullable | target statement | exact year key | `(form,code,year)` | same / 2026-08-23 | verified parser shape | unit unverified | approved_transform | disabled | fixed label `Продажи` | same deterministic rules | I20/I23 |
| `finance.results.2200` | finance | `$.fin_results..{code="2200"}.sum["<year>"]` | number/string Decimal; 0..N; nullable | target statement | exact year key | `(form,code,year)` | same / 2026-08-23 | verified parser shape | unit unverified | approved_transform | disabled | fixed operating-profit metric | same deterministic rules | I20/I23 |
| `finance.results.2400` | finance | `$.fin_results..{code="2400"}.sum["<year>"]` | number/string Decimal; 0..N; nullable | target statement | exact year key | `(form,code,year)` | same / 2026-08-23 | verified parser shape | unit unverified | approved_transform | disabled | fixed label `Чистая прибыль` | same deterministic rules | I20/I23 |
| `finance.reporting_years` | finance | year keys of each matched sibling `sum` object; form-level `years` is provenance only | integer-like object keys; 0..N | target statement | reporting year, exact semantics not inferred from current date | bound to each `(form,code)` value | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified parser shape | verified as explicit keys only | approved_transform | planned after unit gate | data-derived anchor/window only | malformed key ignored with warning; gaps remain gaps | I20/I23 |
| `finance.source_unit` | finance | `NOT_VERIFIED` | unknown | exact finance endpoint/filter/shape and twelve codes | same reporting period as value | must bind every compared value scale | no unit leaf in inspected evidence / 2026-08-23 | unverified | unverified | approved_transform | disabled | no `RUB`, ruble symbol, multiplication/division, or monetary Chart Facts | any ambiguity keeps policy blocked | Future authorized evidence stage |
| `finance.decimal_transport` | finance response bytes | `NOT_VERIFIED`; current `response.json()` is post-coercion only | source number lexeme or JSON string required by `company_card_source_decimal_v1` | every monetary value | exact source value | binds lexical value before Decimal conversion | `R-CODE` / 2026-08-23 | unverified | unverified | approved_transform | disabled | no v3 money, Chart Facts or geometry | float/post-coercion input => `decimal_transport_lossy`; no fallback | I20 future lexical-ingestion evidence |
| `finance.code_4400` | finance | observed under money-flow form, excluded from H2 v1 | number/string Decimal candidate; historical years only | target cash-flow statement | exact year key | different form/code from approved twelve | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified parser shape | out of H2 contract | prohibited for H2 v1 projection | disabled | never emitted or carried into later periods | historical presence cannot fill a missing approved row | I20 regression tests |

## 7. Arbitration fields

The owner sample contained one complete-looking page for one subject. That
observation does not prove the vendor total leaf, offset semantics, page
stability, or multi-page behavior. Collection remains disabled until the
arbitration evidence registry binds the envelope before the first v3 request.

| Field ID | Dataset / endpoint | Exact path or `NOT_VERIFIED` | JSON type; cardinality; nullability | Subject scope | Effective/reference date | Identity semantics | Observed source/date | Schema | Semantic | Privacy | Operational | Public transformation | Missing/conflict behavior | Future owner |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `arbitration.data` | arbitration / `GET /v1/arbitration-cases` | `$.data` | array; 0..limit rows; required envelope member | cases related to requested target under provider scope | page receipt; case dates separate | row identity comes only from verified case key | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed shape | provider collection scope unverified | unreviewed until row privacy transform | disabled | sanitized rows only; raw pages never persisted | invalid/non-array => envelope invalid/partial | I20 |
| `arbitration.source_total` | arbitration | `NOT_VERIFIED`; observed candidate `$.total_cases` is not authoritative evidence | nonnegative integer required; exactly one per page | exact provider result population for target/filter | page receipt | collection bound, not case identity | `R-FIX`, `O-SHAPE` / 2026-08-23 | unverified authoritative leaf/type | unverified total scope/stability | approved_transform | disabled | internal count and disclosed scope only after bind | missing/drift => no complete assertion; partial with reason | Future evidence + I20 |
| `arbitration.collection_completeness` | derived from bound pagination | not a provider leaf | `collection_complete`, closed completion reasons, counters and page manifest | bounded collection only | collection receipt | no calendar assertion | iteration-19 contract / 2026-08-23 | planned | planned | approved_transform | disabled | stored in `ArbitrationCollectionV1` and public summary only after envelope gate | collection completion never proves calendar completion or zero | I20 |
| `arbitration.calendar_completeness` | separate calendar evidence | `NOT_VERIFIED` | `calendar_complete`, `calendar_scope`, calendar/observed bounds, `calendar_evidence_version`, `unknown_year_count`, `zero_years_proven` | calendar coverage independent from collection | evidence-bound calendar period | no case identity use | no approved calendar evidence / 2026-08-23 | unverified | unverified | approved_transform | disabled | A1 observed-only; no synthetic zero | only separate zero-year proof may emit zero bucket | Future evidence + I24 |
| `arbitration.offset` | arbitration | `$.offset` observed candidate | nonnegative integer; exactly one; nullable in current shapes | requested result page | page receipt | request/response page position | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed shape | expected-offset semantics unverified | approved_transform | disabled | page provenance only | missing/drift => partial | Future evidence + I20 |
| `arbitration.limit` | arbitration | `$.limit` observed candidate | positive integer; exactly one; nullable in current shapes | requested result page | page receipt | page bound only | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed shape | provider semantics unverified | approved_transform | disabled | page provenance only; product request `page_size=100` | invalid/change => partial | Future evidence + I20 |
| `arbitration.case_key` | arbitration | preferred `$.data[*].case_id`, fallback `$.data[*].id` | string; exactly one nonblank effective key per valid row | one arbitration case | case lifetime identity | exact preferred/fallback; visible number is separate | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed shape | identity semantics require registry confirmation | internal only | disabled | deterministic report-scoped `case_` public ID after closed CJSON ordering; provider key never public | neither key => malformed; same key/equal canonical row collapses; conflict excludes key | Future evidence + I20 |
| `arbitration.visible_case_number` | arbitration | `NOT_VERIFIED`; observed candidate must not be assumed | string candidate; 0..1; nullable | one arbitration case | case identity display only | never used for dedup | local candidates only / 2026-08-23 | unverified | unverified | approved_transform | disabled | null / `Номер не указан` until exact path gate | never display case key as fallback | Future evidence + I20 |
| `arbitration.case_year` | arbitration | `$.data[*].year` observed candidate | integer; 0..1; nullable | one case | claimed case-start year requires proof | not identity | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed shape | year semantics unverified | approved_transform | disabled | validated year or null | missing => unknown-year bucket; no synthetic zero year in partial collection | Future evidence + I20/I24 |
| `arbitration.date_start` | arbitration | `$.data[*].date_start` | ISO-date string candidate; 0..1; nullable | one case | case start candidate | not identity | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed shape | date scope unverified | approved_transform | disabled | validated date or null | malformed/missing => null | Future evidence + I20 |
| `arbitration.date_update` | arbitration | `$.data[*].date_update` | ISO-date string candidate; 0..1; nullable | one case | last-update candidate | alias ordering only after scope proof | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed shape | date scope unverified | approved_transform | disabled | validated date or null | inversion with start => null duration plus limitation | Future evidence + I20 |
| `arbitration.party_collections` | arbitration | `$.data[*].{plaintiffs,respondents,applicants,creditors,creditors_current_payments,debtors,interested_persons,third_parties,others}` | arrays; 0..N each; nullable/malformed possible | parties to one case | case record dates only | source collection ID plus array ordinal defines exact party position | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed collection shapes | provider role scope unverified | transformation pending | disabled | sanitize each eligible party; collections drive exact role set | malformed collection => case privacy/role limitation, never guessed role | Future evidence + I20 |
| `arbitration.party_inn` | arbitration | `$.data[*].<verified_collection>[*].inn`, candidate fallback `inn_src` | string; 0..1 per party; nullable | one party position | case record only | exact normalized INN; target role and verified legal/state grouping use distinct policies | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed shape | provider identity semantics unverified | internal grouping only; public identifier prohibited | disabled | never DTO/HTML/AI/telemetry; exact target match only | missing => no exact target match/no cross-case legal grouping | Future evidence + I20 |
| `arbitration.party_ogrn` | arbitration | `$.data[*].<verified_collection>[*].ogrn`, candidate fallback `ogrn_src` | string; 0..1; nullable | one party position | case record only | supplementary identity; never target-role substitute | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed shape | semantics unverified | internal only | disabled | not emitted | missing/conflict does not change exact-INN role | Future evidence + I20 |
| `arbitration.party_name` | arbitration | `$.data[*].<verified_collection>[*].name`; normalized candidate `norm_name` | string; 0..1 each; nullable | one party position | case record only | never identity, entity classifier, or cross-case grouping key | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed shape | safe-name semantics unverified | legal/state only after entity gate; natural/unknown prohibited | disabled | safe normalized alias or mask only | missing => safe mask/omission; conflicting aliases resolved only by approved algorithm | Future evidence + I20/I24 |
| `arbitration.party_role_leaf` | arbitration | `$.data[*].<verified_collection>[*].role` | string; 0..1; nullable | one party position | case record only | source collection, not free role text, controls public role | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed shape | free-text/catalog semantics unverified | internal only | disabled | not emitted; may be retained only as sanitized evidence if approved | missing/conflict never overrides collection role | Future evidence + I20 |
| `arbitration.party_entity_type` | arbitration | `NOT_VERIFIED` | unknown; 0..1 per party; nullable | one party position | case record only | must be exact provider-backed legal/state/natural classification | no approved leaf / 2026-08-23 | unverified | unverified | approved_transform contract; implementation blocked | disabled | legal/state safe name; natural and unknown/conflict report-scoped mask | never infer from name, OPF text, or identifier length | Future evidence + I20 |
| `arbitration.party_result` | arbitration | `$.data[*].party_result` observed only in ignored local shape | string; 0..1; nullable | exact target company's result in one case | case record/update scope unverified | must be company-scoped, not general case result | `O-SHAPE`; absent from tracked fixture/current snapshot / 2026-08-23 | unverified tracked contract | unverified scope/semantics | approved_transform | disabled | exact case-sensitive `WON/LOST/RETURNED`, else unknown, only after gate | missing/unknown => `unknown`; never substitute result/status/documents | Future evidence + I20/I24 |
| `arbitration.result_detail` | arbitration | `$.data[*].result_type` | string; 0..1; nullable | one case | case record/update scope unverified | clarification only, never outcome | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed shape | closed detail catalog unverified | approved_transform after catalog | disabled | null until optional catalog gate | missing/unknown => null; never classify win/loss | Future evidence + I20 |
| `arbitration.amount` | arbitration | `$.data[*].sum` | number/string Decimal candidate; 0..1; nullable | one case | case record/update scope | belongs to case key, not debt identity | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified post-coercion parser shape only | field meaning/scope and lexical transport unverified | approved_transform | disabled | blocked; after both gates, exact signed source amount and never debt/recovered sum | missing remains missing; explicit zero and negative retain sign only after transport proof | Future evidence + I20/I24 |
| `arbitration.decimal_transport` | arbitration response bytes | `NOT_VERIFIED`; current `response.json()` is post-coercion only | source number lexeme or JSON string required by `company_card_source_decimal_v1` | arbitration amount only | exact source amount | binds lexical value before Decimal conversion | `R-CODE` / 2026-08-23 | unverified | unverified | approved_transform | disabled | A4 amount display/geometry blocked | float/post-coercion input => `decimal_transport_lossy`; no fallback | I20/I24 lexical-ingestion evidence |
| `arbitration.currency` | arbitration | `$.data[*].currency` | string; 0..1; nullable | one case amount | same as amount | closed source-currency catalog required | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed shape | mapping unverified | approved_transform | disabled | closed ID/display only; no FX | missing/unknown => no symbol and amount excluded from A4 currency group | Future evidence + I20/I24 |
| `arbitration.instance_count` | arbitration | `NOT_VERIFIED`; local candidate observed | integer candidate; 0..1; nullable | one case | case record/update scope | must count the same verified instance collection | `O-SHAPE`; absent tracked fixture/current snapshot / 2026-08-23 | unverified | unverified | approved_transform | disabled | null | never derive from documents or array length without exact bind | Future evidence + I20 |
| `arbitration.courts` | arbitration | `NOT_VERIFIED`; local `instances[]` candidates observed | array of objects/labels; 0..N, public cap 10 | one case | per instance date/scope unverified | exact court/instance label only | `O-SHAPE`; absent tracked fixture/current snapshot / 2026-08-23 | unverified | unverified | approved_transform | disabled | empty array until exact path/catalog | no court inference from document text | Future evidence + I20 |
| `arbitration.public_case_url` | arbitration | candidate `$.data[*].kad_arbitr_link`; host/path contract `NOT_VERIFIED` | string URL; 0..1; nullable | one case | case record only | must correspond to exact case | `R-CODE`, `R-FIX`, `O-SHAPE` / 2026-08-23 | verified observed scalar | HTTPS host/path semantics unverified | approved_transform | disabled | null until allowlist; then external link with no-referrer protections | invalid/missing/unapproved host => text-only case number | Future evidence + I20/I24 |

## 8. Derived public identifiers and labels

The following are deliberately not provider fields:

- `case_public_id` and `opponent_public_id` are report-scoped deterministic
  public IDs allocated from closed ordering identities (`case_`/`opponent_`
  plus six zero-padded digits); they never embed provider IDs, HMAC material or
  source ordinals;
- finance and outcome labels come from closed versioned catalogs;
- natural/unknown opposing-party displays come from the approved HMAC masking
  transformation;
- percentages, Chart Facts, geometry, `N/M`, durations, windows, and coverage
  are deterministic derived facts governed by the architecture and privacy
  ADRs;
- actions, breadcrumbs, CTA copy, report date, source metadata, and narrative
  are controlled product/persistence fields, not provider leaf guesses.

Provider names, IDs, hashes, or free text must never be reused as these public
identifiers.

## 9. Gate conclusion and downstream blockers

The local sample supports the observed finance and arbitration shapes, but it
does not close vendor semantics. Current conclusions are therefore:

1. Existing core identity/address may be reused through the exact H1-safe
   transformation.
2. Finance monetary capability remains `UNVERIFIED / BLOCKED`; iteration 23
   cannot start.
3. Arbitration envelope total, visible case number, outcome scope, entity
   type, currency mapping, instance/court fields, and KAD link remain
   unverified. Bounded full collection and A1-A5 publication remain blocked.
4. Manager safe composition has an approved privacy shape but remains hidden
   until provider role/scope semantics close.
5. Owners, activities, workers, tax modes, tax authority, status/effective
   date, legal form, and charter-capital unit remain hidden.
6. Contacts and personal identifiers are prohibited, not merely unavailable.

After iteration 19 is merged, this evidence artifact is immutable. Later
authorization or vendor evidence creates a new versioned artifact and registry
decision instead of rewriting this history.

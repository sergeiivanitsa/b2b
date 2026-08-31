# Data Newton LLC OPF alias evidence v1

Evidence date: `2026-09-01`

Source: Data Newton public API documentation and its public sandbox for
`GET /v1/counterparty`:
`https://datanewton.ru/docs/api/counterparty`.

The response schema binds the legal-form field to `$.company.opf`. The public
sandbox response exposes this exact LLC value:

```text
Общества с ограниченной ответственностью
```

This differs from the singular product label
`Общество с ограниченной ответственностью`. The URL registry therefore treats
the observed plural value as an exact provider alias of the existing
`ООО -> ooo` rule. Matching remains NFKC/casefold/whitespace-normalized and
default-deny; no other provider aliases are approved by this evidence.

The repository does not retain the sandbox response, company identifiers,
names, owners or any other raw provider data. Regression tests use only the
exact observed OPF scalar inside the existing minimal sanitized provider
shape. No production record is read, rewritten, regenerated or backfilled by
this change.

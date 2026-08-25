"""Local-only deterministic H2 SSR fixture server for visual checks.

It deliberately has no database, provider, Gateway, AI or network client.
Run after ``npm run build --prefix services/web_ui``.
"""
from __future__ import annotations

import os
import sys
import json
from datetime import datetime, timezone
from hashlib import sha256
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "services" / "product_api" / "src"))

import shared  # noqa: E402,F401  # proves current-worktree shared import

from product_api.company_reports.company_card_v2.finance import build_chart_facts
from product_api.company_reports.company_card_v2.models import (  # noqa: E402
    ArbitrationBasisV1, CompanyCardCounterpartyCoreV1, CompanyCardV2Snapshot,
    FinanceBasisV1,
)
from product_api.company_reports.company_card_v2.narrative.catalog import (  # noqa: E402
    FALLBACK_DESCRIPTION, FALLBACK_PROFILE_ID, FALLBACK_RENDERER_VERSION,
)
from product_api.company_reports.company_card_v2.public_h2 import build_public_h2  # noqa: E402
from product_api.company_reports.company_card_v2.canonical_json import canonical_digest  # noqa: E402
from product_api.company_reports.company_card_v2.public_h2_asset_manifest import load_public_h2_asset_manifest  # noqa: E402
from product_api.company_reports.company_card_v2.public_h2_document import render_public_h2_document  # noqa: E402
from product_api.company_reports.company_card_v2.public_h2_models import PublicH2Narrative  # noqa: E402


class _Binding:
    narrative = PublicH2Narrative(
        mode="deterministic_fallback", renderer_version=FALLBACK_RENDERER_VERSION,
        description=FALLBACK_DESCRIPTION, statement_ids=(FALLBACK_PROFILE_ID,),
        render_digest=sha256(FALLBACK_DESCRIPTION.encode("utf-8")).hexdigest(),
    )


class _ArtifactBinding:
    narrative = PublicH2Narrative(
        mode="artifact", renderer_version=FALLBACK_RENDERER_VERSION,
        description=FALLBACK_DESCRIPTION, statement_ids=(FALLBACK_PROFILE_ID,),
        render_digest=sha256(FALLBACK_DESCRIPTION.encode("utf-8")).hexdigest(),
    )


REQUESTS: list[str] = []


def _dto(profile: str = "saved-artifact"):
    basis = FinanceBasisV1()
    snapshot = CompanyCardV2Snapshot(
        report_id="00000000-0000-4000-8000-000000000001", subject_inn="7701234567", target_inn="7701234567",
        rollout_config_generation=1, generated_at=datetime(2026, 8, 24, 12, tzinfo=timezone.utc),
        counterparty=CompanyCardCounterpartyCoreV1(inn="7701234567", full_name=("Тестовое общество " + "длинное наименование " * 20 if profile == "long-public-strings" else "Тестовое общество"), address=("г. Москва, " + "длинный адрес, " * 40 if profile == "long-public-strings" else "г. Москва")),
        finance_basis=basis, arbitration_basis=ArbitrationBasisV1(), chart_facts=build_chart_facts(basis),
        evidence_version="evidence_v1", privacy_version="privacy_v1",
    )
    dto = build_public_h2(snapshot, narrative_binding=_ArtifactBinding() if profile == "saved-artifact" else _Binding())
    data = dto.model_dump(mode="json")
    if profile == "deterministic-fallback":
        data["narrative"]["description"] = data["narrative"]["description"].replace("компания", "организация", 1)
    if profile == "long-public-strings":
        data["identity"]["display_name"] = "Тестовое общество — длинный профиль"
        data["breadcrumbs"][1]["label"] = data["identity"]["display_name"]
    if profile == "gate-closed":
        data["limitations"].append({"code": "fixture_gate_closed", "block_id": "finance_f1", "field_id": None, "message": "Тестовое ограничение: доступ к части сведений закрыт."})
        data["coverage"][2]["state"] = "gate_closed"; data["coverage"][2]["limitation_codes"] = ["fixture_gate_closed"]
    if profile == "partial-long-limitations":
        data["limitations"].append({
            "code": "fixture_partial",
            "block_id": "arbitration_a1",
            "field_id": None,
            "message": (
                "Тестовое длинное ограничение: сведения представлены не полностью; "
                "часть источников недоступна на дату составления отчёта, поэтому "
                "показатели раздела нельзя считать исчерпывающими. " * 2
            ).strip(),
        })
        data["coverage"][7]["state"] = "partial"; data["coverage"][7]["limitation_codes"] = ["fixture_partial"]
    digest_payload = dict(data); digest_payload.pop("projection_digest", None)
    data["projection_digest"] = canonical_digest(digest_payload)
    from product_api.company_reports.company_card_v2.public_h2_models import CompanyPublicH2Response
    return CompanyPublicH2Response.model_validate(data)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / "services" / "web_ui" / "dist-company-public-h2"), **kwargs)

    def do_GET(self):  # noqa: N802
        REQUESTS.append(self.path)
        path, _, query = self.path.partition("?")
        if path == "/favicon.ico":
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        profile = "saved-artifact"
        if query.startswith("profile="):
            profile = query.removeprefix("profile=")
        if profile not in {"saved-artifact", "deterministic-fallback", "gate-closed", "partial-long-limitations", "long-public-strings"}:
            self.send_error(404); return
        if path == "/__requests":
            body = json.dumps(REQUESTS).encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            return
        if path == _dto().canonical_path:
            body = render_public_h2_document(_dto(profile), load_public_h2_asset_manifest(), "fixture-nonce").encode("utf-8")
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
            return
        super().do_GET()


if __name__ == "__main__":
    host, port = "127.0.0.1", int(os.environ.get("ITERATION22_FIXTURE_PORT", "8122"))
    print(f"iteration22 fixture: http://{host}:{port}/company/7701234567-company")
    ThreadingHTTPServer((host, port), Handler).serve_forever()

from pathlib import Path
import tomllib

from product_api.providers.datanewton import build_cache_key, calculate_response_hash


def _cache_key(body):
    return build_cache_key(
        provider="DataNewton",
        dataset="batch_cards",
        base_url="https://api.datanewton.ru/",
        method="post",
        endpoint="v1/batchCards",
        query_params={"region": " 25 ", "key": "super-secret-api-key"},
        body=body,
    )


def test_cache_key_is_stable_for_same_logical_request():
    first = _cache_key({"source_inns_or_ogrns": ["7701-234-567", "1027700132195"]})
    second = build_cache_key(
        provider="datanewton",
        dataset="batch_cards",
        base_url="https://api.datanewton.ru",
        method="POST",
        endpoint="/v1/batchCards",
        query_params={"KEY": "a-different-secret", "region": "25"},
        body={"source_inns_or_ogrns": ["7701234567", "1027700132195"]},
    )

    assert first == second
    assert first.startswith("datanewton:batch_cards:v1:")


def test_cache_key_changes_when_body_changes_or_identifier_order_changes():
    original = _cache_key({"source_inns_or_ogrns": ["7701234567", "1027700132195"]})
    other_identifier = _cache_key(
        {"source_inns_or_ogrns": ["7701234567", "500100000001"]}
    )
    other_order = _cache_key(
        {"source_inns_or_ogrns": ["1027700132195", "7701234567"]}
    )

    assert original != other_identifier
    assert original != other_order


def test_cache_key_never_contains_api_key():
    cache_key = _cache_key({"source_inns_or_ogrns": ["7701234567"]})

    assert "super-secret-api-key" not in cache_key
    assert "key" not in cache_key


def test_response_hash_uses_canonical_json():
    first = calculate_response_hash({"name": "ООО Тест", "nested": {"b": 2, "a": 1}})
    second = calculate_response_hash({"nested": {"a": 1, "b": 2}, "name": "ООО Тест"})

    assert first == second
    assert len(first) == 64


def test_package_discovery_includes_product_api_packages():
    project_root = Path(__file__).resolve().parents[1]
    configuration = tomllib.loads((project_root / "pyproject.toml").read_text("utf-8"))
    package_find = configuration["tool"]["setuptools"]["packages"]["find"]

    assert package_find == {"where": ["src"], "include": ["product_api*"]}
    for relative_package in (
        "product_api",
        "product_api/claims",
        "product_api/routers",
        "product_api/db",
        "product_api/providers",
        "product_api/providers/datanewton",
    ):
        assert (project_root / "src" / relative_package / "__init__.py").is_file()

async def test_public_h2_disabled_get_and_head_are_no_store(async_client) -> None:
    get_response = await async_client.get("/company-reports/7701234567/public-h2")
    head_response = await async_client.head("/company-reports/7701234567/public-h2")
    assert get_response.status_code == head_response.status_code == 404
    assert get_response.json()["detail"]["code"] == "company_public_h2_disabled"
    assert head_response.content == b""
    assert get_response.headers["cache-control"] == "no-store"

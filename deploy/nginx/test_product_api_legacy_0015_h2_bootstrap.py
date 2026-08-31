"""Static contract for the one-time revision-0015 nginx bridge."""
from pathlib import Path


CONFIG = Path(__file__).with_name("product_api_legacy_0015_h2_bootstrap.conf")


def test_bridge_exposes_only_candidate_web_and_fail_closed_h2_assets() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    assert "root /opt/b2b/services/web_ui/dist;" not in text
    assert text.count("root /var/lib/pork/web-ui/v1/current/site;") == 1
    assert text.count("location ^~ /assets/company-public-h2.") == 1
    h2 = text.split("location ^~ /assets/company-public-h2.", 1)[1].split("}", 1)[0]
    assert "root /var/lib/pork/company-public-h2/v1;" in h2
    assert "try_files $uri =404;" in h2
    assert "alias " not in h2 and "proxy_pass" not in h2


def test_bridge_closes_every_product_backed_route_until_switch() -> None:
    text = CONFIG.read_text(encoding="utf-8")
    for token in (
        "location ^~ /api/",
        'location ~ "^/company/(?:[0-9]{10}|[0-9]{12})-',
        'location ~ "^/company/(?:ooo|ao|oao|zao|pao|ip)-',
        "location = /robots.txt",
        "location = /sitemaps/index.xml",
        "location /",
    ):
        assert token in text
    assert text.count('add_header Retry-After "300" always;') >= 5
    assert text.count("return 503;") >= 4
    assert "proxy_pass" not in text
    public = text.split("location / {", 1)[1].split("}", 1)[0]
    assert "try_files $uri $uri/ /index.html =503;" in public
    assert "location ~ \"^/company/(?:[0-9]{10}|[0-9]{12})$\"" not in text
    assert "error_page 500" not in text and "error_page 502" not in text

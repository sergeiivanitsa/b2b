from datetime import datetime, timezone

from product_api.company_reports.seo import render_sitemap, render_sitemap_index


def test_sitemaps_are_canonical_deterministic_and_preserve_immutable_lastmod():
    lastmod = datetime(2026, 7, 24, 1, 2, 3, tzinfo=timezone.utc)
    url = "https://pork.su/company/0000000000-ooo-test"
    xml = render_sitemap([(url, lastmod)])
    assert "0000000000-ooo-test" in xml
    assert "2026-07-24T01:02:03Z" in xml
    assert "?" not in xml.split("<loc>", 1)[1].split("</loc>", 1)[0]
    index = render_sitemap_index(["https://pork.su/sitemaps/1.xml"])
    assert "sitemapindex" in index and "1.xml" in index

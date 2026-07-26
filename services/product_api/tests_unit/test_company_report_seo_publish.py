from product_api.company_reports.seo_publish import _parser


def test_manual_cli_requires_a_bounded_explicit_command():
    assert _parser().parse_args(["run", "--limit", "1"]).limit == 1
    assert _parser().parse_args(["control", "pause"]).state == "pause"

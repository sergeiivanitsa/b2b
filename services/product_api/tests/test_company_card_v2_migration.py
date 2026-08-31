from sqlalchemy import text


async def test_company_card_v2_foundation_tables_and_legacy_defaults(engine) -> None:
    async with engine.connect() as connection:
        names = set((await connection.execute(text("SELECT tablename FROM pg_tables WHERE schemaname=current_schema()"))).scalars())
        assert {"company_report_presentations", "company_report_presentation_pins"} <= names
        columns = set((await connection.execute(text("SELECT column_name FROM information_schema.columns WHERE table_name='company_reports'"))).scalars())
        assert {"writer_profile", "presentation_contract", "rollout_generation"} <= columns

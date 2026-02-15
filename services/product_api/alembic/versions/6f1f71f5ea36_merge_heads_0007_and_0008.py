"""merge heads 0007 and 0008

Revision ID: 6f1f71f5ea36
Revises: 0007_org_roles_and_company_fields, 0008_message_usage
Create Date: 2026-02-15 12:34:06.374307

"""
from alembic import op
import sqlalchemy as sa


revision = '6f1f71f5ea36'
down_revision = ('0007_org_roles_and_company_fields', '0008_message_usage')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

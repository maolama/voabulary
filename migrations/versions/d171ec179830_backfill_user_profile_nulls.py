"""backfill_user_profile_nulls

Revision ID: d171ec179830
Revises: 885d4f01a4ad
Create Date: 2026-04-01 01:44:08.255700

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd171ec179830'
down_revision = '885d4f01a4ad'
branch_labels = None
depends_on = None


def upgrade():
    # JUST PASTE THESE 4 LINES HERE:
    op.execute("UPDATE user_profile SET daily_review_limit = 50 WHERE daily_review_limit IS NULL")
    op.execute("UPDATE user_profile SET sprinkler_tokens = 0 WHERE sprinkler_tokens IS NULL")
    op.execute("UPDATE user_profile SET vacation_mode = 0 WHERE vacation_mode IS NULL")

def downgrade():
    pass

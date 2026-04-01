"""add_custom_data_to_saved_word

Revision ID: e585d6a65c73
Revises: d171ec179830
Create Date: 2026-04-01 12:14:33.992990

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e585d6a65c73'
down_revision = 'd171ec179830'
branch_labels = None
depends_on = None


def upgrade():
    # SQLite workaround for adding JSON columns
    op.execute("ALTER TABLE saved_words ADD COLUMN custom_data TEXT")

def downgrade():
    pass

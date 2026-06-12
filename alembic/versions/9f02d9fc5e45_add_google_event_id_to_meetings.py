"""add google_event_id to meetings

Revision ID: 9f02d9fc5e45
Revises: cb654acf820e
Create Date: 2026-06-12 23:03:42.476285

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9f02d9fc5e45'
down_revision: Union[str, Sequence[str], None] = 'cb654acf820e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("meetings", sa.Column("google_event_id", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("meetings", "google_event_id")

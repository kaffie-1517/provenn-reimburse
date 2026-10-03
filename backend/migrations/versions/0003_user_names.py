"""user names

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("name", sa.String(length=120), nullable=True))
    # Existing accounts: derive a readable name from the email ("rohan.mehta@" -> "Rohan Mehta").
    op.execute(
        """
        UPDATE users
           SET name = initcap(regexp_replace(split_part(email, '@', 1), '[._-]+', ' ', 'g'))
         WHERE name IS NULL
        """
    )
    op.alter_column("users", "name", nullable=False)


def downgrade() -> None:
    op.drop_column("users", "name")

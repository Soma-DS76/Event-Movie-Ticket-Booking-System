'add booking reminder tracking\n\nRevision ID: b6930214adb4\nRevises: 5c6e2ada986d\nCreate Date: 2026-10-28 16:48:16.913675\n\n'
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6930214adb4'
down_revision: Union[str, Sequence[str], None] = '5c6e2ada986d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'bookings',
        sa.Column('reminder_sent', sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column('bookings', 'reminder_sent')

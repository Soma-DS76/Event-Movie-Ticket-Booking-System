'add payment paid timestamp\n\nRevision ID: dcd88337d035\nRevises: b6930214adb4\nCreate Date: 2026-10-28 16:51:01.844829\n\n'
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dcd88337d035'
down_revision: Union[str, Sequence[str], None] = 'b6930214adb4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('payments', sa.Column('paid_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('payments', 'paid_at')

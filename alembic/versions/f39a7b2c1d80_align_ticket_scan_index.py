
from alembic import op
import sqlalchemy as sa


revision = 'f39a7b2c1d80'
down_revision = 'e88c6db741a2'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    duplicate = bind.execute(
        sa.text(
            'SELECT booking_id FROM ticket_scans '
            'GROUP BY booking_id HAVING COUNT(*) > 1 LIMIT 1'
        )
    ).first()

    if duplicate:
        raise RuntimeError(
            'Duplicate booking_id values exist in ticket_scans. '
            'Resolve them before applying the unique index.'
        )

    indexes = {
        index['name']: index
        for index in sa.inspect(bind).get_indexes('ticket_scans')
    }

    if 'uq_ticket_scans_booking_id' not in indexes:
        op.create_index(
            'uq_ticket_scans_booking_id',
            'ticket_scans',
            ['booking_id'],
            unique=True,
        )

    if 'ix_ticket_scans_booking_id' in indexes:
        op.drop_index(
            'ix_ticket_scans_booking_id',
            table_name='ticket_scans',
        )


def downgrade():
    bind = op.get_bind()

    indexes = {
        index['name']: index
        for index in sa.inspect(bind).get_indexes('ticket_scans')
    }

    if 'uq_ticket_scans_booking_id' in indexes:
        op.drop_index(
            'uq_ticket_scans_booking_id',
            table_name='ticket_scans',
        )

    if 'ix_ticket_scans_booking_id' not in indexes:
        op.create_index(
            'ix_ticket_scans_booking_id',
            'ticket_scans',
            ['booking_id'],
            unique=False,
        )

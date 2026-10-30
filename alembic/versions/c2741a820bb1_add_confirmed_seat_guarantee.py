'add database-level confirmed seat protection\n\nRevision ID: c2741a820bb1\nRevises: dcd88337d035\n'
from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = 'c2741a820bb1'
down_revision: Union[str, Sequence[str], None] = 'dcd88337d035'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not context.is_offline_mode():
        connection = op.get_bind()
        duplicates = connection.execute(
            sa.text(
                'SELECT show_id, seat_id FROM booking_seats '
                'JOIN bookings ON bookings.id = booking_seats.booking_id '
                "WHERE bookings.status = 'Confirmed' "
                'GROUP BY show_id, seat_id HAVING COUNT(*) > 1'
            )
        ).first()
        if duplicates:
            raise RuntimeError(
                'Cannot add confirmed-seat protection: duplicate confirmed seats '
                f"exist for show {duplicates.show_id}, seat {duplicates.seat_id}"
            )

    op.create_table(
        'confirmed_seats',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('booking_id', sa.Integer(), nullable=False),
        sa.Column('show_id', sa.Integer(), nullable=False),
        sa.Column('seat_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['show_id'], ['shows.id']),
        sa.ForeignKeyConstraint(['seat_id'], ['seats.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('show_id', 'seat_id', name='uq_confirmed_show_seat'),
        sa.UniqueConstraint('booking_id', 'seat_id', name='uq_confirmed_booking_seat'),
    )
    op.create_index('ix_confirmed_seats_id', 'confirmed_seats', ['id'])
    op.create_index('ix_confirmed_seats_booking_id', 'confirmed_seats', ['booking_id'])
    op.execute(
        sa.text(
            'INSERT INTO confirmed_seats (booking_id, show_id, seat_id) '
            'SELECT booking_seats.booking_id, booking_seats.show_id, booking_seats.seat_id '
            'FROM booking_seats JOIN bookings '
            'ON bookings.id = booking_seats.booking_id '
            "WHERE bookings.status = 'Confirmed'"
        )
    )


def downgrade() -> None:
    op.drop_index('ix_confirmed_seats_booking_id', table_name='confirmed_seats')
    op.drop_index('ix_confirmed_seats_id', table_name='confirmed_seats')
    op.drop_table('confirmed_seats')

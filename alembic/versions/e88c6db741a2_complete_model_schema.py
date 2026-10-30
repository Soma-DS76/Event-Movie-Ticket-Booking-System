'complete model schema and timestamp tracking\n\nRevision ID: e88c6db741a2\nRevises: c2741a820bb1\n'
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e88c6db741a2'
down_revision: Union[str, Sequence[str], None] = 'c2741a820bb1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_timestamps(table_name: str) -> None:
    op.add_column(
        table_name,
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.add_column(
        table_name,
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )


def upgrade() -> None:
    for table_name in (
        'screens',
        'seats',
        'seat_category_prices',
        'booking_seats',
    ):
        _add_timestamps(table_name)
    op.add_column(
        'payments',
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    _add_timestamps('confirmed_seats')

    op.create_table(
        'waitlists',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('show_id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('seat_count', sa.Integer(), nullable=False),
        sa.Column('preferred_category', sa.String(length=50), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['customer_id'], ['users.id']),
        sa.ForeignKeyConstraint(['show_id'], ['shows.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('show_id', 'customer_id', name='uq_waitlist_show_customer'),
    )
    op.create_index('ix_waitlists_id', 'waitlists', ['id'])
    op.create_index('ix_waitlists_show_id', 'waitlists', ['show_id'])
    op.create_index('ix_waitlists_customer_id', 'waitlists', ['customer_id'])

    op.create_table(
        'refunds',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('booking_id', sa.Integer(), nullable=False),
        sa.Column('payment_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('reason', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('refunded_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id']),
        sa.ForeignKeyConstraint(['payment_id'], ['payments.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_refunds_id', 'refunds', ['id'])
    op.create_index('ix_refunds_booking_id', 'refunds', ['booking_id'])

    op.create_table(
        'ticket_scans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('booking_id', sa.Integer(), nullable=False),
        sa.Column('staff_id', sa.Integer(), nullable=False),
        sa.Column('scanned_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['booking_id'], ['bookings.id']),
        sa.ForeignKeyConstraint(['staff_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('booking_id'),
    )
    op.create_index('ix_ticket_scans_id', 'ticket_scans', ['id'])
    op.create_index('ix_ticket_scans_booking_id', 'ticket_scans', ['booking_id'])


def downgrade() -> None:
    op.drop_index('ix_ticket_scans_booking_id', table_name='ticket_scans')
    op.drop_index('ix_ticket_scans_id', table_name='ticket_scans')
    op.drop_table('ticket_scans')
    op.drop_index('ix_refunds_booking_id', table_name='refunds')
    op.drop_index('ix_refunds_id', table_name='refunds')
    op.drop_table('refunds')
    op.drop_index('ix_waitlists_customer_id', table_name='waitlists')
    op.drop_index('ix_waitlists_show_id', table_name='waitlists')
    op.drop_index('ix_waitlists_id', table_name='waitlists')
    op.drop_table('waitlists')

    op.drop_column('confirmed_seats', 'updated_at')
    op.drop_column('confirmed_seats', 'created_at')
    op.drop_column('payments', 'updated_at')
    for table_name in (
        'booking_seats',
        'seat_category_prices',
        'seats',
        'screens',
    ):
        op.drop_column(table_name, 'updated_at')
        op.drop_column(table_name, 'created_at')

"""Add manager role and payment review workflow."""
from alembic import op
import sqlalchemy as sa

revision = "0004_manager_and_payment_review"
down_revision = "0003_customer_profiles_and_forced_password"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TYPE role ADD VALUE IF NOT EXISTS 'manager'")

    cols = {col["name"] for col in sa.inspect(bind).get_columns("payments")}
    if "status" not in cols:
        with op.batch_alter_table("payments") as batch:
            batch.add_column(sa.Column("status", sa.String(length=20), nullable=False, server_default="confirmed"))
    if "review_note" not in cols:
        with op.batch_alter_table("payments") as batch:
            batch.add_column(sa.Column("review_note", sa.String(length=255), nullable=False, server_default=""))
    if "reviewed_by" not in cols:
        with op.batch_alter_table("payments") as batch:
            batch.add_column(sa.Column("reviewed_by", sa.Integer(), nullable=True))
            batch.create_foreign_key("fk_payments_reviewed_by_users", "users", ["reviewed_by"], ["id"])
    if "reviewed_at" not in cols:
        with op.batch_alter_table("payments") as batch:
            batch.add_column(sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    # Existing payments were already posted to the ledger before this workflow.
    op.execute("UPDATE payments SET status = 'confirmed' WHERE status IS NULL OR status = ''")


def downgrade():
    with op.batch_alter_table("payments") as batch:
        batch.drop_column("reviewed_at")
        batch.drop_constraint("fk_payments_reviewed_by_users", type_="foreignkey")
        batch.drop_column("reviewed_by")
        batch.drop_column("review_note")
        batch.drop_column("status")

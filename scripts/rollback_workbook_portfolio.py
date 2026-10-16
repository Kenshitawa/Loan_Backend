"""Remove only the workbook portfolio import from the live database.

The import copied source created_at values to newly created customer rows. The
single pre-existing matched customer has a different timestamp and is kept.
This script aborts before deletion if the expected records or relationships do
not match the reviewed import counts.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import (  # noqa: E402
    AuditLog,
    Customer,
    CustomerDocument,
    CustomerInteraction,
    LegacyPortfolioLoan,
    Loan,
    SessionLocal,
    Setting,
    User,
)

MARKER = "workbook_entire_import_from_supabase_v1"


def source_url() -> str:
    raw = os.environ.get("SUPABASE_DATABASE_URL", "").strip()
    if not raw:
        raise RuntimeError("SUPABASE_DATABASE_URL is required for the targeted rollback")
    if raw.startswith("postgres://"):
        return "postgresql+psycopg://" + raw.removeprefix("postgres://")
    if raw.startswith("postgresql://"):
        return "postgresql+psycopg://" + raw.removeprefix("postgresql://")
    if not raw.startswith("postgresql+psycopg://"):
        raise RuntimeError("SUPABASE_DATABASE_URL must be a PostgreSQL URL")
    return raw


def main() -> None:
    source_engine = create_engine(source_url(), pool_pre_ping=True)
    try:
        with source_engine.connect().execution_options(isolation_level="REPEATABLE READ") as source:
            source_customers = source.execute(
                select(Customer.__table__).where(Customer.organization_id == 1)
            ).mappings().all()
            source_snapshots = source.execute(
                select(LegacyPortfolioLoan.__table__).where(LegacyPortfolioLoan.organization_id == 1)
            ).mappings().all()

        if len(source_customers) != 174 or len(source_snapshots) != 174:
            raise RuntimeError("Source workbook counts changed; no records were deleted")
        timestamps = {row["created_at"] for row in source_customers}
        if len(timestamps) != 1:
            raise RuntimeError("Source customer timestamps are not unique to this import; no records were deleted")
        imported_at = next(iter(timestamps))
        source_keys = [row["source_key"] for row in source_snapshots]
        if len(set(source_keys)) != 174:
            raise RuntimeError("Source snapshot identifiers are incomplete; no records were deleted")

        with SessionLocal() as db, db.begin():
            marker = db.scalar(select(Setting.id).where(Setting.key == MARKER).limit(1))
            if not marker:
                print("Workbook rollback marker is already absent; no changes made.")
                return

            imported_customers = db.scalars(
                select(Customer).where(
                    Customer.organization_id == 1,
                    Customer.created_at == imported_at,
                )
            ).all()
            if len(imported_customers) != 173:
                raise RuntimeError("Expected 173 newly imported customers; no records were deleted")
            imported_ids = [customer.id for customer in imported_customers]

            snapshot_ids = db.scalars(
                select(LegacyPortfolioLoan.id).where(
                    LegacyPortfolioLoan.organization_id == 1,
                    LegacyPortfolioLoan.source_key.in_(source_keys),
                )
            ).all()
            if len(snapshot_ids) != 174:
                raise RuntimeError("Expected 174 imported portfolio snapshots; no records were deleted")

            blockers = {
                "loans": db.scalar(select(Loan.id).where(Loan.customer_id.in_(imported_ids)).limit(1)),
                "interactions": db.scalar(select(CustomerInteraction.id).where(CustomerInteraction.customer_id.in_(imported_ids)).limit(1)),
                "documents": db.scalar(select(CustomerDocument.id).where(CustomerDocument.customer_id.in_(imported_ids)).limit(1)),
            }
            present = [name for name, record_id in blockers.items() if record_id is not None]
            if present:
                raise RuntimeError(
                    "Imported customers now have non-workbook records (" + ", ".join(present) + "); no records were deleted"
                )

            db.query(LegacyPortfolioLoan).filter(LegacyPortfolioLoan.id.in_(snapshot_ids)).delete(
                synchronize_session=False
            )
            db.query(Customer).filter(Customer.id.in_(imported_ids)).delete(synchronize_session=False)
            db.query(Setting).filter(Setting.key == MARKER).delete(synchronize_session=False)

            actor_id = db.scalar(select(User.id).where(User.role == "admin").order_by(User.id).limit(1))
            if actor_id is not None:
                db.add(
                    AuditLog(
                        actor_id=actor_id,
                        entity="legacy_portfolio",
                        entity_id=0,
                        action="rollback",
                        details="Removed the 174-row Entire workbook import and its 173 newly created customer records; preserved the one matched pre-existing customer.",
                        organization_id=1,
                        branch_id=1,
                    )
                )

        print(
            "Workbook rollback completed: snapshots_deleted=174, "
            "imported_customers_deleted=173, matched_preexisting_customers_preserved=1."
        )
    finally:
        source_engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Workbook rollback failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)

"""Merge the one-time Supabase workbook import into Render's live database.

This imports only customer records and legacy opening-balance snapshots. It
never modifies live loans, repayments, products, or existing customer details.
The settings marker makes the operation safe to repeat on service restarts.
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
    LegacyPortfolioLoan,
    SessionLocal,
    Setting,
    User,
)


MARKER = "workbook_entire_import_from_supabase_v1"
CUSTOMER_FIELDS = (
    "full_name",
    "national_id",
    "phone",
    "location",
    "next_of_kin",
    "guarantors",
    "occupation",
    "monthly_income_cents",
    "deleted",
    "organization_id",
    "branch_id",
    "created_at",
)
SNAPSHOT_FIELDS = (
    "source_key",
    "source_sheet",
    "source_row",
    "source_date",
    "source_phone",
    "principal_cents",
    "total_due_cents",
    "balance_cents",
    "balance_formula",
    "balance_is_formula",
    "last_payment",
    "guarantor",
    "guarantor_phone",
    "organization_id",
    "branch_id",
    "created_at",
)


def source_url() -> str:
    raw = os.environ.get("SUPABASE_DATABASE_URL", "").strip()
    if not raw:
        raise RuntimeError("SUPABASE_DATABASE_URL is required for the one-time import")
    if raw.startswith("postgres://"):
        return "postgresql+psycopg://" + raw.removeprefix("postgres://")
    if raw.startswith("postgresql://"):
        return "postgresql+psycopg://" + raw.removeprefix("postgresql://")
    if not raw.startswith("postgresql+psycopg://"):
        raise RuntimeError("SUPABASE_DATABASE_URL must be a PostgreSQL URL")
    return raw


def matching_customer(db, row):
    scope = Customer.organization_id == row["organization_id"]
    if row["national_id"]:
        customer = db.scalar(select(Customer).where(scope, Customer.national_id == row["national_id"]))
        if customer:
            return customer
    if row["phone"]:
        customer = db.scalar(select(Customer).where(scope, Customer.phone == row["phone"]))
        if customer:
            return customer
    # A small part of the workbook has neither a phone nor a national ID.
    # Match only an unambiguous exact name/location pair to avoid duplicates.
    if not row["national_id"] and not row["phone"]:
        matches = db.scalars(
            select(Customer).where(
                scope,
                Customer.full_name == row["full_name"],
                Customer.location == row["location"],
            ).limit(2)
        ).all()
        if len(matches) == 1:
            return matches[0]
    return None


def main() -> None:
    source_engine = create_engine(source_url(), pool_pre_ping=True)
    added_customers = matched_customers = added_snapshots = existing_snapshots = 0
    try:
        with source_engine.connect().execution_options(isolation_level="REPEATABLE READ") as source:
            source_customers = source.execute(
                select(Customer.__table__).where(Customer.organization_id == 1)
            ).mappings().all()
            source_snapshots = source.execute(
                select(LegacyPortfolioLoan.__table__).where(LegacyPortfolioLoan.organization_id == 1)
            ).mappings().all()

        if not source_customers or not source_snapshots:
            raise RuntimeError("The source database does not contain the expected workbook records")

        with SessionLocal() as db, db.begin():
            if db.scalar(select(Setting.id).where(Setting.key == MARKER).limit(1)):
                print("Workbook portfolio import already completed; no changes made.")
                return

            id_map: dict[int, int] = {}
            for row in source_customers:
                target = matching_customer(db, row)
                if target is None:
                    target = Customer(**{field: row[field] for field in CUSTOMER_FIELDS})
                    db.add(target)
                    db.flush()
                    added_customers += 1
                else:
                    # Restore a matched portfolio customer if it was soft-deleted.
                    if target.deleted:
                        target.deleted = False
                    matched_customers += 1
                id_map[row["id"]] = target.id

            for row in source_snapshots:
                if row["customer_id"] not in id_map:
                    raise RuntimeError("A portfolio snapshot has no matching source customer")
                exists = db.scalar(
                    select(LegacyPortfolioLoan.id).where(
                        LegacyPortfolioLoan.organization_id == row["organization_id"],
                        LegacyPortfolioLoan.source_key == row["source_key"],
                    ).limit(1)
                )
                if exists:
                    existing_snapshots += 1
                    continue
                values = {field: row[field] for field in SNAPSHOT_FIELDS}
                values["customer_id"] = id_map[row["customer_id"]]
                db.add(LegacyPortfolioLoan(**values))
                added_snapshots += 1

            actor_id = db.scalar(select(User.id).where(User.role == "admin").order_by(User.id).limit(1))
            if actor_id is not None:
                db.add(
                    AuditLog(
                        actor_id=actor_id,
                        entity="legacy_portfolio",
                        entity_id=0,
                        action="import",
                        details=f"Supabase Entire workbook merge: customers_added={added_customers}; customers_matched={matched_customers}; snapshots_added={added_snapshots}; snapshots_existing={existing_snapshots}",
                        organization_id=1,
                        branch_id=1,
                    )
                )
            db.add(Setting(key=MARKER, value="completed", organization_id=1, branch_id=1))

        print(
            "Workbook portfolio import completed: "
            f"customers_added={added_customers}, customers_matched={matched_customers}, "
            f"snapshots_added={added_snapshots}, snapshots_existing={existing_snapshots}."
        )
    finally:
        source_engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Workbook portfolio import failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)

"""Small in-process daily job runner. Replace the runner with a queue worker later."""
from datetime import date
from sqlalchemy import select
from app.main import SessionLocal, Loan, LoanStatus, Installment, LoanProduct, LedgerEntry, daily_penalty_cents, emit_event

def assess_daily_penalties(today:date|None=None):
    today=today or date.today(); created=0
    with SessionLocal() as db:
        rows=db.execute(select(Loan,Installment,LoanProduct).join(Installment,Installment.loan_id==Loan.id).join(LoanProduct,Loan.product_id==LoanProduct.id).where(Loan.status==LoanStatus.active,Installment.due_date<today)).all()
        for loan,installment,product in rows:
            amount=daily_penalty_cents(installment.due_date,today,product.penalty_daily_cents,product.grace_days)
            if not amount: continue
            # One daily posting per loan and due installment is idempotent.
            description=f"Daily penalty installment {installment.id} {today.isoformat()}"
            exists=db.scalar(select(LedgerEntry.id).where(LedgerEntry.loan_id==loan.id,LedgerEntry.account=="penalty_receivable",LedgerEntry.description==description))
            if exists: continue
            from uuid import uuid4
            transaction_id=str(uuid4())
            db.add(LedgerEntry(loan_id=loan.id,transaction_id=transaction_id,account="penalty_receivable",debit_cents=amount,organization_id=loan.organization_id,branch_id=loan.branch_id,description=description))
            db.add(LedgerEntry(loan_id=loan.id,transaction_id=transaction_id,account="penalty_income",credit_cents=amount,organization_id=loan.organization_id,branch_id=loan.branch_id,description=description))
            emit_event("LoanOverdue",{"loan_id":loan.id,"installment_id":installment.id}); created+=1
        db.commit()
    return created

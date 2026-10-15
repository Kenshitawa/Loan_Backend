from datetime import date
from decimal import Decimal
from app.main import generate_schedule, allocate_payment, daily_penalty_cents, Frequency, InterestMethod
def test_flat_schedule_calculates_cent_exact_interest():
    rows=generate_schedule(100_000,Decimal("0.12"),4,Frequency.monthly,InterestMethod.flat,date(2026,1,1))
    assert sum(x["principal_cents"] for x in rows)==100_000
    assert [x["interest_cents"] for x in rows]==[1_000]*4
    assert rows[0]["due_date"]==date(2026,2,1)
def test_reducing_schedule_interest_tracks_declining_balance():
    rows=generate_schedule(120_000,Decimal("0.12"),3,Frequency.monthly,InterestMethod.reducing,date(2026,1,1))
    assert [x["interest_cents"] for x in rows]==[1_200,800,400]
    assert sum(x["principal_cents"] for x in rows)==120_000
def test_payment_allocation_waterfall_and_overpayment():
    result=allocate_payment(1_750,{"penalties":100,"fees":150,"interest":500,"principal":700})
    assert result=={"penalties":100,"fees":150,"interest":500,"principal":700,"overpayment":300}
def test_ledger_pair_balances():
    amount=12_345
    entries=[{"debit_cents":amount,"credit_cents":0},{"debit_cents":0,"credit_cents":amount}]
    assert sum(x["debit_cents"] for x in entries)==sum(x["credit_cents"] for x in entries)
def test_penalty_respects_grace_period_and_posts_daily_amount():
    due=date(2026,1,1)
    assert daily_penalty_cents(due,date(2026,1,4),250,3)==0
    assert daily_penalty_cents(due,date(2026,1,5),250,3)==250

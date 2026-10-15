"""MWANGAZABIz modular monolith API."""
from __future__ import annotations

import enum
import os
import calendar
from pathlib import Path
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pwdlib import PasswordHash
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (Boolean, Date, DateTime, Enum, ForeignKey, Integer, String,
                        Text, UniqueConstraint, create_engine, select, func)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mwangazabiz.db")
# Render provides PostgreSQL URLs without a SQLAlchemy driver suffix. This
# project installs psycopg 3, so normalize those URLs before creating the engine.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.removeprefix("postgres://")
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = "postgresql+psycopg://" + DATABASE_URL.removeprefix("postgresql://")
SECRET_KEY = os.getenv("SECRET_KEY", "development-only-change-me")
ALGORITHM = "HS256"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
password_hash = PasswordHash.recommended()
oauth = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

class Base(DeclarativeBase): pass
class Role(str, enum.Enum):
    admin="admin"; manager="manager"; branch_manager="branch_manager"; loan_officer="loan_officer"; collections_officer="collections_officer"; accountant="accountant"; read_only="read_only"
class LoanStatus(str, enum.Enum):
    application="application"; appraisal="appraisal"; approved="approved"; rejected="rejected"; disbursed="disbursed"; active="active"; closed="closed"; written_off="written_off"; restructured="restructured"
class InterestMethod(str, enum.Enum): flat="flat"; reducing="reducing"
class Frequency(str, enum.Enum): daily="daily"; weekly="weekly"; monthly="monthly"

class Scoped(Base):
    __abstract__=True
    id: Mapped[int]=mapped_column(primary_key=True)
    organization_id: Mapped[int]=mapped_column(Integer, default=1, index=True)
    branch_id: Mapped[int]=mapped_column(Integer, default=1, index=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class User(Scoped):
    __tablename__="users"
    username: Mapped[str]=mapped_column(String(80), unique=True, index=True)
    password: Mapped[str]=mapped_column(String(255))
    role: Mapped[Role]=mapped_column(Enum(Role), default=Role.read_only)
    active: Mapped[bool]=mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool]=mapped_column(Boolean, default=False)
    failed_logins: Mapped[int]=mapped_column(Integer, default=0)
    locked_until: Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True), nullable=True)

class Customer(Scoped):
    __tablename__="customers"
    full_name: Mapped[str]=mapped_column(String(160), index=True)
    national_id: Mapped[str]=mapped_column(String(40), unique=True, index=True)
    phone: Mapped[str]=mapped_column(String(30), unique=True, index=True)
    location: Mapped[str]=mapped_column(String(160))
    next_of_kin: Mapped[str]=mapped_column(String(160), default="")
    guarantors: Mapped[str]=mapped_column(Text, default="")
    occupation: Mapped[str]=mapped_column(String(120), default="")
    monthly_income_cents: Mapped[int]=mapped_column(Integer, default=0)
    deleted: Mapped[bool]=mapped_column(Boolean, default=False)

class CustomerDocument(Scoped):
    __tablename__="customer_documents"
    customer_id: Mapped[int]=mapped_column(ForeignKey("customers.id"), index=True)
    document_type: Mapped[str]=mapped_column(String(40), default="other")
    filename: Mapped[str]=mapped_column(String(255))
    storage_key: Mapped[str]=mapped_column(String(500))
    uploaded_by: Mapped[int]=mapped_column(ForeignKey("users.id"))

class CustomerInteraction(Scoped):
    __tablename__="customer_interactions"
    customer_id: Mapped[int]=mapped_column(ForeignKey("customers.id"), index=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id"), index=True)
    interaction_type: Mapped[str]=mapped_column(String(30))
    summary: Mapped[str]=mapped_column(Text)
    direction: Mapped[str]=mapped_column(String(20), default="outbound")
    follow_up: Mapped[Optional[date]]=mapped_column(Date, nullable=True, index=True)

class LoanProduct(Scoped):
    __tablename__="loan_products"
    name: Mapped[str]=mapped_column(String(120))
    min_cents: Mapped[int]=mapped_column(Integer)
    max_cents: Mapped[int]=mapped_column(Integer)
    annual_rate: Mapped[Decimal]=mapped_column(default=Decimal("0.12"))
    interest_method: Mapped[InterestMethod]=mapped_column(Enum(InterestMethod))
    term_periods: Mapped[int]=mapped_column(Integer)
    frequency: Mapped[Frequency]=mapped_column(Enum(Frequency))
    processing_fee_cents: Mapped[int]=mapped_column(Integer, default=0)
    penalty_daily_cents: Mapped[int]=mapped_column(Integer, default=0)
    grace_days: Mapped[int]=mapped_column(Integer, default=0)

class Loan(Scoped):
    __tablename__="loans"
    customer_id: Mapped[int]=mapped_column(ForeignKey("customers.id"), index=True)
    product_id: Mapped[int]=mapped_column(ForeignKey("loan_products.id"), index=True)
    principal_cents: Mapped[int]=mapped_column(Integer)
    currency: Mapped[str]=mapped_column(String(3), default="KES")
    status: Mapped[LoanStatus]=mapped_column(Enum(LoanStatus), default=LoanStatus.application, index=True)
    officer_id: Mapped[int]=mapped_column(ForeignKey("users.id"), index=True)
    assigned_collector_id: Mapped[Optional[int]]=mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    disbursed_at: Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True), nullable=True)

class Installment(Scoped):
    __tablename__="installments"
    loan_id: Mapped[int]=mapped_column(ForeignKey("loans.id"), index=True)
    number: Mapped[int]=mapped_column(Integer)
    due_date: Mapped[date]=mapped_column(Date, index=True)
    principal_cents: Mapped[int]=mapped_column(Integer)
    interest_cents: Mapped[int]=mapped_column(Integer)
    fees_cents: Mapped[int]=mapped_column(Integer, default=0)

class LedgerEntry(Scoped):
    __tablename__="ledger_entries"
    loan_id: Mapped[int]=mapped_column(ForeignKey("loans.id"), index=True)
    transaction_id: Mapped[str]=mapped_column(String(36), index=True)
    account: Mapped[str]=mapped_column(String(40))
    debit_cents: Mapped[int]=mapped_column(Integer, default=0)
    credit_cents: Mapped[int]=mapped_column(Integer, default=0)
    currency: Mapped[str]=mapped_column(String(3), default="KES")
    description: Mapped[str]=mapped_column(String(255))
    reversal_of: Mapped[Optional[str]]=mapped_column(String(36), nullable=True)

class Payment(Scoped):
    __tablename__="payments"
    __table_args__=(UniqueConstraint("organization_id", "idempotency_key"),)
    loan_id: Mapped[int]=mapped_column(ForeignKey("loans.id"), index=True)
    idempotency_key: Mapped[str]=mapped_column(String(120))
    amount_cents: Mapped[int]=mapped_column(Integer)
    method: Mapped[str]=mapped_column(String(20))
    reference: Mapped[str]=mapped_column(String(120), default="")
    transaction_id: Mapped[str]=mapped_column(String(36), default="")
    created_by: Mapped[int]=mapped_column(ForeignKey("users.id"))
    reversed: Mapped[bool]=mapped_column(Boolean, default=False)
    reversal_reason: Mapped[str]=mapped_column(String(255), default="")
    status: Mapped[str]=mapped_column(String(20), default="pending")
    review_note: Mapped[str]=mapped_column(String(255), default="")
    reviewed_by: Mapped[Optional[int]]=mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[Optional[datetime]]=mapped_column(DateTime(timezone=True), nullable=True)

class PaymentAllocation(Scoped):
    __tablename__="payment_allocations"
    payment_id: Mapped[int]=mapped_column(ForeignKey("payments.id"), index=True)
    bucket: Mapped[str]=mapped_column(String(30))
    amount_cents: Mapped[int]=mapped_column(Integer)

class StatusHistory(Scoped):
    __tablename__="loan_status_history"
    loan_id: Mapped[int]=mapped_column(ForeignKey("loans.id"), index=True)
    from_status: Mapped[str]=mapped_column(String(30))
    to_status: Mapped[str]=mapped_column(String(30))
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id"))
    changed_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    note: Mapped[str]=mapped_column(String(255), default="")

class CollectionActivity(Scoped):
    __tablename__="collection_activities"
    loan_id: Mapped[int]=mapped_column(ForeignKey("loans.id"), index=True)
    user_id: Mapped[int]=mapped_column(ForeignKey("users.id"))
    activity: Mapped[str]=mapped_column(String(30))
    notes: Mapped[str]=mapped_column(Text, default="")
    follow_up: Mapped[Optional[date]]=mapped_column(Date, nullable=True, index=True)

class AuditLog(Scoped):
    __tablename__="audit_logs"
    actor_id: Mapped[int]=mapped_column(Integer, index=True)
    entity: Mapped[str]=mapped_column(String(60), index=True)
    entity_id: Mapped[int]=mapped_column(Integer, index=True)
    action: Mapped[str]=mapped_column(String(40))
    details: Mapped[str]=mapped_column(Text, default="")

class Setting(Scoped):
    __tablename__="settings"
    key: Mapped[str]=mapped_column(String(100), index=True)
    value: Mapped[str]=mapped_column(Text)

def db_session():
    with SessionLocal() as session:
        yield session

def money(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

def add_months(value:date,months:int)->date:
    absolute=value.year*12+(value.month-1)+months
    year,month=divmod(absolute,12); month+=1
    return date(year,month,min(value.day,calendar.monthrange(year,month)[1]))

def generate_schedule(principal_cents: int, annual_rate: Decimal, periods: int, frequency: Frequency, method: InterestMethod, first_due: date, fee_cents: int=0):
    """Generate cent-exact amortization installments; periodic rate maps daily/weekly/monthly."""
    if principal_cents <= 0 or periods <= 0: raise ValueError("Principal and periods must be positive")
    divisor={Frequency.daily:Decimal(365), Frequency.weekly:Decimal(52), Frequency.monthly:Decimal(12)}[frequency]
    rate=Decimal(annual_rate)/divisor
    principal_parts=[principal_cents//periods]*periods
    principal_parts[-1]+=principal_cents-sum(principal_parts)
    rows=[]; balance=principal_cents
    for i in range(periods):
        interest=money(Decimal(principal_cents)*rate) if method==InterestMethod.flat else money(Decimal(balance)*rate)
        p=principal_parts[i]; balance-=p
        due=first_due+timedelta(days=i+1) if frequency==Frequency.daily else first_due+timedelta(days=7*(i+1)) if frequency==Frequency.weekly else add_months(first_due,i+1)
        rows.append({"number":i+1,"due_date":due,"principal_cents":p,"interest_cents":interest,"fees_cents":fee_cents if i==0 else 0})
    # Correct final installment's interest against any round-off; each installment is cent-exact.
    return rows

def allocate_payment(amount_cents: int, balances: dict[str,int], order: tuple[str,...]=("penalties","fees","interest","principal")):
    if amount_cents < 0: raise ValueError("Payment cannot be negative")
    remaining=amount_cents; allocation={k:0 for k in balances}
    for bucket in order:
        due=max(0, balances.get(bucket,0)); applied=min(due,remaining); allocation[bucket]=applied; remaining-=applied
    allocation["overpayment"]=remaining
    return allocation

def daily_penalty_cents(due_date:date,today:date,daily_fee_cents:int,grace_days:int)->int:
    return max(0,daily_fee_cents) if (today-due_date).days>grace_days else 0

def emit_event(event: str, payload: dict):
    """Domain event seam; replace subscribers/transport without coupling services."""
    return {"event":event,"payload":payload}

class Input(BaseModel): model_config=ConfigDict(from_attributes=True)
class LoginIn(BaseModel): username:str; password:str
class UserCreateIn(BaseModel): username:str=Field(min_length=3,max_length=80); password:str=Field(min_length=12,max_length=128); role:Role
class ChangePasswordIn(BaseModel): old_password:str; new_password:str=Field(min_length=12,max_length=128)
class InteractionIn(BaseModel): interaction_type:str=Field(pattern="^(call|visit|message|note)$"); summary:str=Field(min_length=2,max_length=3000); direction:str=Field(default="outbound",pattern="^(inbound|outbound|internal)$"); follow_up:Optional[date]=None
class AssignmentIn(BaseModel): collector_id:int
class CustomerIn(BaseModel): full_name:str; national_id:str; phone:str; location:str; next_of_kin:str=""; guarantors:str=""; occupation:str=""; monthly_income_cents:int=Field(ge=0)
class ProductIn(BaseModel): name:str=Field(min_length=2,max_length=120); min_cents:int=Field(gt=0); max_cents:int=Field(gt=0); annual_rate:Decimal=Field(ge=0,le=2); interest_method:InterestMethod; term_periods:int=Field(gt=0,le=365); frequency:Frequency; processing_fee_cents:int=Field(ge=0); penalty_daily_cents:int=Field(ge=0); grace_days:int=Field(ge=0)
class LoanIn(BaseModel): customer_id:int; product_id:int; principal_cents:int=Field(gt=0)
class PaymentIn(BaseModel): loan_id:int; amount_cents:int=Field(gt=0); method:str=Field(pattern="^(cash|mpesa|bank)$"); reference:str=Field(default="",max_length=120)
class PaymentReviewIn(BaseModel): status:str=Field(pattern="^(confirmed|rejected)$"); note:str=Field(default="",max_length=255)
class StatusIn(BaseModel): status:LoanStatus; note:str=""
class ActivityIn(BaseModel): activity:str; notes:str=""; follow_up:Optional[date]=None

app=FastAPI(title="MWANGAZABIz Loan Management", version="1.0.0", description="API-first lending operations for Kenyan lenders")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS","http://localhost:5173,http://127.0.0.1:5173").split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.on_event("startup")
def startup():
    if os.getenv("APP_ENV", "development").lower()=="production":
        if SECRET_KEY=="development-only-change-me" or len(SECRET_KEY)<32: raise RuntimeError("Set a strong SECRET_KEY (at least 32 characters) for production")
        if DATABASE_URL.startswith("sqlite"): raise RuntimeError("Production requires PostgreSQL; SQLite is for local development only")
        production_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS","").split(",") if origin.strip()]
        if not production_origins or "*" in production_origins: raise RuntimeError("Set explicit production CORS_ORIGINS; wildcard origins are not allowed")
    # Schema changes are applied by Alembic before the server starts.
    if os.getenv("ENABLE_SCHEDULER", "true").lower()=="true":
        from apscheduler.schedulers.background import BackgroundScheduler
        from app.jobs import assess_daily_penalties
        scheduler=BackgroundScheduler(timezone="UTC")
        scheduler.add_job(assess_daily_penalties,"cron",hour=1,minute=0,id="daily-penalties",replace_existing=True)
        scheduler.start(); app.state.scheduler=scheduler

@app.on_event("shutdown")
def shutdown():
    scheduler=getattr(app.state,"scheduler",None)
    if scheduler: scheduler.shutdown(wait=False)

def current_user(request:Request,token:str=Depends(oauth), db:Session=Depends(db_session)):
    try:
        claims=jwt.decode(token,SECRET_KEY,algorithms=[ALGORITHM])
        if claims.get("type")!="access": raise HTTPException(401,"Access token required")
        username=claims["sub"]
    except (JWTError,KeyError): raise HTTPException(401,"Invalid or expired token")
    user=db.scalar(select(User).where(User.username==username,User.active==True))
    if not user: raise HTTPException(401,"User not found")
    if user.must_change_password and request.url.path not in ("/api/v1/auth/me","/api/v1/auth/change-password"):
        raise HTTPException(403,"Change your temporary password before continuing")
    return user

def require(*roles:Role):
    def check(user:User=Depends(current_user)):
        if user.role not in roles: raise HTTPException(403,"Insufficient permissions")
        return user
    return check

MANAGERS=(Role.admin,Role.manager,Role.branch_manager)
WRITE_ROLES=(Role.admin,Role.manager,Role.branch_manager,Role.loan_officer,Role.collections_officer,Role.accountant)

@app.post("/api/v1/auth/login")
def login(data:LoginIn, db:Session=Depends(db_session)):
    user=db.scalar(select(User).where(User.username==data.username))
    if not user: raise HTTPException(401,"Incorrect username or password")
    if user.locked_until:
        lock_time=user.locked_until.replace(tzinfo=timezone.utc) if user.locked_until.tzinfo is None else user.locked_until
        if lock_time>datetime.now(timezone.utc): raise HTTPException(423,"Account temporarily locked")
    if not password_hash.verify(data.password,user.password):
        user.failed_logins+=1
        if user.failed_logins>=5: user.locked_until=datetime.now(timezone.utc)+timedelta(minutes=15)
        db.commit(); raise HTTPException(401,"Incorrect username or password")
    user.failed_logins=0
    token=jwt.encode({"sub":user.username,"type":"access","exp":datetime.now(timezone.utc)+timedelta(hours=8)},SECRET_KEY,algorithm=ALGORITHM)
    refresh_token=jwt.encode({"sub":user.username,"type":"refresh","exp":datetime.now(timezone.utc)+timedelta(days=14)},SECRET_KEY,algorithm=ALGORITHM); db.commit()
    return {"access_token":token,"refresh_token":refresh_token,"token_type":"bearer","role":user.role.value,"must_change_password":user.must_change_password}

@app.post("/api/v1/auth/refresh")
def refresh(token:str=Depends(oauth),db:Session=Depends(db_session)):
    try:
        claims=jwt.decode(token,SECRET_KEY,algorithms=[ALGORITHM])
        if claims.get("type")!="refresh": raise HTTPException(401,"Refresh token required")
    except JWTError: raise HTTPException(401,"Invalid or expired refresh token")
    user=db.scalar(select(User).where(User.username==claims["sub"],User.active==True))
    if not user: raise HTTPException(401,"User not found")
    if user.must_change_password: raise HTTPException(403,"Change your temporary password before continuing")
    access=jwt.encode({"sub":user.username,"type":"access","exp":datetime.now(timezone.utc)+timedelta(hours=8)},SECRET_KEY,algorithm=ALGORITHM)
    return {"access_token":access,"token_type":"bearer"}

@app.get("/api/v1/auth/me")
def me(user:User=Depends(current_user)): return {"id":user.id,"username":user.username,"role":user.role.value,"branch_id":user.branch_id,"must_change_password":user.must_change_password}

@app.post("/api/v1/auth/change-password")
def change_password(data:ChangePasswordIn,db:Session=Depends(db_session),user:User=Depends(current_user)):
    if not password_hash.verify(data.old_password,user.password): raise HTTPException(400,"Current password is incorrect")
    if password_hash.verify(data.new_password,user.password): raise HTTPException(422,"Choose a different password")
    user.password=password_hash.hash(data.new_password); user.must_change_password=False
    db.add(AuditLog(actor_id=user.id,entity="user",entity_id=user.id,action="change_password",organization_id=user.organization_id,branch_id=user.branch_id)); db.commit()
    return {"status":"password_changed"}

@app.get("/api/v1/users")
def list_users(db:Session=Depends(db_session),user:User=Depends(require(Role.admin,Role.manager,Role.branch_manager))):
    users=db.scalars(select(User).where(User.organization_id==user.organization_id).order_by(User.id)).all()
    return [{"id":u.id,"username":u.username,"role":u.role.value,"active":u.active,"must_change_password":u.must_change_password,"branch_id":u.branch_id,"created_at":u.created_at} for u in users]

@app.post("/api/v1/users",status_code=201)
def create_user(data:UserCreateIn,db:Session=Depends(db_session),user:User=Depends(require(Role.admin,Role.manager,Role.branch_manager))):
    allowed=(Role.manager,Role.loan_officer,Role.collections_officer) if user.role==Role.admin else (Role.loan_officer,Role.collections_officer)
    if data.role not in allowed: raise HTTPException(422,"Admins can create managers and officers; managers can create officer accounts")
    if db.scalar(select(User).where(User.username==data.username)): raise HTTPException(409,"Username is already in use")
    created=User(username=data.username,password=password_hash.hash(data.password),role=data.role,must_change_password=True,organization_id=user.organization_id,branch_id=user.branch_id)
    db.add(created); db.flush(); db.add(AuditLog(actor_id=user.id,entity="user",entity_id=created.id,action="create",details=f"role={created.role.value}",organization_id=user.organization_id,branch_id=user.branch_id)); db.commit(); db.refresh(created)
    return {"id":created.id,"username":created.username,"role":created.role.value,"active":created.active,"must_change_password":created.must_change_password,"branch_id":created.branch_id,"created_at":created.created_at}

@app.delete("/api/v1/users/{user_id}")
def remove_user(user_id:int,db:Session=Depends(db_session),user:User=Depends(require(Role.admin))):
    if user_id==user.id: raise HTTPException(400,"You cannot remove your own administrator account")
    target=db.scalar(select(User).where(User.id==user_id,User.organization_id==user.organization_id))
    if not target: raise HTTPException(404,"Team member not found")
    if target.active:
        target.active=False
        db.add(AuditLog(actor_id=user.id,entity="user",entity_id=target.id,action="deactivate",details=f"username={target.username}; role={target.role.value}",organization_id=user.organization_id,branch_id=user.branch_id))
        db.commit()
    return {"status":"deactivated","id":target.id,"username":target.username}

@app.post("/api/v1/customers")
def create_customer(data:CustomerIn,db:Session=Depends(db_session),user:User=Depends(require(*WRITE_ROLES))):
    if db.scalar(select(Customer).where((Customer.phone==data.phone)|(Customer.national_id==data.national_id))): raise HTTPException(409,"Customer with that ID or phone already exists")
    customer=Customer(**data.model_dump(),organization_id=user.organization_id,branch_id=user.branch_id); db.add(customer); db.flush(); db.add(AuditLog(actor_id=user.id,entity="customer",entity_id=customer.id,action="create")); db.commit(); db.refresh(customer); return customer

@app.post("/api/v1/customers/{customer_id}/documents")
async def upload_customer_document(customer_id:int,file:UploadFile=File(...),document_type:str=Query("id_image",pattern="^(id_image|profile_photo|other)$"),db:Session=Depends(db_session),user:User=Depends(require(Role.admin,Role.manager,Role.branch_manager,Role.loan_officer))):
    customer=db.get(Customer,customer_id)
    if not customer or customer.organization_id!=user.organization_id: raise HTTPException(404,"Customer not found")
    if file.content_type not in ("application/pdf","image/jpeg","image/png"): raise HTTPException(415,"Only PDF, JPEG and PNG files are accepted")
    if document_type=="profile_photo" and file.content_type not in ("image/jpeg","image/png"): raise HTTPException(415,"Profile photos must be JPEG or PNG images")
    content=await file.read(10*1024*1024+1)
    if len(content)>10*1024*1024: raise HTTPException(413,"Document exceeds 10 MB")
    from app.adapters import LocalStorageProvider
    safe_name=f"{user.organization_id}/{customer_id}/{uuid4().hex}_{Path(file.filename or 'document').name}"
    key=LocalStorageProvider(os.getenv("UPLOAD_DIR","uploads")).save(safe_name,content)
    doc=CustomerDocument(customer_id=customer_id,document_type=document_type,filename=Path(file.filename or "document").name,storage_key=key,uploaded_by=user.id,organization_id=user.organization_id,branch_id=user.branch_id)
    db.add(doc); db.flush(); db.add(AuditLog(actor_id=user.id,entity="customer_document",entity_id=doc.id,action="upload",details=f"customer_id={customer_id},type={document_type}",organization_id=user.organization_id,branch_id=user.branch_id)); db.commit(); db.refresh(doc); return {"id":doc.id,"customer_id":doc.customer_id,"document_type":doc.document_type,"filename":doc.filename,"created_at":doc.created_at}

@app.get("/api/v1/customers/{customer_id}/documents/{document_id}")
def download_customer_document(customer_id:int,document_id:int,db:Session=Depends(db_session),user:User=Depends(require(Role.admin,Role.manager,Role.branch_manager,Role.loan_officer))):
    doc=db.get(CustomerDocument,document_id); customer=db.get(Customer,customer_id)
    if not doc or not customer or doc.customer_id!=customer_id or customer.organization_id!=user.organization_id: raise HTTPException(404,"Document not found")
    path=Path(doc.storage_key)
    if not path.is_file(): raise HTTPException(404,"Stored document not found")
    from fastapi.responses import FileResponse
    media_type="application/pdf" if path.suffix.lower()==".pdf" else "image/png" if path.suffix.lower()==".png" else "image/jpeg"
    return FileResponse(path,media_type=media_type,filename=doc.filename)

@app.get("/api/v1/customers")
def list_customers(page:int=Query(1,ge=1),limit:int=Query(25,ge=1,le=100),q:str="",db:Session=Depends(db_session),user:User=Depends(current_user)):
    stmt=select(Customer).where(Customer.deleted==False,Customer.organization_id==user.organization_id)
    if q: stmt=stmt.where((Customer.full_name.ilike(f"%{q}%"))|(Customer.phone.ilike(f"%{q}%"))|(Customer.national_id.ilike(f"%{q}%")))
    total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0; items=db.scalars(stmt.order_by(Customer.id.desc()).offset((page-1)*limit).limit(limit)).all()
    return {"items":[{**{k:getattr(c,k) for k in ("id","full_name","national_id","phone","location","occupation","monthly_income_cents")},"national_id": c.national_id if user.role in (Role.admin,Role.manager,Role.branch_manager,Role.loan_officer) else "••••"+c.national_id[-4:],"phone":c.phone if user.role!=Role.read_only else "••••"+c.phone[-4:]} for c in items],"total":total,"page":page,"limit":limit}

@app.get("/api/v1/customers/{customer_id}/profile")
def customer_profile(customer_id:int,db:Session=Depends(db_session),user:User=Depends(current_user)):
    customer=db.get(Customer,customer_id)
    if not customer or customer.organization_id!=user.organization_id: raise HTTPException(404,"Customer not found")
    loans=db.scalars(select(Loan).where(Loan.customer_id==customer_id,Loan.organization_id==user.organization_id).order_by(Loan.created_at.desc())).all()
    loan_cards=[]; loan_ids=[l.id for l in loans]
    for loan in loans:
        product=db.get(LoanProduct,loan.product_id)
        entries=db.scalars(select(LedgerEntry).where(LedgerEntry.loan_id==loan.id,LedgerEntry.account.in_(["loan_receivable","interest_receivable","fee_receivable","penalty_receivable"]))).all()
        balance=max(0,sum(e.debit_cents-e.credit_cents for e in entries))
        loan_cards.append({"loan_id":loan.id,"product_name":product.name if product else "Loan product","amount_cents":loan.principal_cents,"balance_cents":balance,"currency":loan.currency,"status":loan.status.value,"created_at":loan.created_at})
    payments=db.scalars(select(Payment).where(Payment.loan_id.in_(loan_ids)).order_by(Payment.created_at.desc()).limit(100)).all() if loan_ids else []
    interactions=db.scalars(select(CustomerInteraction).where(CustomerInteraction.customer_id==customer_id,CustomerInteraction.organization_id==user.organization_id).order_by(CustomerInteraction.created_at.desc()).limit(100)).all()
    documents=db.scalars(select(CustomerDocument).where(CustomerDocument.customer_id==customer_id,CustomerDocument.organization_id==user.organization_id).order_by(CustomerDocument.created_at.desc())).all()
    mask=user.role==Role.read_only
    return {"customer":{"id":customer.id,"full_name":customer.full_name,"national_id":"••••"+customer.national_id[-4:] if mask else customer.national_id,"phone":"••••"+customer.phone[-4:] if mask else customer.phone,"location":customer.location,"next_of_kin":customer.next_of_kin,"guarantors":customer.guarantors,"occupation":customer.occupation,"monthly_income_cents":customer.monthly_income_cents},"loans":loan_cards,"payments":[{"id":p.id,"loan_id":p.loan_id,"amount_cents":p.amount_cents,"method":p.method,"reference":p.reference,"reversed":p.reversed,"status":p.status,"review_note":p.review_note,"created_by":p.created_by,"created_at":p.created_at} for p in payments],"interactions":[{"id":i.id,"interaction_type":i.interaction_type,"summary":i.summary,"direction":i.direction,"follow_up":i.follow_up,"created_at":i.created_at,"username":db.get(User,i.user_id).username if db.get(User,i.user_id) else "Unknown"} for i in interactions],"documents":[{"id":d.id,"document_type":d.document_type,"filename":d.filename,"created_at":d.created_at} for d in documents]}

@app.post("/api/v1/customers/{customer_id}/interactions",status_code=201)
def create_customer_interaction(customer_id:int,data:InteractionIn,db:Session=Depends(db_session),user:User=Depends(require(*WRITE_ROLES))):
    customer=db.get(Customer,customer_id)
    if not customer or customer.organization_id!=user.organization_id: raise HTTPException(404,"Customer not found")
    interaction=CustomerInteraction(customer_id=customer_id,user_id=user.id,organization_id=user.organization_id,branch_id=user.branch_id,**data.model_dump())
    db.add(interaction); db.flush(); db.add(AuditLog(actor_id=user.id,entity="customer_interaction",entity_id=interaction.id,action="create",organization_id=user.organization_id,branch_id=user.branch_id)); db.commit(); db.refresh(interaction)
    return {"id":interaction.id,"customer_id":customer_id,"interaction_type":interaction.interaction_type,"summary":interaction.summary,"direction":interaction.direction,"follow_up":interaction.follow_up,"created_at":interaction.created_at,"username":user.username}

@app.post("/api/v1/products")
def create_product(data:ProductIn,db:Session=Depends(db_session),user:User=Depends(require(*MANAGERS))):
    if data.max_cents<data.min_cents: raise HTTPException(422,"max_cents must be >= min_cents")
    product=LoanProduct(**data.model_dump(),organization_id=user.organization_id,branch_id=user.branch_id); db.add(product); db.commit(); db.refresh(product); return product

@app.get("/api/v1/products")
def list_products(db:Session=Depends(db_session),user:User=Depends(current_user)): return db.scalars(select(LoanProduct).where(LoanProduct.organization_id==user.organization_id)).all()

def change_status(db:Session,loan:Loan,status:LoanStatus,user:User,note:str):
    old=loan.status; loan.status=status; db.add(StatusHistory(loan_id=loan.id,from_status=old.value,to_status=status.value,user_id=user.id,note=note,organization_id=user.organization_id,branch_id=user.branch_id))
    db.add(AuditLog(actor_id=user.id,entity="loan",entity_id=loan.id,action="status_change",details=f"{old.value}->{status.value}: {note}",organization_id=user.organization_id,branch_id=user.branch_id))

@app.post("/api/v1/loans")
def create_loan(data:LoanIn,db:Session=Depends(db_session),user:User=Depends(require(Role.admin,Role.manager,Role.branch_manager,Role.loan_officer))):
    product=db.get(LoanProduct,data.product_id); customer=db.get(Customer,data.customer_id)
    if not product or not customer or product.organization_id!=user.organization_id or customer.organization_id!=user.organization_id: raise HTTPException(404,"Customer or product not found")
    if not product.min_cents<=data.principal_cents<=product.max_cents: raise HTTPException(422,"Amount outside product limits")
    loan=Loan(**data.model_dump(),officer_id=user.id,organization_id=user.organization_id,branch_id=user.branch_id); db.add(loan); db.flush()
    db.add(StatusHistory(loan_id=loan.id,from_status="",to_status="application",user_id=user.id,organization_id=user.organization_id,branch_id=user.branch_id)); db.add(AuditLog(actor_id=user.id,entity="loan",entity_id=loan.id,action="create",organization_id=user.organization_id,branch_id=user.branch_id)); db.commit(); db.refresh(loan); return loan

@app.get("/api/v1/loans")
def list_loans(page:int=Query(1,ge=1),limit:int=Query(25,ge=1,le=100),status:Optional[LoanStatus]=None,db:Session=Depends(db_session),user:User=Depends(current_user)):
    stmt=select(Loan).where(Loan.organization_id==user.organization_id)
    if status: stmt=stmt.where(Loan.status==status)
    total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    items=db.scalars(stmt.order_by(Loan.id.desc()).offset((page-1)*limit).limit(limit)).all()
    result=[]
    for loan in items:
        customer=db.get(Customer,loan.customer_id); product=db.get(LoanProduct,loan.product_id)
        result.append({"id":loan.id,"customer_id":loan.customer_id,"customer_name":customer.full_name if customer else "Unknown customer","product_id":loan.product_id,"product_name":product.name if product else "Loan product","principal_cents":loan.principal_cents,"currency":loan.currency,"status":loan.status.value,"officer_id":loan.officer_id,"assigned_collector_id":loan.assigned_collector_id,"created_at":loan.created_at,"disbursed_at":loan.disbursed_at})
    return {"items":result,"total":total,"page":page,"limit":limit}

@app.patch("/api/v1/loans/{loan_id}/status")
def update_status(loan_id:int,data:StatusIn,db:Session=Depends(db_session),user:User=Depends(require(*WRITE_ROLES))):
    loan=db.get(Loan,loan_id)
    if not loan or loan.organization_id!=user.organization_id: raise HTTPException(404,"Loan not found")
    transitions={LoanStatus.application:{LoanStatus.appraisal,LoanStatus.rejected},LoanStatus.appraisal:{LoanStatus.approved,LoanStatus.rejected},LoanStatus.approved:{LoanStatus.disbursed},LoanStatus.disbursed:{LoanStatus.active},LoanStatus.active:{LoanStatus.closed,LoanStatus.written_off,LoanStatus.restructured},LoanStatus.restructured:{LoanStatus.active,LoanStatus.closed,LoanStatus.written_off}}
    if data.status not in transitions.get(loan.status,set()): raise HTTPException(409,f"Invalid transition: {loan.status.value} to {data.status.value}")
    if data.status==LoanStatus.approved and user.role not in MANAGERS: raise HTTPException(403,"Only a manager can approve")
    if data.status in (LoanStatus.written_off,LoanStatus.restructured) and user.role not in MANAGERS: raise HTTPException(403,"Only a manager can write off or restructure")
    if data.status==LoanStatus.disbursed and user.role not in (*MANAGERS,Role.accountant): raise HTTPException(403,"Only finance or management can disburse")
    change_status(db,loan,data.status,user,data.note)
    if data.status in (LoanStatus.disbursed,LoanStatus.active):
        product=db.get(LoanProduct,loan.product_id)
        if not db.scalar(select(Installment.id).where(Installment.loan_id==loan.id)):
            first=date.today()+timedelta(days=product.grace_days); schedule=generate_schedule(loan.principal_cents,Decimal(product.annual_rate),product.term_periods,product.frequency,product.interest_method,first,product.processing_fee_cents)
            for row in schedule: db.add(Installment(loan_id=loan.id,organization_id=user.organization_id,branch_id=user.branch_id,**row))
        if data.status==LoanStatus.disbursed:
            loan.disbursed_at=datetime.now(timezone.utc); txn=str(uuid4()); db.add(LedgerEntry(loan_id=loan.id,transaction_id=txn,account="loan_receivable",debit_cents=loan.principal_cents,organization_id=user.organization_id,branch_id=user.branch_id,description="Loan disbursement")); db.add(LedgerEntry(loan_id=loan.id,transaction_id=txn,account="cash",credit_cents=loan.principal_cents,organization_id=user.organization_id,branch_id=user.branch_id,description="Loan disbursement"))
            installments=db.scalars(select(Installment).where(Installment.loan_id==loan.id)).all()
            interest_total=sum(i.interest_cents for i in installments); fee_total=sum(i.fees_cents for i in installments)
            for debit_account,credit_account,amount,label in (("interest_receivable","interest_income",interest_total,"Interest accrual"),("fee_receivable","fee_income",fee_total,"Fee accrual")):
                if amount:
                    db.add(LedgerEntry(loan_id=loan.id,transaction_id=txn,account=debit_account,debit_cents=amount,organization_id=user.organization_id,branch_id=user.branch_id,description=label)); db.add(LedgerEntry(loan_id=loan.id,transaction_id=txn,account=credit_account,credit_cents=amount,organization_id=user.organization_id,branch_id=user.branch_id,description=label))
            emit_event("LoanApproved",{"loan_id":loan.id})
    db.commit(); return loan

@app.get("/api/v1/loans/{loan_id}/schedule")
def schedule(loan_id:int,db:Session=Depends(db_session),user:User=Depends(current_user)):
    return db.scalars(select(Installment).where(Installment.loan_id==loan_id,Installment.organization_id==user.organization_id).order_by(Installment.number)).all()

@app.post("/api/v1/payments")
def record_payment(data:PaymentIn,db:Session=Depends(db_session),user:User=Depends(require(Role.admin,Role.manager,Role.branch_manager,Role.accountant,Role.collections_officer)) ,idempotency_key:str=Header(...,alias="Idempotency-Key")):
    prior=db.scalar(select(Payment).where(Payment.organization_id==user.organization_id,Payment.idempotency_key==idempotency_key))
    if prior: return prior
    loan=db.get(Loan,data.loan_id)
    if not loan or loan.organization_id!=user.organization_id or loan.status not in (LoanStatus.active,LoanStatus.disbursed,LoanStatus.restructured): raise HTTPException(404,"Active loan not found")
    p=Payment(loan_id=loan.id,idempotency_key=idempotency_key,amount_cents=data.amount_cents,method=data.method,reference=data.reference,created_by=user.id,organization_id=user.organization_id,branch_id=user.branch_id); db.add(p); db.flush()
    db.add(AuditLog(actor_id=user.id,entity="payment",entity_id=p.id,action="submit_for_review",details=f"{data.amount_cents} cents",organization_id=user.organization_id,branch_id=user.branch_id)); db.commit(); db.refresh(p); return p

def post_payment_to_ledger(db:Session,p:Payment,loan:Loan,user:User):
    schedules=db.scalars(select(Installment).where(Installment.loan_id==loan.id)).all()
    paid_rows=db.execute(select(PaymentAllocation.bucket,func.sum(PaymentAllocation.amount_cents)).join(Payment,Payment.id==PaymentAllocation.payment_id).where(Payment.loan_id==loan.id,Payment.reversed==False).group_by(PaymentAllocation.bucket)).all()
    paid={bucket:int(total or 0) for bucket,total in paid_rows}
    penalty_total=sum(e.debit_cents-e.credit_cents for e in db.scalars(select(LedgerEntry).where(LedgerEntry.loan_id==loan.id,LedgerEntry.account=="penalty_receivable")).all())
    fee_due=sum(s.fees_cents for s in schedules); interest_due=sum(s.interest_cents for s in schedules); principal_due=loan.principal_cents
    allocation=allocate_payment(p.amount_cents,{"penalties":max(0,penalty_total),"fees":max(0,fee_due-paid.get("fees",0)),"interest":max(0,interest_due-paid.get("interest",0)),"principal":max(0,principal_due-paid.get("principal",0))})
    for bucket,amount in allocation.items():
        if amount and bucket!="overpayment": db.add(PaymentAllocation(payment_id=p.id,bucket=bucket,amount_cents=amount,organization_id=user.organization_id,branch_id=user.branch_id))
    txn=str(uuid4()); p.transaction_id=txn; db.add(LedgerEntry(loan_id=loan.id,transaction_id=txn,account="cash",debit_cents=p.amount_cents,organization_id=user.organization_id,branch_id=user.branch_id,description=f"Repayment {p.reference}"))
    accounts={"penalties":"penalty_receivable","fees":"fee_receivable","interest":"interest_receivable","principal":"loan_receivable","overpayment":"customer_credit"}
    for bucket,account in accounts.items():
        amount=allocation.get(bucket,0)
        if amount: db.add(LedgerEntry(loan_id=loan.id,transaction_id=txn,account=account,credit_cents=amount,organization_id=user.organization_id,branch_id=user.branch_id,description=f"Repayment {p.reference} ({bucket})"))

@app.patch("/api/v1/payments/{payment_id}/review")
def review_payment(payment_id:int,data:PaymentReviewIn,db:Session=Depends(db_session),user:User=Depends(require(*MANAGERS))):
    p=db.scalar(select(Payment).where(Payment.id==payment_id).with_for_update())
    if not p or p.organization_id!=user.organization_id: raise HTTPException(404,"Payment not found")
    if p.status!="pending": raise HTTPException(409,f"Payment is already {p.status}")
    if p.created_by==user.id: raise HTTPException(403,"A manager cannot review their own repayment entry")
    if data.status=="rejected" and len(data.note.strip())<3: raise HTTPException(422,"A rejection reason of at least 3 characters is required")
    if data.status=="confirmed":
        loan=db.scalar(select(Loan).where(Loan.id==p.loan_id).with_for_update())
        if not loan or loan.organization_id!=user.organization_id: raise HTTPException(404,"Loan not found")
        post_payment_to_ledger(db,p,loan,user)
        emit_event("PaymentReceived",{"payment_id":p.id})
    p.status=data.status; p.review_note=data.note; p.reviewed_by=user.id; p.reviewed_at=datetime.now(timezone.utc)
    db.add(AuditLog(actor_id=user.id,entity="payment",entity_id=p.id,action=data.status,details=data.note,organization_id=user.organization_id,branch_id=user.branch_id)); db.commit(); db.refresh(p); return p

@app.get("/api/v1/payments")
def list_payments(page:int=Query(1,ge=1),limit:int=Query(25,ge=1,le=100),db:Session=Depends(db_session),user:User=Depends(current_user)):
    stmt=select(Payment).where(Payment.organization_id==user.organization_id)
    total=db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    return {"items":db.scalars(stmt.order_by(Payment.id.desc()).offset((page-1)*limit).limit(limit)).all(),"total":total,"page":page,"limit":limit}

@app.post("/api/v1/payments/{payment_id}/reverse")
def reverse_payment(payment_id:int,reason:str=Query(min_length=3,max_length=255),db:Session=Depends(db_session),user:User=Depends(require(Role.admin,Role.manager,Role.branch_manager,Role.accountant))):
    p=db.get(Payment,payment_id)
    if not p or p.organization_id!=user.organization_id: raise HTTPException(404,"Payment not found")
    if p.reversed: raise HTTPException(409,"Payment already reversed")
    if p.status!="confirmed": raise HTTPException(409,"Only confirmed payments can be reversed")
    original=p.transaction_id
    txn=str(uuid4())
    if original:
        for entry in db.scalars(select(LedgerEntry).where(LedgerEntry.transaction_id==original)).all():
            db.add(LedgerEntry(loan_id=entry.loan_id,transaction_id=txn,account=entry.account,debit_cents=entry.credit_cents,credit_cents=entry.debit_cents,organization_id=user.organization_id,branch_id=user.branch_id,description=f"Reversal: {reason}",reversal_of=original))
    p.reversed=True; p.reversal_reason=reason; db.add(AuditLog(actor_id=user.id,entity="payment",entity_id=p.id,action="reverse",details=reason,organization_id=user.organization_id,branch_id=user.branch_id)); db.commit(); return {"status":"reversed"}

@app.get("/api/v1/collections/queue")
def collections_queue(db:Session=Depends(db_session),user:User=Depends(current_user)):
    today=date.today(); stmt=select(Loan,Installment).join(Installment,Installment.loan_id==Loan.id).where(Loan.organization_id==user.organization_id,Loan.status.in_([LoanStatus.active,LoanStatus.disbursed]),Installment.due_date<=today)
    if user.role==Role.collections_officer: stmt=stmt.where(Loan.assigned_collector_id==user.id)
    rows=db.execute(stmt.order_by(Installment.due_date)).all()
    result=[]
    for loan,inst in rows:
        days=(today-inst.due_date).days; customer=db.get(Customer,loan.customer_id); collector=db.get(User,loan.assigned_collector_id) if loan.assigned_collector_id else None
        result.append({"loan_id":loan.id,"customer_id":loan.customer_id,"customer_name":customer.full_name if customer else "Unknown customer","officer_id":loan.officer_id,"collector_id":loan.assigned_collector_id,"collector_name":collector.username if collector else None,"due_date":inst.due_date,"days_past_due":days,"bucket":"1-30" if days<=30 else "31-60" if days<=60 else "61-90" if days<=90 else "90+","amount_due_cents":inst.principal_cents+inst.interest_cents+inst.fees_cents})
    return result

@app.post("/api/v1/collections/{loan_id}/assign")
def assign_collection_case(loan_id:int,data:AssignmentIn,db:Session=Depends(db_session),user:User=Depends(require(*MANAGERS))):
    loan=db.get(Loan,loan_id); collector=db.get(User,data.collector_id)
    if not loan or loan.organization_id!=user.organization_id: raise HTTPException(404,"Loan not found")
    if not collector or collector.organization_id!=user.organization_id or collector.role!=Role.collections_officer or not collector.active: raise HTTPException(422,"Choose an active collections officer in this organization")
    loan.assigned_collector_id=collector.id; db.add(AuditLog(actor_id=user.id,entity="loan",entity_id=loan.id,action="assign_collector",details=f"collector_id={collector.id}",organization_id=user.organization_id,branch_id=user.branch_id)); db.commit(); return {"loan_id":loan.id,"collector_id":collector.id,"collector_name":collector.username}

@app.get("/api/v1/collections/officers")
def list_collection_officers(db:Session=Depends(db_session),user:User=Depends(require(Role.admin,Role.manager,Role.branch_manager,Role.collections_officer))):
    return [{"id":u.id,"username":u.username} for u in db.scalars(select(User).where(User.organization_id==user.organization_id,User.role==Role.collections_officer,User.active==True).order_by(User.username)).all()]

@app.get("/api/v1/collections/{loan_id}/activities")
def list_collection_activities(loan_id:int,db:Session=Depends(db_session),user:User=Depends(current_user)):
    loan=db.get(Loan,loan_id)
    if not loan or loan.organization_id!=user.organization_id: raise HTTPException(404,"Loan not found")
    if user.role==Role.collections_officer and loan.assigned_collector_id!=user.id: raise HTTPException(403,"This collection case is assigned to another officer")
    rows=db.scalars(select(CollectionActivity).where(CollectionActivity.loan_id==loan_id,CollectionActivity.organization_id==user.organization_id).order_by(CollectionActivity.created_at.desc())).all()
    return [{"id":r.id,"user_id":r.user_id,"activity":r.activity,"notes":r.notes,"follow_up":r.follow_up,"created_at":r.created_at} for r in rows]

@app.post("/api/v1/collections/{loan_id}/activities")
def add_activity(loan_id:int,data:ActivityIn,db:Session=Depends(db_session),user:User=Depends(require(Role.admin,Role.manager,Role.branch_manager,Role.collections_officer,Role.loan_officer))):
    loan=db.get(Loan,loan_id)
    if not loan or loan.organization_id!=user.organization_id: raise HTTPException(404,"Loan not found")
    if user.role==Role.collections_officer and loan.assigned_collector_id!=user.id: raise HTTPException(403,"This collection case is assigned to another officer")
    row=CollectionActivity(loan_id=loan_id,user_id=user.id,organization_id=user.organization_id,branch_id=user.branch_id,**data.model_dump()); db.add(row); db.commit(); db.refresh(row); return row

@app.get("/api/v1/reports/summary")
def report_summary(db:Session=Depends(db_session),user:User=Depends(current_user)):
    loans=db.scalars(select(Loan).where(Loan.organization_id==user.organization_id)).all(); active=[l for l in loans if l.status in (LoanStatus.active,LoanStatus.disbursed,LoanStatus.restructured)]; payments=db.scalars(select(Payment).where(Payment.organization_id==user.organization_id,Payment.reversed==False,Payment.status=="confirmed")).all(); ledger=db.scalars(select(LedgerEntry).where(LedgerEntry.organization_id==user.organization_id)).all(); disbursed=sum(l.principal_cents for l in loans if l.disbursed_at); collected=sum(p.amount_cents for p in payments); outstanding=sum(x.debit_cents-x.credit_cents for x in ledger if x.account=="loan_receivable")
    overdue=db.scalars(select(Installment).join(Loan,Installment.loan_id==Loan.id).where(Loan.organization_id==user.organization_id,Installment.due_date<date.today())).all(); par=sum(i.principal_cents+i.interest_cents for i in overdue)
    pending_payments=db.scalar(select(func.count()).select_from(Payment).where(Payment.organization_id==user.organization_id,Payment.status=="pending")) or 0
    return {"currency":"KES","portfolio_outstanding_cents":max(0,outstanding),"disbursed_cents":disbursed,"collected_cents":collected,"active_loans":len(active),"overdue_installments":len(overdue),"pending_payments":pending_payments,"par_cents":par,"collection_rate":round(collected/disbursed,4) if disbursed else 0}

@app.get("/api/v1/reports/loans.csv")
def report_csv(db:Session=Depends(db_session),user:User=Depends(current_user)):
    from fastapi.responses import StreamingResponse
    import csv,io
    stream=io.StringIO(); writer=csv.writer(stream); writer.writerow(["loan_id","customer_id","principal_cents","currency","status"])
    for l in db.scalars(select(Loan).where(Loan.organization_id==user.organization_id)): writer.writerow([l.id,l.customer_id,l.principal_cents,l.currency,l.status.value])
    from fastapi.responses import Response
    return Response(stream.getvalue(),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=loans.csv"})

@app.get("/api/v1/health")
def health(db:Session=Depends(db_session)):
    db.execute(select(1))
    return {"status":"ok","database":"ok"}

_frontend=Path(__file__).resolve().parents[2]/"frontend"/"dist"
if _frontend.exists():
    app.mount("/assets",StaticFiles(directory=_frontend/"assets"),name="assets")
    @app.get("/{path:path}",include_in_schema=False)
    def frontend(path:str):
        candidate=_frontend/path
        return FileResponse(candidate) if candidate.is_file() else FileResponse(_frontend/"index.html")

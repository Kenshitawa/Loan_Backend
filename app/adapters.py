"""Provider seams. Production integrations can implement these protocols."""
from typing import Protocol

class PaymentProvider(Protocol):
    def verify_callback(self, payload: dict) -> dict: ...
class SMSProvider(Protocol):
    def send(self, phone: str, message: str) -> str: ...
class StorageProvider(Protocol):
    def save(self, name: str, content: bytes) -> str: ...
class CreditBureauProvider(Protocol):
    def check(self, national_id: str) -> dict: ...

class MockPaymentProvider:
    def verify_callback(self,payload): return {"valid":True,"reference":payload.get("reference","MOCK")}
class MockSMSProvider:
    def send(self,phone,message): return "mock-queued"
class LocalStorageProvider:
    def __init__(self,root="uploads"): self.root=root
    def save(self,name,content):
        from pathlib import Path
        path=Path(self.root)/name
        path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(content); return str(path)
class MockCreditBureauProvider:
    def check(self,national_id): return {"status":"not_configured","reference":national_id[-4:]}

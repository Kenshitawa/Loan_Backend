"""Provider seams. Production integrations can implement these protocols."""
import os
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from typing import Protocol

class PaymentProvider(Protocol):
    def verify_callback(self, payload: dict) -> dict: ...
class SMSProvider(Protocol):
    def send(self, phone: str, message: str) -> str: ...
class StorageProvider(Protocol):
    def save(self, name: str, content: bytes, content_type: str = "application/octet-stream") -> str: ...
    def load(self, name: str) -> bytes: ...
class CreditBureauProvider(Protocol):
    def check(self, national_id: str) -> dict: ...

class MockPaymentProvider:
    def verify_callback(self,payload): return {"valid":True,"reference":payload.get("reference","MOCK")}
class MockSMSProvider:
    def send(self,phone,message): return "mock-queued"
class LocalStorageProvider:
    def __init__(self,root="uploads"): self.root=root
    def save(self,name,content,content_type="application/octet-stream"):
        from pathlib import Path
        path=Path(self.root)/name
        path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(content); return str(path)
    def load(self,name):
        from pathlib import Path
        return Path(name).read_bytes()

class SupabaseStorageProvider:
    """Private Supabase Storage bucket accessed only by the trusted API server."""
    def __init__(self,url=None,service_role_key=None,bucket=None):
        self.url=(url or os.getenv("SUPABASE_URL","")).rstrip("/")
        self.key=service_role_key or os.getenv("SUPABASE_SERVICE_ROLE_KEY","")
        self.bucket=bucket or os.getenv("SUPABASE_STORAGE_BUCKET","customer-documents")
        if not self.url or not self.key:
            raise RuntimeError("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to use Supabase Storage")

    def _request(self,method,name,content=None,content_type=None):
        path=f"/storage/v1/object/{quote(self.bucket,safe='')}/{quote(name,safe='/')}"
        headers={"apikey":self.key,"Authorization":f"Bearer {self.key}"}
        if content_type: headers["Content-Type"]=content_type
        if method=="POST": headers["x-upsert"]="false"
        request=Request(f"{self.url}{path}",data=content,headers=headers,method=method)
        try:
            with urlopen(request,timeout=30) as response:
                return response.read()
        except HTTPError as exc:
            detail=exc.read(2048).decode("utf-8","replace")
            raise RuntimeError(f"Supabase Storage returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise RuntimeError(f"Could not reach Supabase Storage: {exc.reason}") from exc

    def save(self,name,content,content_type="application/octet-stream"):
        self._request("POST",name,content,content_type)
        return name

    def load(self,name):
        return self._request("GET",name)

def customer_storage():
    if os.getenv("SUPABASE_URL") or os.getenv("SUPABASE_SERVICE_ROLE_KEY"):
        return SupabaseStorageProvider()
    if os.getenv("APP_ENV", "development").lower()=="production":
        raise RuntimeError("Configure Supabase Storage before enabling customer document uploads in production")
    return LocalStorageProvider(os.getenv("UPLOAD_DIR","uploads"))

class MockCreditBureauProvider:
    def check(self,national_id): return {"status":"not_configured","reference":national_id[-4:]}

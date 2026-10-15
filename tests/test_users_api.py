from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import Base, SessionLocal, User, Role, app, engine, password_hash


def test_admin_can_create_officer_roles_and_other_roles_are_rejected():
    Base.metadata.create_all(engine)
    suffix=uuid4().hex[:10]
    admin_name=f"testadmin_{suffix}"
    with SessionLocal() as db:
        admin=User(username=admin_name,password=password_hash.hash("TestAdminPass123!"),role=Role.admin)
        db.add(admin); db.commit(); admin_id=admin.id
    created_ids=[]
    try:
        with TestClient(app) as client:
            login=client.post("/api/v1/auth/login",json={"username":admin_name,"password":"TestAdminPass123!"})
            assert login.status_code==200
            admin_headers={"Authorization":f"Bearer {login.json()['access_token']}"}
            for role in ("loan_officer","collections_officer"):
                result=client.post("/api/v1/users",headers=admin_headers,json={"username":f"{role}_{suffix}","password":"OfficerPass123!","role":role})
                assert result.status_code==201
                assert result.json()["role"]==role
                created_ids.append(result.json()["id"])
                officer_login=client.post("/api/v1/auth/login",json={"username":f"{role}_{suffix}","password":"OfficerPass123!"})
                assert officer_login.status_code==200
                assert officer_login.json()["role"]==role
            rejected=client.post("/api/v1/users",headers=admin_headers,json={"username":f"badrole_{suffix}","password":"OfficerPass123!","role":"accountant"})
            assert rejected.status_code==422
            officer_login=client.post("/api/v1/auth/login",json={"username":f"loan_officer_{suffix}","password":"OfficerPass123!"})
            officer_headers={"Authorization":f"Bearer {officer_login.json()['access_token']}"}
            assert client.get("/api/v1/users",headers=officer_headers).status_code==403
    finally:
        with SessionLocal() as db:
            db.query(User).filter(User.id.in_([admin_id,*created_ids])).delete(synchronize_session=False)
            db.commit()

# MWANGAZABIz API

This repository contains the FastAPI backend only. It stores users, loans, repayments, and customer interactions. Customer document uploads also go through this API.

## Local setup

Use Python 3.12+. From this folder, run:

```sh
python -m venv .venv
```

Activate the environment, install the development requirements, and prepare the database:

```sh
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

The local development database is `mwangazabiz.db` and is intentionally ignored by Git. API documentation is available at `http://127.0.0.1:8000/docs`.

## Production settings

Deploy this repository as a Docker web service with a managed PostgreSQL database and persistent file storage. The included `Dockerfile` applies Alembic migrations and creates the first admin only when the database has no admin.

Configure these environment variables in the hosting provider's private settings:

- `APP_ENV=production`
- `DATABASE_URL` — PostgreSQL connection URL, preferably using `postgresql+psycopg://...`
- `SECRET_KEY` — a random secret of at least 32 characters
- `CORS_ORIGINS` — comma-separated exact HTTPS origins of the deployed website (no `*`)
- `BOOTSTRAP_ADMIN_USERNAME` and `BOOTSTRAP_ADMIN_PASSWORD` — temporary initial credentials; password must be at least 16 characters
- `UPLOAD_DIR` — path on persistent storage for customer ID and profile uploads
- `ENABLE_SCHEDULER=true` — keep only one running API instance while the in-process daily penalty scheduler is enabled
- `PORT` — supplied by most Docker hosting providers; defaults to 8000

Never commit `.env`, customer data, a database file, uploaded identity documents, or real credentials. Before accepting real data, confirm that the hosting provider keeps both PostgreSQL and `UPLOAD_DIR` persistent across restarts and deployments. Set `CORS_ORIGINS` to the Vercel website's exact URL. The API health endpoint is `/api/v1/health`.

## API

The API base path is `/api/v1`. Sign-in returns a bearer token. New users and the initial admin must change their temporary password at first sign-in. Run database migrations with `alembic upgrade head` from this repository root.

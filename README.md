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

## Deploy this API on Render

1. In Render, create a **PostgreSQL** database and a **Web Service** connected to this GitHub repository. Choose the Docker runtime so Render uses the included `Dockerfile`.
2. Connect the web service to the database using Render's internal connection URL as `DATABASE_URL`. This backend automatically converts Render's standard PostgreSQL URL to the installed psycopg driver format.
3. Add the remaining environment variables below in the Render dashboard. Set `APP_ENV` to `production` and set `CORS_ORIGINS` to the exact Vercel site URL (for example, `https://your-site.vercel.app`, no trailing slash).
4. To keep uploaded customer ID and profile photos after restarts, attach a persistent disk to the web service at `/app/uploads`, then set `UPLOAD_DIR=/app/uploads`. Render disks require a paid web service and the service must stay at one instance while this disk is attached.
5. Once Render finishes deploying, check `https://YOUR-RENDER-SERVICE.onrender.com/api/v1/health`. In Vercel, set `VITE_API_URL` to `https://YOUR-RENDER-SERVICE.onrender.com/api/v1`, then redeploy the frontend.

Use a test database and dummy customer data while setting this up. Render's free web services cannot use persistent disks, and its free PostgreSQL databases expire after 30 days; those free resources are for testing, not real loan records or identity documents. See Render's [persistent disk guide](https://render.com/docs/disks) and [free tier limitations](https://render.com/docs/free).

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


## Supabase and workbook migration

For the beginner-friendly Render + Supabase setup, required environment variables, database cutover, Vercel API configuration, and the reviewed import flow for the `Entire` workbook tab, see [docs/SUPABASE_MIGRATION.md](docs/SUPABASE_MIGRATION.md).

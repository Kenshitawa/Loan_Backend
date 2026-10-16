# Supabase migration (keep Render API free)

This setup moves PostgreSQL and private customer document storage to Supabase while keeping the existing FastAPI API on Render's Free web-service tier. Render's free API can sleep after inactivity, so first requests may take a while. The Supabase Free database can pause after a week of low activity and has no built-in downloadable backups. Use this setup for controlled testing; do not treat it as a backed-up production system for real lending records.

## 1. Create a Supabase project

1. Create a Supabase project and save its database password in a password manager.
2. Pick a region reasonably close to the Render API region.
3. In **Project Settings → Database → Connect**, copy the **Session pooler** connection string (not the transaction pooler string). Preserve the `sslmode=require` query parameter and use the SQLAlchemy driver form `postgresql+psycopg://`.
4. In **Storage**, create a bucket named `customer-documents` and keep it **private**. Do not make it public.
5. In **Project Settings → API**, copy the Project URL and service-role/secret key. That key belongs only in Render's secret environment variables; never put it in Vercel or this repository.

## 2. Back up the current Render database

Do not delete or change the existing Render database until the new deployment has been checked. For a live database, pause writes during the final backup so no new payments or loans arrive between export and cutover.

On a computer with PostgreSQL client tools installed, set these values only in the current PowerShell window. Use the Render **external** database URL for the source and the Supabase **Session pooler** URL for the destination. Do not paste real URLs into chat or commit them:

```powershell
$env:SOURCE_DATABASE_URL = 'postgresql://...'
$env:SUPABASE_DATABASE_URL = 'postgresql://...'
pg_dump --schema=public --format=custom --no-owner --no-acl --file .\mwangazabiz-before-supabase.dump $env:SOURCE_DATABASE_URL
```

Restore into a **new/empty Supabase project**. The command does not delete destination data; if that project already has application tables or customer data, stop and use a fresh project instead.

```powershell
pg_restore --no-owner --no-acl --exit-on-error --dbname=$env:SUPABASE_DATABASE_URL .\mwangazabiz-before-supabase.dump
```

Keep the backup private and verify its size. It contains borrower information. Store it encrypted and remove it securely after a verified backup policy is in place.

## 3. Configure Render

In the existing Render API service, set/update these environment variables. Keep the database password and service-role key in Render's **Environment** settings, never in source control:

- `APP_ENV=production`
- `DATABASE_URL` = Supabase Session pooler URL, converted to `postgresql+psycopg://...` if necessary
- `SUPABASE_URL` = Supabase Project URL
- `SUPABASE_SERVICE_ROLE_KEY` = Supabase service-role/secret key
- `SUPABASE_STORAGE_BUCKET=customer-documents`
- `CORS_ORIGINS` = exact production Vercel origin, with no trailing slash
- `SECRET_KEY` = existing strong application JWT secret; keep it unchanged so current sessions/passwords still work
- Keep the existing bootstrap-admin settings; with an imported database, bootstrap is skipped if an admin already exists

Render will redeploy, run Alembic migrations, and connect to Supabase. New customer ID and profile uploads will go to the private Supabase bucket and will still be served through the authenticated API. Existing local uploads are not automatically copied; export any still-accessible files before the Render service restarts if you need them.

## 4. Set the Vercel API address

In the Vercel project for the frontend, add `VITE_API_URL` with the full API prefix, for example `https://YOUR-RENDER-SERVICE.onrender.com/api/v1`, then redeploy the frontend. In Render, set `CORS_ORIGINS` to the exact Vercel site origin (for example `https://your-app.vercel.app`) so browser requests are allowed. Do not put database URLs or Supabase service-role keys in Vercel.

The selected `Entire` worksheet has been imported as legacy opening-balance snapshots. Those snapshots remain separate from live loans, schedules, payments, and ledger balances. Formula-derived workbook balances are marked unverified and should be reviewed with staff before operational use. The upload/import feature was removed after the one-time import.

## 5. Verify before removing the old database

1. Check `https://YOUR-RENDER-SERVICE.onrender.com/api/v1/health` reports both API and database as healthy.
2. Sign in and verify team, customers, products, loans, repayments, reports, and customer documents.
3. Compare key record counts and portfolio totals from before migration.
4. Test one small document upload and download, then confirm the object exists in the private bucket.
5. Keep Render's old database untouched until these checks pass and you have a separate backup. Only then remove any paid Render database resource.

## Free-tier limits to keep in mind

Supabase Free currently includes 500 MB of database and 1 GB of file storage, may pause low-activity projects after a week, and does not include downloadable database backups. Keep a separate, encrypted backup schedule and test restores before using real borrower data. Render's Free API service may sleep after 15 minutes without requests; moving the database does not remove that cold start.

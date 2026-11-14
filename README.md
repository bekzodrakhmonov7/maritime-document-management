# Maritime Crew Document Expiry Monitoring System

A full-stack application for tracking maritime crew document expirations across a fleet of vessels. Built with FastAPI, React, Tailwind CSS v4, and Supabase (local).

## Stack

- **Backend**: FastAPI + asyncpg + Supabase local (PostgreSQL + Auth + Storage)
- **Frontend**: React 19 + Vite + Tailwind CSS v4 + shadcn/ui
- **E-mail**: Resend HTTP API

## Prerequisites

- Python 3.13+
- Node.js 22+
- Docker & Docker Compose
- `npx` (comes with Node.js)

## Quick Start

### 1. Install Supabase CLI & start services

```bash
npx supabase@latest login
npx supabase@latest start
```

This starts PostgreSQL (port 54322), Auth, Storage, and other services.

### 2. Backend setup

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install uv
uv sync
```

Copy environment variables and run migrations:

```bash
cd backend
cp ../.env.example .env
npx supabase@latest db reset   # Applies migrations in supabase/migrations/
```

> **Note:** `supabase db reset` is destructive — it drops and recreates the
> local database, which **wipes all registered auth users** (`auth.users` and
> `public.users`). Only the seed data is restored. After every reset you must
> re-register your account and make it an administrator again (below).

The app connects as the restricted `app_backend` database role, never as the
table owner, so it can only add to and read the Audit Log. `seed.sql` gives it
the local password `app_backend_dev` (see `DATABASE_URL` in `.env.example`).

### First administrator

New accounts start **pending** with no role and see only a "waiting for
approval" page. Sign up in the app, then make that account the first
administrator:

```bash
cd backend
uv run python -m app.scripts.make_admin you@company.com
```

After that, administrators approve new sign-ups on the **Accounts** page,
choosing a role (administrator, crewing officer or manager) and giving a
reason. Every approval, role change and switch-off/on is audited.

Sign-in goes through the backend (`POST /api/auth/login`, a proxy to Supabase
Auth) so failed attempts are recorded, including ones on unknown e-mails; the
frontend then calls `setSession`. Successful logins are copied into the Audit
Log by a trigger on `auth.audit_log_entries`, logouts by
`POST /api/auth/logout`, and every refused request (403, or a 404 on a record
outside the caller's Scope) by one exception handler. Stated limit: a direct
call to Supabase Auth with the public key skips the failed-login record.

Start the FastAPI server:

```bash
uv run uvicorn app.main:app --reload --port 8000
```

### 3. Frontend setup

```bash
cd frontend
npm install
npm run dev
```

The UI will be available at `http://localhost:5173`.

## Running Tests

### Backend

```bash
cd backend
uv run pytest tests/ -v
```

Integration tests need the local database. The app under test connects as
`app_backend` (derived from `OWNER_DATABASE_URL`, or set `APP_DATABASE_URL`);
fixtures arrange rows through `OWNER_DATABASE_URL` and never use the seed.

### Frontend

```bash
cd frontend
npm run build
```

## Environment Variables

Key variables in `.env` (project root):

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | The app's connection, as `app_backend` | `postgresql://app_backend:app_backend_dev@127.0.0.1:54322/postgres` |
| `OWNER_DATABASE_URL` | The table owner, for tooling and test fixtures only | `postgresql://postgres:postgres@127.0.0.1:54322/postgres` |
| `SUPABASE_URL` | Supabase local API URL | `http://127.0.0.1:54321` |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key | `eyJhbG...` |
| `SUPABASE_JWT_SECRET` | JWT signing secret | `super-secret-jwt-token-with-at-least-32-characters-long` |
| `RESEND_API_KEY` | Resend API key for e-mail | `re_...` |
| `MAIL_FROM` | Sender email | `noreply@maritime.local` |

Frontend variables in `frontend/.env`:

| Variable | Description | Example |
|----------|-------------|---------|
| `VITE_SUPABASE_URL` | Supabase local API URL | `http://127.0.0.1:54321` |
| `VITE_SUPABASE_ANON_KEY` | Supabase anon/public key | `eyJhbG...` |
| `VITE_API_BASE` | Backend API base URL | `http://localhost:8000` |

## Project Structure

```
.
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app factory
│   │   ├── config.py            # Pydantic settings
│   │   ├── db.py                # asyncpg pool
│   │   ├── deps.py              # JWT + per-request account check
│   │   ├── audit.py             # The audit helper (Audit Log writes)
│   │   ├── refused_access.py    # Records every refused request
│   │   ├── supabase_auth.py     # Password sign-in against Supabase Auth
│   │   ├── routers/             # API endpoints (under /api)
│   │   ├── services/            # Business logic
│   │   └── scripts/             # make_admin
│   ├── tests/
│   │   ├── integration/         # Integration tests (app runs as app_backend)
│   │   └── unit/                # Unit tests
├── supabase/
│   └── migrations/              # Database migrations
├── frontend/
│   ├── src/
│   │   ├── pages/               # Route pages
│   │   ├── components/          # Reusable UI components
│   │   ├── hooks/               # React hooks
│   │   ├── lib/                 # API client & Supabase
│   │   └── context/             # Auth context
│   └── public/
├── docker-compose.yml           # Mailhog only
└── README.md
```

## API Documentation

With the backend running, visit:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Roles

- **Administrator**: approves accounts and changes their roles and status; maintains the fleet and the rules.
- **Crewing Officer**: manages the seafarers and documents of their vessels.
- **Manager**: sees fleet-level totals only.

Accounts are never deleted. The last active administrator can't be deactivated
or demoted, and no administrator can change their own role or status.

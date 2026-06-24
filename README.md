# Maritime Crew Document Expiry Monitoring System

A full-stack application for tracking maritime crew document expirations across a fleet of vessels. Built with FastAPI, React, Tailwind CSS v4, and Supabase (local).

## Stack

- **Backend**: FastAPI + asyncpg + Supabase local (PostgreSQL + Auth + Storage)
- **Frontend**: React 19 + Vite + Tailwind CSS v4 + shadcn/ui
- **Worker**: APScheduler for daily expiry scans
- **SMTP**: fastapi-mail + Mailhog (local dev)

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
> `public.users`). Only the seed data (vessels, seafarers, document types) is
> restored. After every reset you must re-register your account. Use a hosted
> Supabase project for durable data.

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

### 4. Worker (optional — runs scheduled scans)

```bash
cd backend
uv run python -m app.worker.run_expiry_scan --once
```

For continuous scheduling:

```bash
uv run python -m app.worker.run_expiry_scan
```

### 5. Mailhog (view emails locally)

Mailhog is available at `http://localhost:8025` when running via docker-compose.

## Running Tests

### Backend

```bash
cd backend
uv run pytest tests/ -v
```

All 68 tests should pass:
- 4 E2E tests
- 38 integration tests
- 26 unit tests

### Frontend

```bash
cd frontend
npm run build
```

## Environment Variables

Key variables in `.env` (project root):

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://postgres:postgres@127.0.0.1:54322/postgres` |
| `SUPABASE_URL` | Supabase local API URL | `http://127.0.0.1:54321` |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key | `eyJhbG...` |
| `SUPABASE_JWT_SECRET` | JWT signing secret | `super-secret-jwt-token-with-at-least-32-characters-long` |
| `SMTP_HOST` | SMTP server | `localhost` |
| `SMTP_PORT` | SMTP port | `1025` |
| `SMTP_USER` | SMTP username | `mailhog` |
| `SMTP_PASS` | SMTP password | `mailhog` |
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
│   │   ├── deps.py              # JWT auth dependency
│   │   ├── routers/             # API endpoints
│   │   ├── services/            # Business logic
│   │   └── worker/              # Expiry scan scheduler
│   ├── tests/
│   │   ├── e2e/                 # End-to-end tests
│   │   ├── integration/         # Integration tests
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

## Default Roles

- **Administrator**: Full access to vessels, seafarers, documents, reports, and configuration.
- **Crewing Officer**: Can manage seafarers and documents, read-only on vessels and reports.

## License

MIT

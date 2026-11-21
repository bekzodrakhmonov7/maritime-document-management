# Maritime Crew Document Expiry Monitoring System

A full-stack application for tracking maritime crew document expirations across a fleet of vessels. Built with FastAPI, React, Tailwind CSS v4, and Supabase (local).

This README is the developer guide. For using the application, see the
[User Guide](USER_GUIDE.md).

## Stack

- **Backend**: FastAPI + asyncpg + Supabase local (PostgreSQL + Auth + Storage)
- **Frontend**: React 19 + Vite + Tailwind CSS v4 + shadcn/ui
- **E-mail**: Resend HTTP API
- **Hosting**: one Vercel project (frontend + API as Python functions in `fra1`), Supabase hosted. See [Hosting](#hosting-vercel--supabase)

## Prerequisites

- Git
- Python 3.13+ and [uv](https://docs.astral.sh/uv/) (it creates and manages the virtual environment)
- Node.js 22+ (with `npx`)
- Docker (running)

All commands below run from the repository root unless they start with `cd`.
They are written for a POSIX shell (Git Bash on Windows works; in PowerShell use
`Copy-Item` instead of `cp`).

## Quick Start

### 1. Start the local Supabase services

```bash
npx supabase@2.122.1 start
```

This starts PostgreSQL (port 54322), Auth, Storage, Mailpit and the other
services, and prints their URLs and keys. No `supabase login` is needed for the
local stack. The CLI version is pinned: CLI 3.x refuses this repository's
`supabase/config.toml` ("inbucket ... is no longer supported").

### 2. Backend setup

```bash
uv sync    # creates .venv at the repository root, including the dev tools
```

Create the environment file **at the repository root** (`backend/app/config.py`
reads `.env` from there) and run the migrations:

```bash
cp .env.example .env
npx supabase@2.122.1 db reset   # Applies migrations in supabase/migrations/
```

Fill in the three Supabase values in `.env` from the output of
`npx supabase@2.122.1 status`: `SUPABASE_ANON_KEY` is `ANON_KEY`,
`SUPABASE_SERVICE_ROLE_KEY` is `SERVICE_ROLE_KEY` and `SUPABASE_JWT_SECRET` is
`JWT_SECRET`. The other defaults work locally.

> **Note:** `supabase db reset` is destructive — it drops and recreates the
> local database, which **wipes all registered auth users** (`auth.users` and
> `public.users`). Only the seed data is restored. After every reset you must
> register your account again and make it an administrator again (below).

The app connects as the restricted `app_backend` database role, never as the
table owner, so it can only add to and read the Audit Log. It cannot remove old
Audit Records either: the owner's nightly `audit-retention` `pg_cron` job
(03:17 UTC) does that (SR-14, ADR 0008). `seed.sql` gives it
the local password `app_backend_dev` (see `DATABASE_URL` in `.env.example`).

### Signing in: a password, then an authenticator code

Two steps (ADR-0005, ADR-0007, SR-03). **Sign in** asks for e-mail and
password, then the 6-digit code from an **authenticator app** (TOTP, Supabase
Auth MFA). At the first sign-in every Account, pending ones too, enrols the
app: the page shows a QR code and the key for typing by hand, and the first
right code finishes both the enrolment and the sign-in. **Register** asks for
full name, e-mail and password, then a code e-mailed to the address (6 digits,
valid 10 minutes, at most one every 60 seconds; the e-mail holds only the
code, never a link), and then goes on to the enrolment. Five wrong codes end
the sign-in; start again with the password.

The API accepts only `aal2` sessions (the TOTP code was verified) that went
through both steps of its sign-in proxy: an `aal1` (password-only) token gets
401 `second_factor_missing` on every protected endpoint and an *access
refused* record, and a session completed directly at Supabase Auth gets 401
`session_not_verified`. So nothing (no env flag, dev mode, demo login or
direct call to Supabase Auth) skips either step. Between the two steps the
proxy keeps Supabase's `aal1` access token in the sign-in challenge row; it is
removed when the challenge is used or ended, an owner `pg_cron` job
(`sign-in-challenge-cleanup`, every 5 minutes) deletes expired challenges, and
the token is never logged or returned.

**Blocked after failed sign-ins (SR-18):** 10 failed sign-ins (wrong
password, unknown e-mail or wrong authenticator code, together) for one e-mail
(any case) or from one address within 15 minutes block both steps (`/api/auth/login`,
`/api/auth/verify`) for that e-mail or address for 15 minutes: 429
`login_blocked` with `Retry-After`, the same answer for known and unknown
e-mails, Supabase Auth not asked, recorded as *login failed* with reason
`login_blocked`. Blocked attempts and Supabase Auth being unavailable are not
counted, so they never extend a block. Blocks live in `public.login_block`;
an owner `pg_cron` job (`login-block-cleanup`, hourly) removes those that
ended over a day ago. To lift one locally:
`DELETE FROM public.login_block WHERE key = 'someone@example.com';`. The
address is the visitor's as the backend sees it (ADR-0006). Uploads are not
rate-limited.

**Lost authenticator:** an administrator presses **Reset authenticator** on the
**Accounts** page (`POST /api/accounts/{id}/second-factor/reset`, recorded as
*second factor reset*). The Account is signed out and enrols a new app at its
next sign-in. **Forgot password?** on the Sign in page e-mails a code; the
reset form takes that code, the new password and the current authenticator
code (`POST /api/auth/password/reset` with `{email, code, password, totp}`).
The e-mailed code opens an `aal1` recovery session, the authenticator code
raises it to `aal2`, and only then is the password set; missing code: 400
`totp_required`, wrong code: 403 `totp_invalid` (both recorded as a refused
*password reset* and needing a new e-mailed code). An Account without an
authenticator (just after **Reset authenticator**) resets with the e-mailed
code alone. Every session of the Account then ends.

Locally, any authenticator app works (scan the QR code from the browser), or
generate the code from the key shown on the enrolment step:

```bash
cd backend
uv run python -c "import pyotp; print(pyotp.TOTP('THE KEY SHOWN'.replace(' ', '')).now())"
```

`pyotp` is a dev dependency only; the real-GoTrue tests in
`tests/integration/test_sign_in_api.py` use it the same way.

A new password (Register, Forgot password) has 12 to 72 characters and is
refused with 422 `weak_password` when it is on the bundled list of common
passwords (`backend/app/data/common_passwords.txt`, case-insensitive) or known
to [Pwned Passwords](https://haveibeenpwned.com/API/v3#PwnedPasswords) (SR-02).
The breach check sends only the first five hex characters of the password's
SHA-1 (k-anonymity); if the service can't be reached within 3 s the password
is accepted and a warning is logged. A refused reset is recorded as *password
reset*, outcome `refused`, reason `weak_password`. Sign in accepts any length,
so Accounts made under the old minimum of 8 still get in. Tests never call the
real service: `tests/conftest.py` replaces it. A local database that ran the
earlier, password-wiping version of migration `20261116130000` lost its test
passwords; set new ones that way.

Locally, Supabase doesn't send mail: its mail catcher, **Mailpit**, catches it.
Register (or ask for a password reset) in the app, open
<http://127.0.0.1:54324>, open the newest message for your address and type the
6 digits. The Auth settings (TOTP on under `[auth.mfa.totp]`) and the code-only
e-mail templates live in `supabase/config.toml` and `supabase/templates/`
(`confirmation.html` for Register, `recovery.html` for Forgot password;
`magic_link.html` is no longer used for signing in); run `npx supabase@2.122.1 stop && npx supabase@2.122.1 start` after
changing them. SMTP (Resend) is off locally and only turned on for hosted.

### First administrator

New Accounts start **pending** with no role and see only a "waiting for
approval" page. Make the first one an administrator:

1. **Register** in the app with your e-mail and full name.
2. Type the **code** from the e-mail (locally: from Mailpit), then enrol an
   authenticator app (QR code or key) and type its code. You land on
   "waiting for approval".
3. Run `make_admin`:

   ```bash
   cd backend
   uv run python -m app.scripts.make_admin you@company.com
   ```

After that, administrators approve new Accounts on the **Accounts** page,
choosing a role (administrator, crewing officer or manager) and giving a
reason. Every approval, role change and switch-off/on is audited.

Every sign-in step goes through the backend's sign-in proxy
(`POST /api/auth/login`, `POST /api/auth/register`, `POST /api/auth/code`,
`POST /api/auth/verify`) so failed attempts are recorded, including wrong
passwords, wrong authenticator codes (`totp_invalid`) and wrong or expired
e-mailed codes. Successful sign-ins are recorded by the proxy once the
authenticator code is right, sign-outs by `POST /api/auth/logout`, and every
refused request (401 for a refused session, 403, or a 404 on a record outside
the caller's Scope) by one exception handler.

The web client never calls Supabase Auth itself (SR-01) and has no Supabase
client, URL or key. It keeps the session the proxy returns in `localStorage`
(key `mdm.session`), renews it through `POST /api/auth/refresh` shortly before
it expires and after a 401, and `POST /api/auth/logout` ends it at Supabase
Auth too. The refresh answers a new session only while it is a verified `aal2`
session of an Account that is not switched off; otherwise 401 (403 when
switched off) and an *access refused* record.

Stated limits:

- A direct call to Supabase Auth with the public key skips the failed-login
  record.
- A session lasts until sign-out; there is no periodic re-proof of the second
  factor (time-boxed sessions need Supabase Pro). Switching an Account off still cuts
  it off on its next request (FR-02).
- A direct call to Supabase's `/otp` with the public key reveals whether an
  e-mail has an Account (422 for unknown, 200 for known). Only our proxy hides
  it. A session it gives is `aal1` and not verified, so it gets nowhere.
- Changing an Account's e-mail has no screen. Through Supabase directly, it
  needs confirmation from both the old and the new inbox.

Start the FastAPI server:

```bash
cd backend
uv run uvicorn app.main:app --reload --port 8000
```

### 3. Frontend setup

Create `frontend/.env` from its example (it only sets `VITE_API_BASE`; the web
client talks to the API alone, never to Supabase):

```bash
cd frontend
cp .env.example .env
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
Unit tests alone (no database): `uv run pytest tests/unit -q`.

#### Coverage

Statement coverage of the three components the thesis names (NFR-06: at least
80 % each). The HTML report lands in `backend/htmlcov/`:

```bash
cd backend
uv run pytest tests/ -q \
  --cov=app.domain --cov=app.reports \
  --cov=app.scope --cov=app.deps --cov=app.routers.crew_access --cov=app.refused_access \
  --cov=app.upload_safety \
  --cov-report=term-missing --cov-report=html
```

| Component | Modules |
|---|---|
| Status engine | `app/domain.py`, `app/reports.py` |
| Access policy | `app/scope.py`, `app/deps.py`, `app/routers/crew_access.py`, `app/refused_access.py` |
| File validation | `app/upload_safety.py` |

### Frontend

```bash
cd frontend
npm test        # unit tests (node --test)
npm run build   # type check and production build
```

## Environment Variables

Key variables in `.env` (project root):

| Variable | Description | Example |
|----------|-------------|---------|
| `DATABASE_URL` | The app's connection, as `app_backend` | `postgresql://app_backend:app_backend_dev@127.0.0.1:54322/postgres` |
| `OWNER_DATABASE_URL` | The table owner, for tooling and test fixtures only | `postgresql://postgres:postgres@127.0.0.1:54322/postgres` |
| `SUPABASE_URL` | Supabase local API URL | `http://127.0.0.1:54321` |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase service role key | `eyJhbG...` |
| `SUPABASE_ANON_KEY` | Supabase anon/public key, for the sign-in proxy | `eyJhbG...` |
| `SUPABASE_JWT_SECRET` | JWT signing secret | `super-secret-jwt-token-with-at-least-32-characters-long` |
| `RESEND_API_KEY` | Resend API key for e-mail | `re_...` |
| `MAIL_FROM` | Sender email | `noreply@maritime.local` |
| `SUPABASE_AUTH_SMTP_PASSWORD` | Hosted only: the Resend API key Supabase Auth sends the Register and password-reset codes with, read by `supabase config push` (`env(...)` in `supabase/config.toml`). Empty locally, where Mailpit catches the mail | `re_...` |
| `FRONTEND_URL` | The app's address, for links in e-mails | `http://localhost:5173` |
| `CRON_SECRET` | Shared with the database's `daily-check` job (Vault `cron_secret`); empty means `/api/internal/daily-check` always answers 404 | `local-dev-cron-secret` |

Frontend variables in `frontend/.env`:

| Variable | Description | Example |
|----------|-------------|---------|
| `VITE_API_BASE` | Backend API base URL. Unset means `http://localhost:8000`; empty means the page's own origin (the Vercel build sets it empty) | `http://localhost:8000` |

## Hosting (Vercel + Supabase)

One Vercel project serves the frontend at `/` and the API at `/api` from one
origin, in Vercel's `fra1` region next to the Supabase project in eu-central-1
(ADR 0003). The root `vercel.json` builds the frontend as static output
(`frontend/dist`, with `VITE_API_BASE` set empty so the app calls its own
origin), exposes the FastAPI app as the Python function `api/index.py` (bundling
`backend/app/**`), and rewrites `/api/*` to that function and every other path to
the SPA. Every 5 minutes the database's `daily-check` `pg_cron` job calls
`POST /api/internal/daily-check`, with the URL and shared secret read from
Supabase Vault. Email goes through Resend. DNS is managed in Vercel.

There are two Supabase projects:

| Supabase project | Used by | Vercel environment |
|------------------|---------|--------------------|
| production | the production deployment (the domain) | Production |
| staging | every preview deployment, so unmerged code never touches real crew records | Preview |

The cutover wizard does the whole setup, step by step, and remembers its answers
in `.env.hosted` (gitignored; delete it when done):

```bash
bash scripts/hosted-cutover.sh
```

### Vercel project

Create the project from this repository with the **Root Directory left at the
repository root** (not `frontend/`) and the framework preset **Other**. Leave the
build, output and install settings unset: `vercel.json` sets them, the `fra1`
region and the rewrites.

### Environment variables

Set these nine in Vercel. Production gets the production Supabase project's
values, Preview gets the staging project's. Mark the secret ones Sensitive.

| Variable | Value |
|----------|-------|
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` |
| `SUPABASE_ANON_KEY` | the project's anon (public) key |
| `SUPABASE_SERVICE_ROLE_KEY` | the project's service_role key |
| `SUPABASE_JWT_SECRET` | the project's (legacy) JWT secret |
| `DATABASE_URL` | the **transaction pooler**, as `app_backend`: `postgresql://app_backend.<project-ref>:<password>@<region>.pooler.supabase.com:6543/postgres` |
| `CRON_SECRET` | a generated secret per environment (`openssl rand -hex 32`), the same value as that project's Vault `cron_secret` |
| `FRONTEND_URL` | Production: `https://<domain>`. Preview: the staging branch URL |
| `MAIL_FROM` | an address on the domain verified in Resend, e.g. `alerts@<domain>` |
| `RESEND_API_KEY` | Production: the Resend key. Preview: **empty**, or a key that can only send to the developer's own address (a Resend account with no verified domain), so staging never e-mails real officers |

Never set `OWNER_DATABASE_URL` on Vercel: the table owner could alter the Audit
Log (ADR 0002). `CORS_ORIGINS` is for local development only, and the build sets
`VITE_API_BASE` itself. Use port 6543 (transaction pooler), not 5432: parallel
function instances would exhaust the session pooler, and the app turns
asyncpg's statement cache off for it.

### Each Supabase project

For production and for staging:

1. **Migrations.** Link it and push: `npx supabase@2.122.1 link --project-ref
   <project-ref>`, then `npx supabase@2.122.1 db push`. Pushed migrations are
   frozen (below). A new staging project just gets every migration.
2. **`app_backend` password.** In the SQL editor:
   `ALTER ROLE app_backend PASSWORD '<generated-secret>';` (for example from
   `openssl rand -hex 32`, which needs no URL escaping). Put it in that
   environment's `DATABASE_URL`. Keep it out of git.
3. **Vault.** Enable Vault if needed, then set the two values the `daily-check`
   job reads. Each project points at its own deployment:

   ```sql
   DELETE FROM vault.secrets WHERE name IN ('daily_check_url', 'cron_secret');
   SELECT vault.create_secret('<url>', 'daily_check_url');
   SELECT vault.create_secret('<CRON_SECRET of that environment>', 'cron_secret');
   ```

   Production's `<url>` is `https://<domain>/api/internal/daily-check`.
   Staging's is the preview of a long-lived `staging` branch,
   `https://<project>-git-staging-<team>.vercel.app/api/internal/daily-check`.
   Previews sit behind Vercel Authentication by default, which also blocks the
   scheduled daily check: either create a **Protection Bypass for Automation** secret
   (Settings → Deployment Protection) and append
   `?x-vercel-protection-bypass=<secret>` to staging's URL, or turn protection
   off for previews.
4. **Auth URLs.** Authentication → URL Configuration: production's Site URL is
   `https://<domain>`; staging's is the staging branch URL, with
   `https://*.vercel.app/**` among its Redirect URLs.
5. **Auth config (password, then code).** Push `supabase/config.toml`'s Auth
   settings and the code-only templates with `supabase config push`, **staging
   first, then production** once staging signs in by code. The wizard does it
   (also on its own, for projects already cut over):

   ```bash
   bash scripts/hosted-cutover.sh auth-config
   ```

   It pushes a copy of the config with Resend SMTP turned on and that
   project's Site URL and redirect URL instead of the local ones, with
   `SUPABASE_AUTH_SMTP_PASSWORD` (a Resend API key) and `MAIL_FROM` (the
   sender, on the domain the Alerts use) in its environment. `config push`
   prints the diff and asks before changing anything: **read it**. It should
   show `enable_confirmations`, `minimum_password_length` 12, `otp_length` 6,
   `otp_expiry` 600, `max_frequency` 60s, SMTP through `smtp.resend.com` and
   the three templates. It
   isn't confirmed that `config push` carries the SMTP, OTP and template
   fields; if the diff lacks them, the wizard sets them through the Management
   API instead: `PATCH https://api.supabase.com/v1/projects/<ref>/config/auth`
   with a personal access token and the same values (`mailer_otp_length`,
   `mailer_otp_exp`, `smtp_*`, `mailer_subjects_*`,
   `mailer_templates_magic_link_content`,
   `mailer_templates_confirmation_content`,
   `mailer_templates_recovery_content`, `password_min_length`, read from the
   repository).
   Supabase's built-in sender only delivers to project team members, so
   without SMTP nobody else gets a code.
6. **First administrator.** Register on that environment's app (with a
   password), type the code
   from the e-mail, then run `make_admin` from your machine against its
   `DATABASE_URL`:
   `cd backend && DATABASE_URL='<that DATABASE_URL>' uv run python -m app.scripts.make_admin <email>`
7. **Database CA certificate (SR-11).** The backend connects to a hosted
   database only over TLS 1.2+ with the server's certificate and host name
   checked against the Supabase root CA, which it reads from
   `backend/app/certs/supabase-ca.crt`. Download it from Database settings →
   SSL Configuration → *Download certificate* and **commit it** at that path
   (it is public; `vercel.json` bundles it with `backend/app/**`). Without it
   the API refuses to start against a hosted `DATABASE_URL`; there is no
   fallback to unchecked TLS. Local URLs (`127.0.0.1`, `localhost`, `::1`)
   need no certificate. Do this before step 6: `make_admin` needs it too.
   `SUPABASE_URL` must be `https://` except for a local
   host, or the backend refuses to start.

### DNS

DNS moves from Namecheap to Vercel. Mail must keep working, so the order matters:

1. Add the domain to the Vercel project (remove it from any older Vercel project first).
2. In Vercel's DNS for the domain, add every record Resend lists for it (SPF,
   DKIM, the send subdomain's MX), the `_dmarc` TXT record, and any
   mail-forwarding MX records, **before** the nameservers change.
3. At Namecheap, set the domain's nameservers to Custom DNS
   `ns1.vercel-dns.com` and `ns2.vercel-dns.com`.
4. Remove the leftover mail records and email forwarding at Namecheap.
5. Wait for Vercel to show the domain as configured (it issues the HTTPS
   certificate itself) and for Resend to still show it as Verified.

### Cutover order

The cutover runs side by side, so there is never a window without Alerts:

1. Deploy on Vercel, with the Railway service still running.
2. Test the preview against staging: the SPA and `/api` load, staging's cron
   calls succeed, and a document upload under 4 MB works.
3. Set the production Vault values.
4. Switch the domain (DNS, above).
5. Confirm one scheduled daily check on Vercel: a `daily_check_run` row with
   `manual = false` after the switch.
6. Delete the Railway service.

### Manual checks

- **A preview serves the SPA and `/api`.** `curl -i <url>/api/me` returns
  FastAPI's JSON `401`. HTML means the `/api` rewrite is missing. FastAPI's
  `{"detail":"Not Found"}` means it didn't see the original `/api` path.
  `ModuleNotFoundError: app` in the function logs means `backend/app` wasn't
  bundled.
- **Responses come from `fra1`.** The `x-vercel-id` response header ends in
  `fra1::<id>` (for example `fra1::fra1::…`), and the deployment's Functions tab
  shows `fra1`.
- **The connection goes through port 6543 as `app_backend`.** Vercel's
  `DATABASE_URL` uses `app_backend.<project-ref>@…:6543`, and
  `SELECT usename, application_name, count(*) FROM pg_stat_activity WHERE usename = 'app_backend' GROUP BY 1, 2;`
  shows its sessions.
- **The cron calls succeed** on staging and production:

  ```sql
  SELECT status, return_message, start_time FROM cron.job_run_details
   WHERE jobid = (SELECT jobid FROM cron.job WHERE jobname = 'daily-check')
   ORDER BY start_time DESC LIMIT 5;
  SELECT status_code, timed_out, error_msg, created, content
    FROM net._http_response ORDER BY created DESC LIMIT 5;
  ```

  Expect `succeeded` and `200` with `{"ran": ...}`. A `404` means Vercel's
  `CRON_SECRET` and Vault's `cron_secret` differ. A `401` on staging means the
  protection bypass is missing or wrong.
- **Email still arrives after the DNS move.**

### One-time hosted reset

The rebuilt app does not migrate the old hosted data. The production Supabase
project is reset once and everyone registers again. The wizard offers this
(skip it if it has already been done):

1. Link the project, then reset it. This drops the old schema and applies
   `supabase/migrations/`. `--no-seed` keeps the local demo data, the
   `app_backend_dev` password and the local Vault values off hosted:
   `npx supabase@2.122.1 db reset --linked --no-seed`
2. Clear the old accounts and files. In the SQL editor run
   `DELETE FROM auth.users;`, then empty the `crew-documents` bucket in
   **Storage** (use the Dashboard, not SQL: Storage objects must be removed
   through the Storage API).
3. Continue with the `app_backend` password, Vault and first administrator
   above.

### Migrations are frozen after the cutover

From the cutover on, **a migration that has been pushed to hosted is never
edited**. Any schema change goes into a new migration file with a later
timestamp, and that file is pushed with `supabase db push`, to staging first,
then to production. Do not run `db reset --linked` on production again: it would
wipe production data.

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
│   │   ├── errors.py            # 422 without input echo; logged generic 500
│   │   ├── supabase_auth.py     # Passwords, e-mailed codes and TOTP (MFA) at Supabase Auth
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
│   │   ├── lib/                 # API client, sign-in helpers
│   │   └── context/             # Auth context
│   └── public/
├── api/
│   └── index.py                 # Vercel Python function: the FastAPI app
├── scripts/
│   └── hosted-cutover.sh        # Hosting setup and cutover wizard
├── vercel.json                  # Build, fra1 region, /api and SPA rewrites
├── docker-compose.yml           # Standalone MailHog; not needed (Supabase includes Mailpit)
└── README.md
```

## Third-party components and licences

Direct dependencies, with the versions locked at the time of writing
(`uv.lock`, `frontend/package-lock.json`). Every licence allows use in this
project. fpdf2 is LGPL-3.0: it is used unmodified as a separately installed
library.

| Component | Version | Licence |
|---|---|---|
| **Backend (Python)** | | |
| FastAPI | 0.138.0 | MIT |
| Uvicorn | 0.49.0 | BSD-3-Clause |
| asyncpg | 0.31.0 | Apache-2.0 |
| pydantic-settings | 2.14.2 | MIT |
| PyJWT | 2.13.0 | MIT |
| httpx | 0.28.1 | BSD-3-Clause |
| python-multipart | 0.0.32 | Apache-2.0 |
| Jinja2 | 3.1.6 | BSD-3-Clause |
| supabase (Python) | 2.31.0 | MIT |
| resend | 2.32.2 | MIT |
| pikepdf | 10.18.1 | MPL-2.0 |
| Pillow | 12.2.0 | MIT-CMU |
| fpdf2 | 2.9.0 | LGPL-3.0-only |
| ReportLab | 5.0.0 | BSD |
| tzdata | 2026.6 | Apache-2.0 |
| pyotp (dev) | 2.12.1 | MIT |
| pytest / pytest-cov / pytest-asyncio (dev) | 9.1.1 / 7.1.0 / 1.4.0 | MIT / MIT / Apache-2.0 |
| **Frontend (npm)** | | |
| React, React DOM | 19.2.7 | MIT |
| React Router | 7.18.0 | MIT |
| TanStack Query / Table | 5.101.0 / 8.21.3 | MIT |
| Tailwind CSS, @tailwindcss/vite | 4.3.1 | MIT |
| Radix UI Slider | 1.4.1 | MIT |
| lucide-react | 1.21.0 | ISC |
| react-dropzone | 15.0.0 | MIT |
| zustand | 5.0.14 | MIT |
| clsx / tailwind-merge | 2.1.1 / 3.6.0 | MIT |
| Vite (dev) | 8.0.16 | MIT |
| TypeScript (dev) | 6.0.3 | Apache-2.0 |
| **Services and tools** | | |
| Supabase CLI and local stack | 2.122.1 | Apache-2.0 (PostgreSQL: PostgreSQL Licence) |

Bundled data:

| File | Source | Licence | Downloaded |
|---|---|---|---|
| `backend/app/data/common_passwords.txt` (the 3,000 most common passwords of 12+ characters, lower-cased) | [SecLists](https://github.com/danielmiessler/SecLists), `Passwords/Common-Credentials/xato-net-10-million-passwords-1000000.txt`, commit `1a89b46` | MIT, Copyright (c) 2018 Daniel Miessler | 2026-11-20 |

The file's header repeats the source, licence and date.

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

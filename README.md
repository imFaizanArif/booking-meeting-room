# Kodifly Meeting Room Booking System

A production-ready meeting room booking system for Kodifly (50 employees).

| Layer      | Tech                                                                                   |
| ---------- | -------------------------------------------------------------------------------------- |
| Frontend   | Next.js 15 (App Router), TypeScript, Tailwind CSS v4, shadcn/ui, Framer Motion, Zustand, TanStack Query, FullCalendar, Lucide |
| Backend    | Python Flask, SQLAlchemy 2, Pydantic 2, Flask-CORS, Supabase Python SDK                 |
| Database   | Supabase PostgreSQL (with RLS + DB-level overlap prevention)                            |
| Auth       | Supabase Auth (email/password, forgot password)                                         |
| Deployment | Frontend → Vercel · Backend → Railway                                                   |

## Folder structure

```
kodifly-meeting-room/
├── supabase/
│   ├── schema.sql            # tables, enums, triggers, overlap exclusion constraint
│   ├── rls_policies.sql      # row-level security policies
│   └── seed.sql              # sample rooms (Alpha, Beta, Conference Hall, Brainstorm)
├── backend/
│   ├── requirements.txt
│   ├── wsgi.py               # gunicorn entrypoint
│   ├── Procfile / railway.json
│   ├── .env.example
│   └── app/
│       ├── __init__.py       # app factory, CORS, blueprints
│       ├── config.py         # env-driven configuration
│       ├── extensions.py     # SQLAlchemy engine + Supabase admin client
│       ├── models.py         # ORM models (profiles, rooms, bookings, attendees)
│       ├── schemas.py        # Pydantic validation schemas
│       ├── auth.py           # Supabase JWT verification decorators
│       ├── errors.py         # centralized error handling
│       ├── repositories/     # repository pattern (data access)
│       ├── services/         # service layer (business rules, conflict detection)
│       └── routes/           # REST endpoints (rooms, bookings, users, analytics)
└── frontend/
    ├── package.json, tsconfig.json, next.config.ts, postcss.config.mjs
    ├── .env.example
    └── src/
        ├── middleware.ts                 # session refresh + route protection
        ├── app/
        │   ├── layout.tsx, globals.css   # Inter font, Tailwind v4 design tokens
        │   ├── (auth)/                   # login, signup, forgot/reset password (+ server actions)
        │   └── (app)/                    # dashboard, rooms, rooms/[id], bookings,
        │                                 # calendar, profile, admin (loading/error states)
        ├── components/
        │   ├── ui/                       # shadcn/ui primitives
        │   ├── layout/                   # sidebar, topbar, theme toggle, logo
        │   ├── bookings/                 # booking dialog (conflict detection), booking card
        │   ├── rooms/, calendar/, dashboard/, admin/, illustrations/
        │   └── providers.tsx             # TanStack Query + next-themes + toaster
        ├── hooks/                        # TanStack Query hooks
        ├── lib/                          # API client, Supabase clients, types, utils
        └── stores/                       # Zustand UI store
```

## 1 · Supabase setup

1. Create a project at [supabase.com](https://supabase.com).
2. In the SQL Editor, run in order:
   1. `supabase/schema.sql`
   2. `supabase/rls_policies.sql`
   3. `supabase/seed.sql`
3. **Auth settings** (Authentication → Providers → Email): enable Email, keep
   "Confirm email" on.
4. **URL configuration** (Authentication → URL Configuration): set Site URL to
   your Vercel URL and add `http://localhost:3000` to redirect URLs.
5. Sign up through the app, then promote yourself to admin:

```sql
update public.profiles set role = 'admin' where email = 'you@kodifly.com';
```

## 2 · Backend (local)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your values
python wsgi.py         # http://localhost:5000
```

### Backend environment variables

| Variable                    | Where to find it                                              |
| --------------------------- | ------------------------------------------------------------- |
| `SUPABASE_URL`              | Project Settings → API → Project URL                          |
| `SUPABASE_SERVICE_ROLE_KEY` | Project Settings → API → `service_role` key (keep secret!)    |
| `SUPABASE_JWT_SECRET`       | Project Settings → API → JWT Settings → JWT Secret            |
| `DATABASE_URL`              | Project Settings → Database → Connection string (URI, pooler) |
| `SECRET_KEY`                | any long random string                                        |
| `CORS_ORIGINS`              | comma-separated: `http://localhost:3000,https://<your-app>.vercel.app` |

## 3 · Frontend (local)

```bash
cd frontend
npm install
cp .env.example .env.local   # fill in your values
npm run dev                  # http://localhost:3000
```

### Frontend environment variables

| Variable                        | Value                                            |
| ------------------------------- | ------------------------------------------------ |
| `NEXT_PUBLIC_SUPABASE_URL`      | Project Settings → API → Project URL             |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Project Settings → API → `anon` key              |
| `NEXT_PUBLIC_API_URL`           | `http://localhost:5000/api` (dev) / Railway URL + `/api` (prod) |
| `NEXT_PUBLIC_SITE_URL`          | `http://localhost:3000` (dev) / Vercel URL (prod) |

## 4 · Deploy everything to Vercel (recommended)

Both apps deploy to Vercel as **two projects from the same repo**. The frontend
proxies `/api/*` to the backend (same-origin, no CORS), so the API is reachable
at `https://<frontend-url>/api/...`.

### 4a · Backend project (Flask as a Vercel Python function)

The backend ships with `backend/vercel.json` and `backend/api/index.py`
(WSGI entrypoint) — no extra config files needed.

1. In [Vercel](https://vercel.com): **Add New Project**, import the repo, set
   **Root Directory** to `backend/`.
2. Framework preset: **Other** (auto-detected via `vercel.json`).
3. Add environment variables:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `DATABASE_URL` → Supabase **Session pooler** URI (IPv4-safe)
   - `SECRET_KEY` → any long random string
   - `CORS_ORIGINS` → `https://<your-frontend>.vercel.app` (harmless extra
     safety; the proxy makes calls same-origin anyway)
   - Optional: `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET`
4. Deploy, then note the URL, e.g. `https://kodifly-meeting-room-api.vercel.app`.
5. Verify: `GET https://<backend-url>/api/health` → `{"status": "ok"}`.

> Serverless note: on Vercel the engine automatically switches to `NullPool`
> (no connection pooling per instance) — always use the Supabase **pooler**
> connection string, never the direct `db.*.supabase.co` host.

### 4b · Frontend project (Next.js)

1. **Add New Project** again, import the same repo, set **Root Directory** to
   `frontend/` (framework preset: **Next.js**, auto-detected).
2. Add environment variables:
   - `NEXT_PUBLIC_SUPABASE_URL`
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `NEXT_PUBLIC_API_URL` → `/api`
   - `BACKEND_URL` → `https://<backend-url>` (no trailing slash, no `/api`)
   - `NEXT_PUBLIC_SITE_URL` → `https://<your-frontend>.vercel.app`
3. Deploy. The rewrite in `next.config.ts` makes
   `https://<frontend-url>/api/...` hit the Flask backend.
4. Post-deploy: add the frontend URL to Supabase Auth → URL Configuration
   (Site URL + redirect URLs, including
   `https://<your-frontend>.vercel.app/reset-password`).

> `BACKEND_URL` is read at **build time** — redeploy the frontend after
> changing it.

## 5 · Alternative: backend on Railway

`backend/Procfile` and `backend/railway.json` are also included. Deploy the
`backend/` directory on [Railway](https://railway.app) with the same env vars,
then set the frontend's `BACKEND_URL` to the Railway URL instead.

## API reference

All endpoints are prefixed with `/api` and require `Authorization: Bearer <supabase access token>`.

| Method | Endpoint                      | Access | Description                                |
| ------ | ----------------------------- | ------ | ------------------------------------------ |
| GET    | `/rooms`                      | all    | List rooms (`?search=&include_inactive=`)  |
| GET    | `/rooms/:id`                  | all    | Room detail                                |
| POST   | `/rooms`                      | admin  | Create room                                |
| PUT    | `/rooms/:id`                  | admin  | Update room                                |
| DELETE | `/rooms/:id`                  | admin  | Delete room                                |
| GET    | `/bookings`                   | all    | List bookings (`?room_id=&user_id=&status=&start_after=&end_before=&search=`) |
| GET    | `/bookings/:id`               | all    | Booking detail                             |
| GET    | `/bookings/availability`      | all    | Conflict check (`?room_id=&start_time=&end_time=`) |
| POST   | `/bookings`                   | all    | Create booking (validated + conflict-checked) |
| PUT    | `/bookings/:id`               | owner/admin | Update booking / approve / reject     |
| POST   | `/bookings/:id/cancel`        | owner/admin | Cancel booking                        |
| DELETE | `/bookings/:id`               | owner/admin | Delete booking                        |
| GET    | `/users`                      | all    | List employees (`?search=`)                |
| GET    | `/users/me` · PUT `/users/me` | self   | Read / update own profile                  |
| PUT    | `/users/:id`                  | admin  | Assign role, enable/disable                |
| GET    | `/analytics/dashboard`        | admin  | Totals, utilization, trend                 |
| GET    | `/health`                     | public | Health check                               |

## Conflict detection — defense in depth

1. **UI**: the booking dialog live-checks `/bookings/availability` and blocks submission.
2. **Service layer**: `BookingService._assert_no_conflict` re-validates on create/update.
3. **Database**: a `gist` exclusion constraint on `tstzrange(start_time, end_time)`
   makes double-booking impossible even under concurrent requests.
# booking-room
# booking-meeting-room

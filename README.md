# TeamsFlow Backend (FastAPI)

A starter backend for an HR / small team app (TeamFlow) built with FastAPI. It includes versioned API routers, Pydantic v2 schemas, placeholder services, SQLAlchemy session scaffolding, and MongoDB integration (Motor) with automatic index creation.

Features
- FastAPI app with health check and versioned routers under `/api/v1`
- Auth, employees, leaves, documents, settings, and lookups endpoints (stubs returning sample data)
- MongoDB integration via Motor with TLS CA bundle (certifi)
- Automatic MongoDB index creation on startup (idempotent)
- SQLAlchemy session base (for relational usage) with example models
- Pydantic v2 schemas, including Mongo document models using `_id` aliasing
- Minimal tests example using FastAPI TestClient

Tech Stack
- Python 3.11+
- FastAPI, Uvicorn
- Pydantic v2
- Motor (MongoDB), certifi, dnspython
- SQLAlchemy (scaffold only)

Project Structure
```
teamsflow-backend/
├── main.py
├── requirements.txt
├── .env
├── .gitignore
├── app/
│   ├── api/
│   │   └── v1/
│   │       ├── auth.py           # register/login/me
│   │       ├── employees.py      # CRUD with paging/search
│   │       ├── leaves.py         # list/get/create/decide/delete
│   │       ├── documents.py      # list/get/upload/delete
│   │       ├── settings.py       # profile/company/notifications
│   │       ├── lookups.py        # leave-types/statuses/roles
│   │       ├── users.py          # example stub
│   │       └── teams.py          # example stub
│   ├── core/
│   │   ├── config.py             # loads env (dotenv)
│   │   └── security.py           # auth helpers + current user stub
│   ├── db/
│   │   ├── session.py            # SQLAlchemy engine/session/Base
│   │   ├── mongo.py              # Motor client + helpers
│   │   └── mongo_indexes.py      # ensure_indexes() on startup
│   ├── models/                   # example SQLAlchemy models
│   │   ├── user.py
│   │   └── team.py
│   ├── schemas/
│   │   ├── auth_schema.py        # UserIn/LoginIn/UserOut/AuthResponse
│   │   ├── employee_schema.py    # EmployeeIn/Out + EmployeeDocument
│   │   ├── leave_schema.py       # LeaveIn/Out + LeaveDocument
│   │   ├── document_schema.py    # DocumentOut/List + DocumentDocument + UserDocument
│   │   ├── settings_schema.py    # Profile/Company/Notifications + SettingsDocument
│   │   ├── company_schema.py     # CompanyDocument
│   │   ├── lookup_schema.py      # LookupDocument
│   │   ├── team_schema.py        # example
│   │   └── user_schema.py        # example
│   ├── services/
│   │   └── team_service.py       # example placeholder
│   └── utils/
│       └── email.py              # example placeholder
└── tests/
    └── test_users.py             # sample TestClient test
```

Quickstart
- Python setup
  - Create venv: `python3 -m venv venv`
  - Activate: `source venv/bin/activate`
  - Install deps: `pip install -r requirements.txt`
- Environment
  - Copy `.env` and set values as needed:
    - `DATABASE_URL=sqlite:///./app.db`
    - `SECRET_KEY=super-secret-key`
    - `MONGODB_URI=mongodb+srv://<user>:<pass>@<cluster>/<params>`
    - `MONGODB_DB_NAME=teamflow`
- Run the server
  - `uvicorn main:app --reload --port 5001`
  - Health: GET `http://localhost:5001/health`

Dashboard Analytics (new)
- Endpoints under `/api/v1/dashboard` provide admin dashboard features:
  - `GET /summary` → employees, pending leaves, documents this week, on leave today
  - `GET /alerts` → red flags based on thresholds (pending leaves)
  - `GET /trends?months=6` → headcount trend points for last N months
  - `GET /scorecards` → department scorecards (employees, pending leaves, active assignments)
  - `GET /drilldown?metric=pending_leaves&group_by=department` → breakdown by department
  - `GET /export.csv` → CSV export of summary metrics
- Feature flags (env vars; default enabled):
  - `FEATURE_DASHBOARD_ALERTS`, `FEATURE_DASHBOARD_TRENDS`, `FEATURE_DASHBOARD_DRILLDOWN`, `FEATURE_DASHBOARD_EXPORT`, `FEATURE_DASHBOARD_SCORECARDS`
- Frontend flags (Vite env; default enabled):
  - `VITE_FEATURE_DASHBOARD_ALERTS`, `VITE_FEATURE_DASHBOARD_TRENDS`, `VITE_FEATURE_DASHBOARD_DRILLDOWN`, `VITE_FEATURE_DASHBOARD_EXPORT`, `VITE_FEATURE_DASHBOARD_SCORECARDS`

Audit utility
- `python3 scripts/audit_dashboard_features.py --frontend /path/to/teamflow` prints JSON status for key analytics features.

Seeding MongoDB
- Purpose: populate required collections with sample data (companies, settings, lookups, users, employees, leaves, documents).
- Command:
  - `python -m scripts.seed_mongo`
  - or `python scripts/seed_mongo.py`
- Behavior:
  - Idempotent upserts using stable IDs and unique keys (won't duplicate on repeated runs).
  - Ensures MongoDB indexes before inserting.
  - Uses `.env` for `MONGODB_URI` and `MONGODB_DB_NAME`.

Configuration
- `.env` is loaded by `python-dotenv` in `app/core/config.py`.
- MongoDB
  - Uses Motor (async) client with `certifi` CA bundle to avoid TLS issues with MongoDB Atlas.
  - Ensure your Atlas project allows your IP (Network Access) and the URI/credentials are valid.
- SQLAlchemy
  - `app/db/session.py` sets up `engine`, `SessionLocal`, and `Base`.
  - Example models exist in `app/models`, but current API stubs use in-memory data.

API Overview (stubs)
- Root/Health
  - `GET /` → welcome payload
  - `GET /health` → `{ "status": "ok" }`
- Auth (`/api/v1/auth`)
  - `POST /register` body: `{ first_name, last_name, email, password, company_name }` → `{ user, token }`
  - `POST /login` body: `{ email, password }` → `{ user, token }`
  - `GET /me` → `UserOut` (current user stub)
- Employees (`/api/v1/employees`)
  - `GET /` query: `page,size,search` → paginated list
  - `GET /{employee_id}` → `EmployeeOut`
  - `POST /` → `EmployeeOut`
  - `PUT /{employee_id}` → `EmployeeOut`
  - `DELETE /{employee_id}` → status
- Leaves (`/api/v1/leaves`)
  - `GET /` query: `page,size,status` → paginated list
  - `GET /{leave_id}` → `LeaveOut`
  - `POST /` → `LeaveOut` (pending)
  - `PATCH /{leave_id}` body: `{ action: approve|reject, comment? }` → `LeaveOut`
  - `DELETE /{leave_id}` → status
- Documents (`/api/v1/documents`)
  - `GET /` query: `page,size,employee_id?` → paginated list
  - `GET /{document_id}` → `DocumentOut`
  - `POST /` multipart: `file` (+ `employee_id?`) → `DocumentOut`
  - `DELETE /{document_id}` → status
- Settings (`/api/v1/settings`)
  - `GET /profile` / `PUT /profile`
  - `POST /password`
  - `GET /company` / `PATCH /company`
  - `GET /notifications` / `PATCH /notifications`
- Lookups (`/api/v1/lookups`)
  - `GET /leave-types` | `GET /statuses` | `GET /roles`
- Examples
  - Users (`/api/v1/users`) and Teams (`/api/v1/teams`) return static sample data.

MongoDB Collections and Schemas
- Users: unique `email` and index on `company_id` (see `UserDocument` in `document_schema.py`)
- Employees: indexes on `company_id`, `email` (see `EmployeeDocument`)
- Leaves: indexes on `employee_id`, `status`, composite `(company_id, status)` (see `LeaveDocument`)
- Documents: indexes on `company_id`, `employee_id` (see `DocumentDocument`)
- Companies: `CompanyDocument` with nested `settings`
- Settings: unique on `company_id` (see `SettingsDocument`)
- Lookups: composite index `(category, code)` (see `LookupDocument`)

Indexes
- Created during app startup via `ensure_indexes()` in `app/db/mongo_indexes.py`.
- Startup won’t crash if index creation fails; it logs a warning (see `main.py`).

Security
- `create_access_token` in `app/core/security.py` returns a random token (not a real JWT).
- `get_current_user` is a stub; replace with proper auth (JWT/OAuth2 + password hashing) before production.

Testing
- Example test: `tests/test_users.py`
- Install pytest to run: `pip install pytest`
- Run: `pytest -q`

Troubleshooting
- Mongo TLS errors with Atlas
  - Ensure `certifi` is installed (already in requirements) and your venv is active.
  - Verify your IP is allowed in Atlas (Network Access) and SRV DNS resolution works.
- Port already in use
  - Change the port: `uvicorn main:app --reload --port 8000`
- Env not applied
  - Ensure `.env` exists and keys are set; restart the server.

Next Steps (optional)
- Replace auth stubs with real JWT (PyJWT) and password hashing (Passlib/argon2).
- Persist data: implement CRUD using Motor for MongoDB and/or SQLAlchemy for relational data.
- Add Alembic for relational migrations if using SQLAlchemy.
- Add CI, linting (ruff), formatting (black), and richer tests.

# Contracting Platform (Flask + MongoDB)

A B2B work-order platform for a plumbing/building contracting company —
Flask edition. Same business logic as the Django version, rebuilt on
Flask + MongoDB, with a custom "dispatch board" design and Google
sign-in.

- Client companies raise work orders with us.
- We quote them; once accepted, we either do the job in-house or
  subcontract it out to a partner company.
- Partner companies can accept/decline what's offered to them.
- Companies can self-register (password or "Continue with Google"), or
  join a company that's already in the system. Internal staff accounts
  are **not** self-service — see below.

## 1. Install dependencies

```bash
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Mac/Linux

pip install -r requirements.txt
```

## 2. Set up MongoDB

Pick one:

**A. Local MongoDB** — install MongoDB Community Server for your OS
from https://www.mongodb.com/try/download/community, then make sure
`mongod` is running. The default connection string
(`mongodb://localhost:27017/contracting_platform`) will work as-is.

**B. MongoDB Atlas (free cloud tier)** — create a free cluster at
https://www.mongodb.com/cloud/atlas, create a database user, allow
your IP, and copy the connection string it gives you.

Then copy the env file and fill in `MONGO_URI` if you're using Atlas:

```bash
cp .env.example .env
```

## 3. (Optional) Set up "Continue with Google"

The app works fine without this — the Google button just won't appear.
To enable it:

1. Go to https://console.cloud.google.com/ and create a project (or
   use an existing one).
2. **APIs & Services → OAuth consent screen** — set it up for
   "External" users, add your email as a test user if it's still in
   testing mode.
3. **APIs & Services → Credentials → Create Credentials → OAuth
   client ID** → Application type: **Web application**.
4. Under **Authorized redirect URIs**, add:
   `http://127.0.0.1:5000/auth/google/callback`
   (update the host/port if you run it elsewhere).
5. Copy the generated **Client ID** and **Client Secret** into `.env`:
   ```
   GOOGLE_CLIENT_ID=your-client-id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your-client-secret
   ```

When someone signs in with Google for the first time, they're asked
one extra question (which company they represent) before their
account is created — Google doesn't know that part.

## 4. Run it

```bash
flask --app run seed-demo         # optional: demo users + one sample order
flask --app run create-staff admin --email admin@example.com   # internal staff account, prompts for password
python run.py
```

Visit `http://127.0.0.1:5000/`.

## Demo logins (after `seed-demo`)

| Role                     | Username      | Password     |
|---------------------------|---------------|--------------|
| Our own staff              | staffuser     | testpass123  |
| Client company (Acme)      | acmeuser      | testpass123  |
| Partner company (FastFix)  | fastfixuser   | testpass123  |

## Creating accounts

- **Client/partner companies**: `/signup` — register a new company,
  join an existing one, or use "Continue with Google". This
  deliberately has **no "staff" option** — letting anyone self-register
  as our own staff would let them see every company's orders.
- **Internal staff**: `flask --app run create-staff <username>` from
  the terminal, or add a `users` document directly in MongoDB with
  `company_id: null`.

## Project structure

- `app/models.py` — the MongoDB data-access layer (Company, User,
  WorkOrder, Quote, Subcontract) — plain dicts in/out via pymongo, no ORM
- `app/auth.py` — login, logout, password signup, Google OAuth
- `app/orders.py` — dashboards, order detail, quote/subcontract actions,
  in-house/completion lifecycle
- `app/templates/` — custom HTML templates (no Bootstrap)
- `app/static/css/style.css` — the design system
- `app/commands.py` — `seed-demo` and `create-staff` CLI commands

## Work order lifecycle

`new` → `quoted` (staff adds a quote) → `accepted` (client accepts) → then either:
- `in_progress` (staff clicks **Start in-house work**) → `completed`
  (staff clicks **Mark completed**), or
- `subcontracted` (staff offers it to a partner) → `in_progress` once
  the partner accepts → `completed` (staff clicks **Mark completed** —
  this button is driven purely by status, so it appears here too, not
  just after the in-house path).

Every action is checked twice: hidden in the template for the wrong
role, and rejected in the route itself if someone hits the URL
directly as the wrong role or wrong status.

## Notes / what's not built yet

- No password reset flow.
- No invoicing UI.
- No file/photo uploads for job sites.
- This was tested against a mock MongoDB (mongomock) standing in for
  a real server, since no MongoDB instance was available in the build
  environment — the logic is fully exercised, but do a quick click-
  through once you've got real MongoDB connected, just in case.

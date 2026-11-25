# GoalStream

GoalStream is a responsive football fixtures, scores, competitions, favourites, and authorized broadcaster app. The frontend uses React, Vite, React Router, Tailwind CSS, and HLS.js. The GoalStream backend is Python with Flask, SQLAlchemy, Flask-Migrate, JWT authentication, and PostgreSQL.

## Local setup

Requirements: Python 3.11+, Node.js 20+, and PostgreSQL 15+.

1. Create a PostgreSQL role and database for the app. On Ubuntu, open the PostgreSQL prompt with `sudo -u postgres psql`, then run:

   ```sql
   CREATE ROLE goalstream_user WITH LOGIN PASSWORD 'choose-a-password';
   CREATE DATABASE goalstream OWNER goalstream_user;
   ```

   Exit with `\q`. If the role or database already exists, keep it and use its existing credentials instead.
2. Create and activate a Python virtual environment from the project root:

   ```sh
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r backend/requirements.txt
   ```

3. Copy `backend/.env.example` to `backend/.env`. Set `DATABASE_URL` to the role, password, and database you created. Set `JWT_ACCESS_SECRET` and `FLASK_SECRET_KEY` to independent random secrets of at least 32 characters. Matchora works without a token; if you choose API-Football or football-data, configure its server-side token. URL-encode special characters in the database password.
4. Apply the checked-in Flask-Migrate database migration:

   ```sh
   flask --app backend.app db upgrade
   ```

   On later schema changes, run `flask --app backend.app db migrate -m "describe change"` followed by `flask --app backend.app db upgrade`, and commit the generated migration.
5. Install frontend dependencies from the project root with `npm install`.
6. Start both services with `npm run dev`. Flask listens at `http://localhost:5000`; Vite listens at `http://localhost:5173`. The client API URL can be overridden with `VITE_API_URL`.

For production, set `APP_ENV=production`, `COOKIE_SECURE=true`, use HTTPS, and set `RATELIMIT_STORAGE_URI` to a shared Redis URL so rate limits persist across workers. Start the API with `gunicorn --bind 0.0.0.0:5000 backend.app:app` after installing `backend/requirements.txt`.

## Football data providers

Responses are fetched by Flask and cached for 60 seconds. The backend also enforces configurable upstream limits through `FOOTBALL_PROVIDER_RPM` and `FOOTBALL_PROVIDER_DAILY_LIMIT`.

- `FOOTBALL_PROVIDER=matchora` uses Matchora's public schedule (`watchable=1`), live, scores, event, channel catalog, and replay endpoints. It requires no API key; set `MATCHORA_BASE_URL` only if you need a different base domain. Match details, the channel guide, and replays use the provider's iframe embeds and health-checked fallback domains; the embedded player and its advertising are left intact. Upstream requests are cached and limited per minute; Matchora traffic does not use the daily quota configured for keyed providers.
- `FOOTBALL_PROVIDER=api-football` with `API_FOOTBALL_KEY`. Its published free plan includes 100 requests/day; the published Pro plan is $16/month for 7,500 requests/day. See [API-Football pricing](https://www.api-football.com/pricing).
- `FOOTBALL_PROVIDER=football-data` with `FOOTBALL_DATA_TOKEN`. Its free tier covers 12 competitions with delayed scores and 10 calls/minute. Its published live-score tier is €12/month. Check [pricing](https://www.football-data.org/pricing) and [coverage](https://www.football-data.org/coverage) because coverage differs from API-Football.

The default quotas (8 requests/minute and 90/day) are conservative for free tiers. Adjust them only to limits allowed by the selected provider plan. Football data services supply scores and fixtures, not video rights.

## Accounts and admin setup

Users register and sign in with email/password. Passwords use Werkzeug's password hashing. Access tokens are short-lived JWTs; refresh tokens are random, stored hashed in PostgreSQL, rotated on refresh, and sent in an HTTP-only cookie.

After registering the first administrator account, promote it in PostgreSQL:

```sql
UPDATE "user" SET role = 'ADMIN' WHERE email = 'admin@example.com';
```

The admin view can manage users, teams, competitions, and streaming source availability. Stream records must include an HTTPS URL and an authorization/license reference. The reference is recorded as administrator-provided evidence; the app cannot independently verify broadcast rights. Only enter a source the platform is licensed to link to or play.

## API overview

- Auth: `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/refresh`, `POST /api/auth/logout`, `GET /api/auth/profile`
- Matches: `GET /api/matches`, `/api/matches/live`, `/api/matches/upcoming`, `/api/matches/:id`, `/api/matches/:id/streams`
- Competitions and teams: `GET /api/competitions`, `/api/competitions/:id`, `/api/teams`, `/api/teams/:id`
- Streams: `GET /api/streams`, `/api/streams/:id`
- Favourites: authenticated `GET/POST /api/favourites`, `DELETE /api/favourites/:id`
- Admin: `/api/admin/dashboard`, `/api/admin/users`, `/api/admin/streams`, `/api/admin/teams`, `/api/admin/competitions`
- Health: `GET /api/health`

`GET /api/football/fixtures`, `/api/football/competitions`, `/api/football/teams`, and `/api/football/standings` expose provider-compatible data for the UI.

If no provider key is configured, the football views show an unavailable state instead of sample fixtures or scores. If there is no active authorized source for a match, the UI says streaming is unavailable.

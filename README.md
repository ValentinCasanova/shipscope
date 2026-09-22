# ShipScope

A rate-shopping and order-sync dashboard: sign in with Google, connect a Google Sheet of orders, compare live carrier rates via EasyPost, and flag unusual orders with a small LLM tool-call.

**Stack:** React + TypeScript (Vite) · Django REST Framework · PostgreSQL · Docker · AWS (ECS Fargate, RDS, S3 + CloudFront) via Terraform · GitHub Actions

> **Status: foundation.** The local development environment works end to end: PostgreSQL, a Django API with a health endpoint, and a React page that shows whether the API and the database are up. The product features and the AWS deployment come next.

## Prerequisites

To run the app you need:

- **Docker Engine with the Compose plugin.** Tested on Ubuntu with Docker Engine 29.8 and Compose 5.5, not with Docker Desktop.
- **git**, and **Python 3** to generate a secret key.

To run tests, linters, and git hooks on your machine you also need:

| Tool | Version | Notes |
|---|---|---|
| [uv](https://docs.astral.sh/uv/) | 0.12 | Installs Python 3.14 (from `backend/.python-version`) if you don't have it |
| [Node.js](https://nodejs.org/) | 24.15 or a later 24.x | `.nvmrc` selects Node 24 for `nvm use` |
| [pre-commit](https://pre-commit.com/) | 4.x | For example, `uv tool install pre-commit` |
| [Terraform](https://developer.hashicorp.com/terraform/install) | 1.16 | For the `terraform fmt` hook and the infrastructure in `infra/` |

## Quickstart

```bash
git clone https://github.com/ValentinCasanova/shipscope.git
cd shipscope
cp .env.example .env
# Fill in DJANGO_SECRET_KEY with a random value. On macOS, use sed -i '' instead of sed -i.
sed -i "s/^DJANGO_SECRET_KEY=$/DJANGO_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')/" .env
docker compose up --build
```

Open http://localhost:5173. The page shows **API: ok** and **Database: ok**. http://localhost:8000/api/health/ returns the same status as JSON.

- The first run downloads base images and installs dependencies, which takes a few minutes. Later starts take about 10 to 20 seconds.
- On its first start, the backend creates the database tables before it accepts requests. If the page shows "API unavailable", reload it a few seconds later.
- Edits to files in `backend/` and `frontend/` apply without a restart: Django reloads itself, and Vite updates the open page.
- To stop, press Ctrl+C or run `docker compose stop`. The next `docker compose up` reuses the containers.
- `docker compose down` removes the containers and keeps the database. `docker compose down -v` also **deletes the database**.

## How it runs locally

`docker compose up` starts three services:

| Service | What runs | Address |
|---|---|---|
| `frontend` | Vite dev server for the React app | http://localhost:5173 |
| `backend` | Django's development server. It applies migrations when the container starts. | http://localhost:8000 |
| `db` | PostgreSQL 17 | `localhost:5432` |

```text
browser ──► frontend :5173 (Vite) ──/api/*──► backend :8000 (Django) ──► db :5432 (PostgreSQL)
```

The React app calls the API with relative `/api/...` URLs, and the Vite dev server forwards those requests to the backend. The page and the API share one origin, so the browser never makes a cross-origin request and the API needs no CORS configuration. In deployed environments, CloudFront will take over the dev server's role: it will serve the built frontend and forward `/api/*` to the API.

The `backend/` and `frontend/` folders are mounted into their containers, so the containers run your working copy. The frontend container keeps its own `node_modules` in a separate volume. Ports are published on 127.0.0.1 only, so other machines on your network can't reach them.

## Environment variables

Settings come from environment variables. Compose passes the repo-root `.env` to the `db` and `backend` containers. Commands you run on your machine, such as `manage.py` and `pytest`, load the same file, and variables already set in your shell take precedence over it.

| Variable | Read by | Local value | Notes |
|---|---|---|---|
| `DJANGO_SECRET_KEY` | backend | Random, generated per machine | Required |
| `DJANGO_DEBUG` | backend | `true` | `false` when unset |
| `DJANGO_ALLOWED_HOSTS` | backend | `localhost,127.0.0.1` | Comma-separated host names Django serves |
| `POSTGRES_DB` | db, backend | `shipscope` | |
| `POSTGRES_USER` | db, backend | `shipscope` | |
| `POSTGRES_PASSWORD` | db, backend | `shipscope-local` | Required. For local use only. |
| `POSTGRES_HOST` | backend | `localhost` | Compose sets `db` for the backend container |
| `POSTGRES_PORT` | backend | `5432` | |
| `API_PROXY_TARGET` | Vite dev server | Not set | Where the dev server forwards `/api/` requests: `http://localhost:8000` when unset, and Compose sets `http://backend:8000`. It comes from the dev server's environment, not from `.env`. |

## Working on your machine

Tests, linters, and git hooks run on your machine, using the tool versions pinned in `backend/uv.lock` and `frontend/package-lock.json`. Set them up once per clone:

```bash
(cd backend && uv sync)
(cd frontend && npm ci)
pre-commit install
```

If you ran `docker compose up` first, `npm ci` fails with `EACCES`: Docker has created an empty `frontend/node_modules` folder owned by root. Remove it with `rmdir frontend/node_modules` (no sudo needed, since it's empty) and run `npm ci` again.

### Backend

Run these in `backend/`. Commands that use the database need it running: `docker compose up -d db`.

| Task | Command |
|---|---|
| Run the tests | `uv run pytest` |
| Lint and format | `uv run ruff check --fix .` and `uv run ruff format .` |
| Create migrations | `uv run python manage.py makemigrations` |
| Apply migrations | `uv run python manage.py migrate`, or `docker compose restart backend` |
| Add a dependency | `uv add <package>`, then rebuild the container with `docker compose up --build backend` |

### Frontend

Run these in `frontend/`.

| Task | Command |
|---|---|
| Run the tests | `npm test` |
| Type-check | `npm run typecheck` |
| Lint | `npm run lint` |
| Format, or check formatting | `npm run format`, or `npm run format:check` |
| Build for production | `npm run build` (writes `dist/`) |
| Add a dependency | `npm install <package>`, then rebuild the container with `docker compose up --build -V frontend` |

### Git hooks

Every commit runs file checks, [gitleaks](https://github.com/gitleaks/gitleaks) secret scanning, Ruff, Prettier, and ESLint, and for the files it touches, `terraform fmt`, [actionlint](https://github.com/rhysd/actionlint) for GitHub Actions workflows, and [ShellCheck](https://www.shellcheck.net/) for shell scripts. To run every hook on the whole repository, use `pre-commit run --all-files`. The hooks call `uv`, `node`, `npm`, and `terraform`, and actionlint runs in Docker, so commit from a terminal where those commands work.

The gitleaks hook scans only the changes being committed. To scan every commit in the history, as CI does, run `pre-commit run --hook-stage manual gitleaks-history`.

## API

| Endpoint | Authentication | Response |
|---|---|---|
| `GET /api/health/` | None | `{"status": "ok", "database": "ok"}`, or `"database": "unavailable"` when the database doesn't answer a `SELECT 1` |

The health endpoint returns 200 whenever the Django process is running, even while the database is down, so a load balancer doesn't replace working containers during a database outage. Django REST framework is configured to require authentication by default, so every endpoint added later is closed unless its view opts out.

## Production image

`backend/Dockerfile` builds the image that deployed environments will run. A builder stage installs the locked dependencies into a virtualenv. The runtime stage copies in only that virtualenv and the code, collects static files, and runs Gunicorn as a non-root user. Compose builds the same image and replaces Gunicorn with Django's development server.

To build it and run it against the Compose database, start `db` (`docker compose up -d db`), then run:

```bash
docker build --target runtime -t shipscope-backend:prod backend
docker run --rm --network shipscope_default -p 127.0.0.1:8001:8000 \
  --env-file .env -e POSTGRES_HOST=db -e DJANGO_DEBUG=false shipscope-backend:prod
```

Gunicorn then serves http://localhost:8001/api/health/. It starts one worker unless `WEB_CONCURRENCY` is set. The image is about 230 MB unpacked, 143 MB of it the `python:3.14-slim` base, and 64 MB compressed.

The frontend has no production container: `npm run build` produces static files, and `frontend/Dockerfile.dev` exists only for local development.

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | Django REST API, managed with uv. `config/` holds the settings and URL routes, and `core/` the health endpoint. |
| `frontend/` | React + TypeScript app built with Vite. `src/api/` holds the typed API client, and `src/components/` the UI. |
| `infra/` | Terraform for the AWS environments. See [`infra/README.md`](infra/README.md). |
| `docker-compose.yml` | The local development stack |
| `.env.example` | Template for your local `.env` |
| `.pre-commit-config.yaml` | Git hooks |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `permission denied` connecting to `docker.sock` | Your user isn't in the `docker` group yet, or the change hasn't taken effect | `sudo usermod -aG docker $USER`, then log out completely and back in, or reboot |
| `env file … .env not found` | `.env` doesn't exist yet | Follow the [Quickstart](#quickstart): copy `.env.example` to `.env` and set `DJANGO_SECRET_KEY` |
| The backend exits with `ImproperlyConfigured` naming `DJANGO_SECRET_KEY` | The key is missing or empty in `.env` | Set `DJANGO_SECRET_KEY` in `.env`, for example with the `sed` line from the [Quickstart](#quickstart) |
| `port is already allocated` or `address already in use` | Something else uses port 5432, 8000, or 5173, such as a local PostgreSQL or `npm run dev` | Stop it, or change the host port in `docker-compose.yml` |
| `npm ci` fails with `EACCES` on `frontend/node_modules` | `docker compose up` ran before `npm ci`, and Docker created the folder as root to mount the container's `node_modules` volume | `rmdir frontend/node_modules`, then `npm ci` |
| `400 Bad Request`, or `DisallowedHost` in the backend log | The host name isn't in `DJANGO_ALLOWED_HOSTS`. Django also rejects host names that contain underscores. | Add the host to `DJANGO_ALLOWED_HOSTS` in `.env`, and don't use `_` in Compose service names |
| `password authentication failed` after changing a `POSTGRES_*` value | The Postgres image applies `POSTGRES_*` only when it initializes an empty volume, so an existing database keeps its original user and password | Change the value back, or reset the database with `docker compose down -v` (this deletes its data) |
| `ModuleNotFoundError` in the backend container after `uv add` | The container uses the packages installed in its image; the mounted folder updates code, not packages | `docker compose up --build backend` |
| The frontend container can't find a package you just installed | A recreated container keeps its old `node_modules` volume | `docker compose up --build -V frontend` |
| `Permission denied` when a container writes to your files, or files you can't edit | Containers write to mounted folders as their own user. The backend runs as UID 10001, which can't write your files, and a container running as root creates files you don't own. | Run `makemigrations`, `uv add`, and `npm install` on your machine, not in a container |
| Vite doesn't update the page after you edit a file | File-change events don't reach the container (rare with Docker Engine on Linux) | Set `server.watch.usePolling` to `true` in `frontend/vite.config.ts` |
| `docker compose ps` shows a `sha256:…` ID instead of an image name | Every build records new build metadata, so a rebuild without changes still gives the image a new ID. Compose keeps a container whose image content hasn't changed. | Nothing; it's harmless |
| Docker volumes use more and more disk space | `docker compose down` and `up -V` leave the frontend's previous `node_modules` volume behind, about 160 MB each time | `docker volume prune` deletes unused anonymous volumes from every project on your machine, and keeps named volumes such as the database's |
| Code with type errors passes `tsc --noEmit` | The root `tsconfig.json` only references the other two configs, so `tsc --noEmit` checks no files | Use `npm run typecheck`, which runs `tsc -b` |
| npm reports a peer-dependency conflict with typescript-eslint | TypeScript 7 got installed, but typescript-eslint supports only versions below 6.1 | Keep `typescript` at `~6.0` in `package.json` |
| A git hook fails with `command not found` | The one-time setup hasn't run, or the git client can't find `uv`, `node`, `npm`, or `terraform` (for example, a GUI app that doesn't load nvm) | Run the setup in [Working on your machine](#working-on-your-machine), and commit from a terminal |
| A frontend test of an error state is slow or times out | TanStack Query retries a failed query 3 times by default | Render with `renderWithQueryClient` from `src/test/render.tsx`, which turns retries off |

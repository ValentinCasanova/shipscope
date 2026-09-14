# ShipScope

A rate-shopping and order-sync dashboard: sign in with Google, connect a Google Sheet of orders, compare live carrier rates via EasyPost, and flag unusual orders with a small LLM tool-call.

**Stack:** React + TypeScript (Vite) · Django REST Framework · PostgreSQL · Docker · AWS (ECS Fargate, RDS, S3 + CloudFront) via Terraform · GitHub Actions

> 🚧 Work in progress — local development environment is being set up. Setup instructions will land here shortly.

## Repository layout

| Path | Contents |
|---|---|
| `backend/` | Django REST API (managed with [uv](https://docs.astral.sh/uv/)) |
| `frontend/` | React + TypeScript single-page app |
| `infra/` | Terraform for AWS infrastructure |

## Git hooks

Every commit runs formatting, linting, and secret-scanning hooks through [pre-commit](https://pre-commit.com/). The hooks use the tool versions pinned in each project's lockfile, so after cloning, install both projects once and enable the hooks:

```bash
(cd backend && uv sync)
(cd frontend && npm ci)
pre-commit install
```

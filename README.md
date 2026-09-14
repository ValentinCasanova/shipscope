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

# Local testing stack (Docker)

Runs the whole app locally in containers: Postgres with all migrations and seed
data, a Supabase-compatible REST layer (PostgREST behind nginx), a Upstash-compatible
Redis (cache + rate limiting), the Hono API (Wrangler), and the TanStack Start web app.

No host Node, Postgres, Supabase CLI, or cloud credentials needed.

## Run

```bash
docker compose up            # db + backend + api + web
docker compose --profile mcp up   # also the MCP server
docker compose down -v       # stop and wipe the database
```

First start pulls images and runs one `npm install` inside the api/web containers
(shared via a volume), so it takes a few minutes. Later starts are fast.

## URLs (host)

| Service | URL | Notes |
|---|---|---|
| Web | http://localhost:3000 | TanStack Start SSR |
| API | http://localhost:8787 | Hono on Wrangler |
| Gateway | http://localhost:54321 | Supabase REST (`/rest/v1/*`) |
| Upstash shim | http://localhost:8079 | REST over Redis |
| Postgres | localhost:54322 | user `postgres` / pass `postgres` |
| MCP | http://localhost:8000/mcp | with `--profile mcp` |

## Port already in use?

Each host port is overridable. If something already runs on 3000:

```bash
WEB_PORT=4321 docker compose up
```

Available: `WEB_PORT`, `API_PORT`, `GATEWAY_PORT`, `SRH_PORT`, `DB_PORT`, `MCP_PORT`.
`API_PORT` also updates the browser's `VITE_API_URL` automatically.

## What is and isn't real

- Search runs FTS-only here: there is no OpenAI key, so the API skips the embedding
  call and the semantic layer. Set `OPENAI_API_KEY` on the `api` service to enable it.
- Admin routes need a real Supabase Auth (GoTrue) JWT, which this minimal stack does
  not run. The auth gate itself works (401/403); the happy path needs GoTrue.
- The JWTs in `compose.yaml` and `api.dev.vars` are signed with the local
  `PGRST_JWT_SECRET` and are not secrets.

## Files

- `compose.yaml` (repo root) — the stack
- `local/migrate.sh` — applies migrations then seeds (idempotent)
- `local/seed.sql` — sample regulations, nodes, and a compliance mapping
- `local/nginx.conf` — maps `/rest/v1/*` to PostgREST
- `local/api.dev.vars` — reference env for running `wrangler dev` on the host
  (the compose api service passes the same values via `--var`)

## Running a piece on the host instead

To run the API or web on the host (not in Docker) against this stack, copy
`local/api.dev.vars` to `apps/api/.dev.vars` (change `gateway`/`srh` to
`localhost:54321` / `localhost:8079`) and use Node 22.

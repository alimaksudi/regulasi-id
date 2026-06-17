# Contributing

---

## Branches

| Branch | Purpose |
|--------|---------|
| `main` | Production. Auto-deploys to Vercel. |
| `feat/short-description` | New features |
| `fix/short-description` | Bug fixes |
| `chore/short-description` | Tooling, deps, docs |
| `db/short-description` | Database migrations only |

Push to `main` directly for small fixes. For anything touching the DB schema or significant frontend changes, use a branch + PR.

---

## Commits

Short imperative subject line. No period.

```
feat: add compliance checklist page
fix: search returns empty for SEOJK queries
chore: bump supabase-js to 2.x
db: add compliance_mappings table (migration 009)
```

Use `db:` prefix for any commit that includes a migration file — makes it easy to find schema changes in git log.

---

## Pull Requests

Keep PRs focused — one concern per PR. Large schema changes and large UI changes should be separate PRs.

PR title follows the same format as commit messages.

PR description must include:
- What changed and why (not what the code does)
- For DB migrations: what tables/functions are added/changed
- For frontend: screenshot or recording of the UI change
- Test plan: what you tested manually before opening the PR

---

## Database Migrations

Always check the next migration number before creating one:

```bash
ls packages/supabase/migrations/ | sort | tail -5
```

File naming: `NNN_short_description.sql` (e.g., `009_compliance_mappings.sql`)

Rules:
- Always enable RLS on new tables
- Always add public read policy for legal content tables
- Always add indexes for columns used in WHERE/JOIN/ORDER BY
- Run migration against a **test Supabase project** first, not production
- Apply via Supabase SQL Editor (not `supabase db push` — the hosted project is managed directly)

Do not:
- Rename or delete existing migration files
- Edit a migration that's already been applied to production
- Use `DROP TABLE` or `DROP COLUMN` without a plan for zero-downtime

---

## Code Review Checklist

Before merging, verify:

- [ ] TypeScript: `npx tsc --noEmit` passes
- [ ] Lint: `npm run lint` clean
- [ ] Unit tests pass: `npm run test:run`
- [ ] Migration CI passes (applies cleanly to test Supabase project)
- [ ] All new API route inputs validated with Zod schema
- [ ] Rate limiting uses Upstash (not in-memory)
- [ ] No hardcoded hex colors (use CSS variables)
- [ ] No `useTranslations` in async Server Components (use `getTranslations`)
- [ ] Navigation uses `@/i18n/routing` imports, not `next/link`
- [ ] Admin routes call `requireAdmin()` at top
- [ ] No `SUPABASE_SERVICE_ROLE_KEY` exposed to client code
- [ ] New public pages have `generateMetadata` with hreflang alternates
- [ ] New tables have RLS + public read policy
- [ ] New migrations numbered correctly and include `SET search_path` on functions
- [ ] pgvector columns have `hnsw` index with `vector_cosine_ops`
- [ ] List endpoints use cursor pagination, not offset
- [ ] Error paths call `Sentry.captureException()`

---

## Local Dev Setup

See [docs/SETUP.md](docs/SETUP.md).

Quick start:
```bash
cd apps/web && npm install && npm run dev
```

---

## Asking for Help

Open a GitHub Issue with:
- What you were trying to do
- What you expected
- What happened instead (error message, screenshot)
- Branch/commit you're on

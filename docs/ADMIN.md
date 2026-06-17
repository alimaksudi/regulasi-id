# Admin Panel

Located at `/admin` — not internationalized, Indonesian only. Access requires Supabase auth + email in `ADMIN_EMAILS` env var.

---

## Authentication

```typescript
// Every admin route must call this first
import { requireAdmin } from "@/lib/admin-auth"

export default async function AdminPage() {
  await requireAdmin()  // redirects to /admin/login if unauthorized
  // ...
}
```

`requireAdmin()` checks:
1. Supabase session exists (`getUser()` — not `getSession()`)
2. User email is in `ADMIN_EMAILS` env var (comma-separated)

To add an admin: add their Supabase-registered email to `ADMIN_EMAILS` in Vercel.

---

## Pages

| Route | Purpose |
|-------|---------|
| `/admin/login` | Supabase Auth email/password login |
| `/admin` | Dashboard — pending suggestions count, crawl stats, recent revisions |
| `/admin/suggestions` | Suggestion queue (list + review) |
| `/admin/suggestions/[id]` | Individual suggestion review page |
| `/admin/regulations` | Browse/search all works in DB |
| `/admin/regulations/[slug]` | Edit work metadata (status, subject_tags) |
| `/admin/crawl` | Crawl job queue — status, retry failed jobs |

---

## Suggestion Queue Flow

### 1. Submission (public)

User submits from the regulation detail page:

```
POST /api/suggestions
{
  work_id, node_id, current_content, suggested_content, reason, email
}
→ suggestions.status = 'pending'
```

### 2. Gemini Verification (automated, optional)

Admin triggers "Run AI Verification" from `/admin/suggestions` or it runs on a schedule:

```python
# scripts/agent/verify_suggestion.py
result = verify_suggestion(suggestion_id)
# → sets status = 'verified', agent_decision, agent_confidence, agent_modified_content
```

Gemini is **advisory only** — it cannot approve. It:
- Checks if the suggested text matches the source PDF
- Returns: `{ decision: 'approve' | 'reject' | 'uncertain', confidence: 0.0–1.0, notes: "..." }`
- Optionally proposes a third corrected version (`agent_modified_content`)

### 3. Admin Review

Admin sees on `/admin/suggestions/[id]`:

```
Current text:    [node content from DB]
User suggestion: [suggested_content]
AI suggestion:   [agent_modified_content, if present]
AI verdict:      Approve (confidence: 0.92) | Reject | Uncertain

Actions:
  [Apply User's Version]
  [Apply AI's Version]     ← only shown if agent_modified_content present
  [Reject]
  [Edit & Apply]           ← free-form text field
```

### 4. Applying

All approval paths call `apply_revision()`:

```typescript
// apps/web/src/app/api/admin/suggestions/[id]/apply/route.ts
await supabase.rpc("apply_revision", {
  p_node_id: suggestion.node_id,
  p_new_content: finalContent,
  p_reason: `Suggestion #${id} approved by admin`,
  p_actor: `admin:${adminEmail}`,
  p_suggestion_id: id,
})
```

This atomically:
1. Inserts row into `revisions` (old content + new content + actor)
2. Updates `document_nodes.content_text` (FTS TSVECTOR auto-regenerates)
3. Sets `suggestions.status = 'approved'`

### 5. Rejection

```typescript
await supabase
  .from("suggestions")
  .update({ status: "rejected", admin_note: "reason", updated_at: new Date() })
  .eq("id", id)
```

No revision is created on rejection.

---

## Crawl Management

`/admin/crawl` shows:

| Column | Source |
|--------|--------|
| Sector | `crawl_jobs.sector_code` |
| Type | `crawl_jobs.regulation_type` |
| Pending | COUNT where status='pending' |
| Processing | COUNT where status='crawling' |
| Loaded | COUNT where status='loaded' |
| Failed | COUNT where status='failed' |

**Retry Failed Jobs** button:
```sql
UPDATE crawl_jobs SET status = 'pending', error_message = NULL WHERE status = 'failed';
```

**Trigger Discovery** button: calls `POST /api/admin/crawl/discover` which runs the discover script for a given sector.

---

## Editing Work Metadata

From `/admin/regulations/[slug]`, admin can update:

- `status` — berlaku | diubah | dicabut | tidak_berlaku
- `subject_tags` — array of topic tags
- `date_enacted`
- `content_verified` — checkbox to mark as human-verified

These are direct `UPDATE works` calls via service role. No revision log (metadata, not content).

---

## API Routes (Admin)

All under `/api/admin/` — require `requireAdmin()` at the handler level.

| Method | Route | Action |
|--------|-------|--------|
| GET | `/api/admin/suggestions` | List pending suggestions |
| POST | `/api/admin/suggestions/[id]/apply` | Apply revision |
| POST | `/api/admin/suggestions/[id]/reject` | Reject suggestion |
| POST | `/api/admin/suggestions/[id]/verify` | Trigger Gemini verification |
| GET | `/api/admin/crawl/stats` | Crawl job counts by status |
| POST | `/api/admin/crawl/retry-failed` | Reset failed jobs to pending |
| POST | `/api/admin/crawl/discover` | Trigger discovery for a sector |
| PATCH | `/api/admin/regulations/[slug]` | Update work metadata |

---

## Supabase Client in Admin Routes

Admin API routes use the **service role** client to bypass RLS:

```typescript
// src/lib/supabase/service.ts
import { createClient } from "@supabase/supabase-js"

export const supabaseService = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_ROLE_KEY!
)
```

Never import `supabaseService` in Server Components or client code — admin API routes only.

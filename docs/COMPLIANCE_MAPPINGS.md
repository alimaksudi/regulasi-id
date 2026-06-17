# Compliance Mappings

The `compliance_mappings` table is the key differentiator of regulasi-id. It answers: **"Which OJK regulations apply to my business?"**

This is a **curated** table — it is not auto-generated. A human (legal analyst or admin) maintains it.

---

## Data Model

```sql
compliance_mappings
├── sector_id      → which OJK sector (perbankan, fintech, etc.)
├── business_type  → specific business type within sector (nullable = sector-wide)
├── work_id        → the regulation that applies
├── priority       → required | recommended | conditional
└── notes          → why this applies / conditions
```

### Priority levels

| Priority | Meaning |
|----------|---------|
| `required` | Mandatory. Business cannot operate without complying. |
| `recommended` | Best practice. OJK expects compliance but enforcement varies. |
| `conditional` | Applies only under specific conditions (see `notes`). |

### Business types per sector

Define business types in code as constants, not free-form strings:

```typescript
// src/lib/compliance.ts
export const BUSINESS_TYPES = {
  fintech: [
    "p2p-lending",          // LPBBTI (POJK 10/2022)
    "payment-gateway",
    "e-money",
    "digital-bank",
    "equity-crowdfunding",
    "crypto-exchange",
    "robo-advisor",
  ],
  perbankan: [
    "bank-umum",
    "bpr",
    "bank-syariah",
  ],
  iknb: [
    "multifinance",
    "modal-ventura",
    "pegadaian",
  ],
  perasuransian: [
    "asuransi-jiwa",
    "asuransi-umum",
    "broker-asuransi",
    "reasuransi",
  ],
  "pasar-modal": [
    "manajer-investasi",
    "broker-dealer",
    "kustodian",
  ],
  "dana-pensiun": [
    "dppk",  // Dana Pensiun Pemberi Kerja
    "dplk",  // Dana Pensiun Lembaga Keuangan
  ],
}
```

---

## How to Add a Mapping

### Step 1 — Identify the regulation

Find the `work_id` for the regulation:

```sql
SELECT id, title_id, number, year FROM works
WHERE regulation_type_id = (SELECT id FROM regulation_types WHERE code = 'POJK')
  AND number = '10' AND year = 2022;
-- → id: 42
```

### Step 2 — Insert the mapping

```sql
INSERT INTO compliance_mappings (sector_id, business_type, work_id, priority, notes)
VALUES (
  (SELECT id FROM sectors WHERE code = 'fintech'),
  'p2p-lending',
  42,
  'required',
  'Primary licensing regulation for P2P lending (LPBBTI) operators'
);
```

Or via admin UI: `/admin/compliance` → "Add Mapping".

### Step 3 — Add SEOJK circulars that implement the POJK

SEOJKs are implementing circulars — they're often as important as the POJK itself. Add them separately:

```sql
INSERT INTO compliance_mappings (sector_id, business_type, work_id, priority, notes)
VALUES (
  (SELECT id FROM sectors WHERE code = 'fintech'),
  'p2p-lending',
  (SELECT id FROM works WHERE number = '19' AND year = 2023
     AND regulation_type_id = (SELECT id FROM regulation_types WHERE code = 'SEOJK')),
  'required',
  'SEOJK implementing POJK 10/2022 — covers reporting requirements'
);
```

---

## Ownership

| Who | Responsibility |
|-----|---------------|
| Legal analyst | Reviews each regulation, determines which business types it applies to |
| Admin | Enters mappings into DB via admin UI or SQL |
| Developer | Maintains `BUSINESS_TYPES` constant in code, keeps it in sync with DB values |

**Do not auto-populate from scraper.** The scraper loads regulation content — which business types a regulation applies to requires legal judgment.

---

## Initial Seeding

Priority order for first launch:

1. **Fintech sector** — highest demand, fastest-growing. Start with:
   - POJK 10/2022 → p2p-lending (required)
   - POJK 77/2016 (if still berlaku) or its replacement → p2p-lending (required)
   - All SEOJK implementing fintech POJKs → p2p-lending (required)
   - POJK on e-money → payment-gateway, e-money (required)

2. **Perbankan sector** — largest by regulation count, but users are larger institutions with legal teams. Seed `bank-umum` first.

3. **IKNB sector** — multifinance, modal ventura.

---

## Maintenance

When a new POJK is published:
1. Scraper picks it up automatically (new regulation in DB)
2. Admin reviews it and adds `compliance_mappings` rows for affected business types
3. If it amends an existing POJK, update `work_relationships` and check whether existing compliance mappings should update `priority` or `notes`

When a POJK is revoked:
1. Scraper or admin updates `works.status = 'dicabut'`
2. The `get_compliance_checklist` MCP tool filters out `dicabut` regulations automatically — no manual cleanup needed

---

## Querying

The `get_compliance_checklist` MCP tool and `/api/v1/compliance` endpoint both use:

```sql
SELECT
  w.frbr_uri, w.title_id, rt.code AS regulation_type,
  w.number, w.year, w.status,
  cm.priority, cm.notes
FROM compliance_mappings cm
JOIN works w ON cm.work_id = w.id
JOIN regulation_types rt ON w.regulation_type_id = rt.id
JOIN sectors s ON cm.sector_id = s.id
WHERE s.code = $1
  AND (cm.business_type = $2 OR cm.business_type IS NULL)
  AND w.status = 'berlaku'
ORDER BY
  CASE cm.priority WHEN 'required' THEN 1 WHEN 'recommended' THEN 2 ELSE 3 END,
  rt.hierarchy_level,
  w.year DESC;
```

`business_type IS NULL` means sector-wide — applies to all business types in that sector.

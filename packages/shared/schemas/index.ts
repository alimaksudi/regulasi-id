import { z } from "zod"

// Shared between the Hono API (validation) and the web client (types).
// Single source of truth for request shapes.

export const SECTOR_CODES = [
  "perbankan",
  "pasar-modal",
  "iknb",
  "fintech",
  "dana-pensiun",
  "perasuransian",
] as const

export const TYPE_CODES = ["UU", "PP", "PERPRES", "POJK", "SEOJK", "KEOJK"] as const

export const STATUS_CODES = ["berlaku", "diubah", "dicabut", "tidak_berlaku"] as const

export const sectorSchema = z.enum(SECTOR_CODES)
export const typeSchema = z.enum(TYPE_CODES)
export const statusSchema = z.enum(STATUS_CODES)

// Comma-separated list of enum values, e.g. "POJK,SEOJK" -> ["POJK", "SEOJK"].
function csvEnum<T extends readonly [string, ...string[]]>(values: T) {
  const allowed = new Set<string>(values)
  return z.string().transform((raw, ctx) => {
    const parts = raw
      .split(",")
      .map((p) => p.trim())
      .filter(Boolean)
    for (const p of parts) {
      if (!allowed.has(p)) {
        ctx.addIssue({ code: "custom", message: `Nilai tidak valid: ${p}` })
        return z.NEVER
      }
    }
    return parts as T[number][]
  })
}

const YEAR = z.number().int().min(1945).max(2099)
const YEAR_COERCED = z.coerce.number().int().min(1945).max(2099)

// POST /api/v1/search (JSON body)
export const SearchSchema = z
  .object({
    q: z.string().min(1, "Wajib diisi").max(500, "Maksimal 500 karakter"),
    sector: sectorSchema.optional(),
    type: csvEnum(TYPE_CODES).optional(),
    year_from: YEAR.optional(),
    year_to: YEAR.optional(),
    status: csvEnum(STATUS_CODES).optional(),
    limit: z.number().int().min(1).max(50).default(10),
  })
  .refine(
    (d) => d.year_to == null || d.year_from == null || d.year_to >= d.year_from,
    { message: "year_to harus lebih besar atau sama dengan year_from", path: ["year_to"] }
  )

// GET /api/v1/regulations (query string)
export const ListRegulationsSchema = z.object({
  sector: sectorSchema.optional(),
  type: csvEnum(TYPE_CODES).optional(),
  year: YEAR_COERCED.optional(),
  year_from: YEAR_COERCED.optional(),
  year_to: YEAR_COERCED.optional(),
  status: csvEnum(STATUS_CODES).optional(),
  cursor: z.string().optional(),
  per_page: z.coerce.number().int().min(1).max(100).default(20),
})

// GET /api/v1/compliance (query string)
export const ComplianceSchema = z.object({
  sector: sectorSchema,
  business_type: z.string().min(1).max(100).optional(),
})

// POST /api/suggestions (JSON body)
export const SuggestionSchema = z.object({
  work_id: z.number().int().positive(),
  node_id: z.number().int().positive(),
  current_content: z.string().min(1).max(20000),
  suggested_content: z.string().min(1).max(20000),
  reason: z.string().max(2000).optional(),
  email: z.email().optional(),
})

// Admin: create/update a compliance mapping (priority per DATABASE.md).
export const ComplianceMappingSchema = z.object({
  sector: sectorSchema,
  business_type: z.string().min(1).max(100).nullable().optional(),
  work_id: z.number().int().positive(),
  priority: z.enum(["required", "recommended", "conditional"]),
  notes: z.string().max(2000).optional(),
})

export type SearchInput = z.infer<typeof SearchSchema>
export type ListRegulationsInput = z.infer<typeof ListRegulationsSchema>
export type ComplianceInput = z.infer<typeof ComplianceSchema>
export type SuggestionInput = z.infer<typeof SuggestionSchema>
export type ComplianceMappingInput = z.infer<typeof ComplianceMappingSchema>

import { describe, it, expect } from "vitest"
import {
  SearchSchema,
  ListRegulationsSchema,
  SuggestionSchema,
  ComplianceMappingSchema,
} from "@regulasi-id/shared/schemas"

describe("SearchSchema", () => {
  it("accepts a minimal valid query and applies the default limit", () => {
    const parsed = SearchSchema.parse({ q: "modal minimum" })
    expect(parsed.limit).toBe(10)
  })

  it("rejects empty query and over-long query", () => {
    expect(SearchSchema.safeParse({ q: "" }).success).toBe(false)
    expect(SearchSchema.safeParse({ q: "x".repeat(501) }).success).toBe(false)
  })

  it("parses a comma-separated type list into an array", () => {
    const parsed = SearchSchema.parse({ q: "p2p", type: "POJK,SEOJK" })
    expect(parsed.type).toEqual(["POJK", "SEOJK"])
  })

  it("rejects an invalid type in the list", () => {
    expect(SearchSchema.safeParse({ q: "p2p", type: "POJK,NOPE" }).success).toBe(false)
  })

  it("rejects year_to before year_from", () => {
    expect(
      SearchSchema.safeParse({ q: "x", year_from: 2022, year_to: 2020 }).success
    ).toBe(false)
  })

  it("clamps limit range", () => {
    expect(SearchSchema.safeParse({ q: "x", limit: 51 }).success).toBe(false)
    expect(SearchSchema.safeParse({ q: "x", limit: 0 }).success).toBe(false)
  })
})

describe("ListRegulationsSchema", () => {
  it("coerces string query params to numbers with a default per_page", () => {
    const parsed = ListRegulationsSchema.parse({ year: "2022" })
    expect(parsed.year).toBe(2022)
    expect(parsed.per_page).toBe(20)
  })

  it("rejects per_page above 100", () => {
    expect(ListRegulationsSchema.safeParse({ per_page: "101" }).success).toBe(false)
  })
})

describe("SuggestionSchema", () => {
  it("accepts a valid suggestion", () => {
    const ok = SuggestionSchema.safeParse({
      work_id: 1,
      node_id: 2,
      current_content: "a",
      suggested_content: "b",
      email: "user@example.com",
    })
    expect(ok.success).toBe(true)
  })

  it("rejects a bad email and non-positive ids", () => {
    expect(
      SuggestionSchema.safeParse({
        work_id: 0,
        node_id: 2,
        current_content: "a",
        suggested_content: "b",
      }).success
    ).toBe(false)
    expect(
      SuggestionSchema.safeParse({
        work_id: 1,
        node_id: 2,
        current_content: "a",
        suggested_content: "b",
        email: "nope",
      }).success
    ).toBe(false)
  })
})

describe("ComplianceMappingSchema", () => {
  it("accepts a valid mapping", () => {
    const ok = ComplianceMappingSchema.safeParse({
      sector: "fintech",
      work_id: 10,
      priority: "required",
    })
    expect(ok.success).toBe(true)
  })

  it("rejects an unknown priority", () => {
    expect(
      ComplianceMappingSchema.safeParse({
        sector: "fintech",
        work_id: 10,
        priority: "informational",
      }).success
    ).toBe(false)
  })
})

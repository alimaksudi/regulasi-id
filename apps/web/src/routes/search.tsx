import { createFileRoute } from "@tanstack/react-router"
import { useQuery } from "@tanstack/react-query"
import { z } from "zod"
import { sectorSchema } from "@regulasi-id/shared/schemas"
import { apiClient } from "~/lib/api"
import { SearchBar } from "~/components/SearchBar"
import { RegulationCard } from "~/components/RegulationCard"

const searchSchema = z.object({
  q: z.string().catch(""),
  sector: sectorSchema.optional(),
})

export const Route = createFileRoute("/search")({
  validateSearch: searchSchema,
  component: SearchPage,
})

function SearchPage() {
  const { q, sector } = Route.useSearch()

  const { data, isLoading, isError } = useQuery({
    queryKey: ["search", q, sector],
    queryFn: () => apiClient.search({ q, sector }),
    enabled: q.trim().length > 0,
  })

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <SearchBar initialQuery={q} />

      <div className="mt-8">
        {!q.trim() && <p className="text-neutral-500">Masukkan kata kunci pencarian.</p>}
        {isLoading && <p className="text-neutral-500">Mencari...</p>}
        {isError && <p className="text-red-600">Pencarian gagal. Coba lagi.</p>}
        {data && (
          <>
            <p className="text-sm text-neutral-500">
              {data.total} hasil untuk "{data.query}"
            </p>
            <div className="mt-4 space-y-3">
              {data.results.map((r) => (
                <RegulationCard key={`${r.work_id}-${r.node_id ?? 0}`} result={r} />
              ))}
            </div>
          </>
        )}
      </div>
    </main>
  )
}

import { createFileRoute, Link } from "@tanstack/react-router"
import { apiClient } from "~/lib/api"

export const Route = createFileRoute("/sektor/$sector")({
  loader: ({ params }) => apiClient.listRegulations({ sector: params.sector }),
  component: SectorPage,
})

function frbrToSlug(item: { type: string; number: string; year: number }): string {
  return `${item.type}-${item.number}-${item.year}`.toLowerCase()
}

function SectorPage() {
  const { sector } = Route.useParams()
  const data = Route.useLoaderData()

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <h1 className="text-2xl font-bold capitalize">{sector.replace("-", " ")}</h1>
      <p className="mt-1 text-sm text-neutral-500">{data.total} peraturan</p>

      <div className="mt-6 space-y-3">
        {data.regulations.map((r) => (
          <Link
            key={r.frbr_uri}
            to="/regulasi/$type/$slug"
            params={{ type: r.type.toLowerCase(), slug: frbrToSlug(r) }}
            className="block rounded-lg border border-neutral-200 p-4 hover:border-neutral-400"
          >
            <div className="text-xs font-medium uppercase text-neutral-500">
              {r.type} {r.number}/{r.year}
            </div>
            <div className="mt-1 font-medium">{r.title}</div>
          </Link>
        ))}
      </div>
    </main>
  )
}

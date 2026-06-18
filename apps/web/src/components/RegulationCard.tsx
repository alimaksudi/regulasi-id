import { Link } from "@tanstack/react-router"
import type { SearchResult } from "~/lib/api"

function typeFromFrbr(frbr: string): string {
  const parts = frbr.split("/")
  return parts[4] ?? "uu"
}

export function RegulationCard({ result }: { result: SearchResult }) {
  const type = typeFromFrbr(result.frbr_uri)
  const slug = `${type}-${result.number}-${result.year}`.toLowerCase()
  const pasal =
    result.node_type === "pasal" && result.node_number
      ? `Pasal ${result.node_number}`
      : null

  return (
    <Link
      to="/regulasi/$type/$slug"
      params={{ type, slug }}
      className="block rounded-lg border border-neutral-200 p-4 hover:border-neutral-400"
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-medium uppercase text-neutral-500">
          {type} {result.number}/{result.year}
        </span>
        <span className="rounded bg-neutral-100 px-2 py-0.5 text-xs text-neutral-600">
          {result.status}
        </span>
      </div>
      <h3 className="mt-1 font-medium">{result.title_id}</h3>
      {pasal && <div className="mt-1 text-sm text-neutral-500">{pasal}</div>}
      {result.snippet && (
        <p
          className="mt-2 text-sm text-neutral-600"
          // snippet contains server-generated <mark> highlights
          dangerouslySetInnerHTML={{ __html: result.snippet }}
        />
      )}
    </Link>
  )
}

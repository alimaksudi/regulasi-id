import { createFileRoute } from "@tanstack/react-router"
import { apiClient } from "~/lib/api"
import { slugToFrbr } from "~/lib/utils"

export const Route = createFileRoute("/regulasi/$type/$slug")({
  loader: ({ params }) => apiClient.getRegulation(slugToFrbr(params.slug)),
  component: RegulationPage,
})

function RegulationPage() {
  const { work, nodes } = Route.useLoaderData()

  return (
    <main className="mx-auto max-w-3xl px-4 py-10">
      <div className="text-xs font-medium uppercase text-neutral-500">
        {work.type} {work.number}/{work.year} · {work.status}
      </div>
      <h1 className="mt-1 text-2xl font-bold">{work.title}</h1>

      {work.related.length > 0 && (
        <section className="mt-4 rounded-lg border border-neutral-200 p-3 text-sm">
          <div className="font-medium">Hubungan</div>
          <ul className="mt-1 space-y-1 text-neutral-600">
            {work.related.map((r, i) => (
              <li key={i}>
                {r.relationship}: {r.title}
              </li>
            ))}
          </ul>
        </section>
      )}

      <article className="mt-8 space-y-4">
        {nodes.map((n) => (
          <div key={n.id}>
            {n.heading && (
              <div className="font-semibold">
                {n.node_type.toUpperCase()} {n.number} {n.heading}
              </div>
            )}
            {n.node_type === "pasal" && (
              <div className="font-medium">Pasal {n.number}</div>
            )}
            {n.content_text && (
              <p className="whitespace-pre-line text-neutral-800">{n.content_text}</p>
            )}
          </div>
        ))}
      </article>
    </main>
  )
}

import { createFileRoute, Link } from "@tanstack/react-router"
import { apiClient } from "~/lib/api"
import { SearchBar } from "~/components/SearchBar"

export const Route = createFileRoute("/")({
  loader: () => apiClient.getSectors(),
  component: LandingPage,
})

function LandingPage() {
  const { sectors } = Route.useLoaderData()

  return (
    <main className="mx-auto max-w-5xl px-4 py-16">
      <h1 className="text-4xl font-bold tracking-tight">
        Regulasi OJK, terbuka untuk semua
      </h1>
      <p className="mt-4 max-w-2xl text-neutral-600">
        Cari dan rujuk peraturan OJK dengan teks pasal yang akurat dan sumber resmi.
      </p>

      <div className="mt-8 max-w-2xl">
        <SearchBar />
      </div>

      <section className="mt-16">
        <h2 className="text-sm font-medium uppercase text-neutral-500">Jelajahi sektor</h2>
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
          {sectors.map((s) => (
            <Link
              key={s.code}
              to="/sektor/$sector"
              params={{ sector: s.code }}
              className="rounded-lg border border-neutral-200 p-4 hover:border-neutral-400"
            >
              <div className="font-medium">{s.name_id}</div>
              <div className="text-sm text-neutral-500">{s.regulation_count} peraturan</div>
            </Link>
          ))}
        </div>
      </section>
    </main>
  )
}

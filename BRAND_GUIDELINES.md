# Brand Guidelines

**Read this before any frontend work.** All UI is built on shadcn/ui + Lucide + Tailwind v4.

---

## Identity

**regulasi.id** — grounded, authoritative, accessible. Serves compliance officers, legal teams, and founders who need to trust what they're reading. The design reflects that: clean, structured, no decorative noise.

---

## Color System

All colors are CSS custom properties in `apps/web/app/styles/globals.css`. Never hardcode hex values — always use tokens.

### Core palette

| Token | Value | Usage |
|-------|-------|-------|
| `--primary` | `#1B4F72` (Deep OJK Blue) | Buttons, links, active states, focus rings |
| `--background` | `#F5F5F0` (Warm Stone) | Page background — never pure white |
| `--card` | `#FFFFFF` | Cards and panels — provides lift over background |
| `--muted` | `#EFEFEA` | Subtle section backgrounds, disabled states |
| `--border` | `#E2DDD8` | All borders and dividers |
| `--foreground` | `#1C1917` (Warm Graphite) | Body text |
| `--muted-foreground` | `#78716C` | Secondary text, metadata, labels |

### Status colors

| Token | Value | Status |
|-------|-------|--------|
| `--status-berlaku` | `#15803D` (Forest Green) | Berlaku (In force) |
| `--status-diubah` | `#B45309` (Amber) | Diubah (Amended) |
| `--status-dicabut` | `#B91C1C` (Red) | Dicabut (Revoked) |
| `--status-tidak-berlaku` | `#6B7280` (Gray) | Tidak Berlaku |

Never use status colors for anything other than regulation status. Never use them decoratively.

### Neutrals

Warm gray only. Never `gray-*`, `slate-*`, `zinc-*`, or `neutral-*` from Tailwind — they have cool undertones that clash with the warm stone background.

```css
/* Correct: warm neutrals */
text-stone-900, text-stone-600, text-stone-400
bg-stone-100, border-stone-200

/* Wrong: cool neutrals */
text-gray-900, text-slate-600, text-zinc-400
```

---

## Typography

Three fonts, each with one job. Configured in TanStack Start root layout.

| Font | CSS Variable | Weight | Usage |
|------|-------------|--------|-------|
| **Instrument Serif** | `--font-heading` | 400 only | Page titles, regulation titles (h1–h3) |
| **Instrument Sans** | `--font-sans` | 400, 500, 600 | Body, UI, labels, navigation |
| **JetBrains Mono** | `--font-mono` | 400 | Article numbers, FRBR URIs, `code` |

**Instrument Serif has no bold.** Font size is the only hierarchy tool for headings.

```css
/* Heading hierarchy via size, never weight */
h1 { font-family: var(--font-heading); font-size: 2.25rem; font-weight: 400; line-height: 1.2; }
h2 { font-family: var(--font-heading); font-size: 1.5rem;  font-weight: 400; line-height: 1.3; }
h3 { font-family: var(--font-heading); font-size: 1.125rem; font-weight: 400; }
```

---

## shadcn/ui Components

shadcn/ui is the component foundation. Initialize with the Vite preset:

```bash
npx shadcn@latest init
# Choose: Vite, Tailwind v4, Stone base color, CSS variables: yes
```

Components in `app/components/ui/`. Never modify shadcn primitives directly — extend by composition.

### Button

```tsx
import { Button } from "~/components/ui/button"

// Primary — call to action
<Button>Cari Peraturan</Button>

// Secondary — alternative action
<Button variant="outline">Lihat Semua</Button>

// Ghost — low-emphasis (table actions, nav links)
<Button variant="ghost" size="sm">Filter</Button>

// Destructive — delete, reject
<Button variant="destructive">Tolak</Button>
```

### Card

```tsx
import { Card, CardHeader, CardTitle, CardContent } from "~/components/ui/card"

<Card>
  <CardHeader>
    <CardTitle>POJK No. 10 Tahun 2022</CardTitle>
  </CardHeader>
  <CardContent>
    {/* Regulation summary */}
  </CardContent>
</Card>
```

No shadows on cards — border only. `shadow-sm` only on floating elements (popovers, dropdowns).

### Input / Search

```tsx
import { Input } from "~/components/ui/input"

<Input
  placeholder="Cari peraturan OJK..."
  className="h-12 text-base"
/>
```

### Badge

```tsx
import { Badge } from "~/components/ui/badge"

// Regulation type chip
<Badge variant="outline" className="font-mono text-xs">POJK</Badge>

// Status badge — use semantic colors
<Badge className="bg-green-50 text-[--status-berlaku] border-green-200 hover:bg-green-50">
  Berlaku
</Badge>
<Badge className="bg-red-50 text-[--status-dicabut] border-red-200 hover:bg-red-50">
  Dicabut
</Badge>
```

### Dialog (Correction form)

```tsx
import { Dialog, DialogTrigger, DialogContent, DialogHeader, DialogTitle } from "~/components/ui/dialog"

<Dialog>
  <DialogTrigger asChild>
    <Button variant="ghost" size="sm">
      <Flag size={14} className="mr-1.5" />
      Laporkan Kesalahan
    </Button>
  </DialogTrigger>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Laporkan Kesalahan Teks</DialogTitle>
    </DialogHeader>
    {/* Correction form */}
  </DialogContent>
</Dialog>
```

### Table (Admin)

```tsx
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "~/components/ui/table"

<Table>
  <TableHeader>
    <TableRow>
      <TableHead>Regulasi</TableHead>
      <TableHead>Status</TableHead>
      <TableHead>Tahun</TableHead>
    </TableRow>
  </TableHeader>
  <TableBody>
    {regulations.map(r => (
      <TableRow key={r.id}>
        <TableCell className="font-medium">{r.title_id}</TableCell>
        <TableCell><StatusBadge status={r.status} /></TableCell>
        <TableCell className="font-mono">{r.year}</TableCell>
      </TableRow>
    ))}
  </TableBody>
</Table>
```

### Select / Filter

```tsx
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "~/components/ui/select"

<Select onValueChange={(v) => setFilter({ sector: v })}>
  <SelectTrigger className="w-48">
    <SelectValue placeholder="Semua sektor" />
  </SelectTrigger>
  <SelectContent>
    <SelectItem value="fintech">Fintech</SelectItem>
    <SelectItem value="perbankan">Perbankan</SelectItem>
  </SelectContent>
</Select>
```

---

## Lucide Icons

`lucide-react` only. No other icon library.

```tsx
import { Search, FileText, ChevronRight, ExternalLink, Flag, X, Check } from "lucide-react"

// Inline (with text)
<Search size={16} className="mr-1.5" />

// Standalone (icon-only button)
<Button variant="ghost" size="icon">
  <X size={20} />
</Button>

// Hero / empty state
<FileText size={48} className="text-muted-foreground" />
```

Common icons for this domain:
- `Search` — search bar
- `FileText` — regulation document
- `BookOpen` — pasal/content reader
- `Scale` — legal/law context
- `Building2` — institution/OJK
- `ChevronRight` — navigation, breadcrumb
- `ExternalLink` — links to source (PDF, JDIH)
- `Flag` — report correction
- `CheckCircle2` — berlaku status
- `XCircle` — dicabut status
- `AlertCircle` — diubah status
- `Copy` — copy MCP URL / article reference

---

## Layout & Spacing

- **Max width:** `max-w-7xl mx-auto` for main content (1280px)
- **Page padding:** `px-4 sm:px-6 lg:px-8`
- **Section spacing:** `py-12 md:py-16`
- **Card padding:** `p-6` (large), `p-4` (compact)
- **Border radius:** `rounded-lg` default, `rounded-xl` for hero cards, `rounded-full` for status badges
- **Grid:** 12-column Tailwind grid. Sidebar layouts: `lg:grid-cols-[280px_1fr]`

---

## Form Patterns

React Hook Form + Zod on every form. Never uncontrolled forms.

```tsx
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { Form, FormField, FormItem, FormLabel, FormControl, FormMessage } from "~/components/ui/form"
import { z } from "zod"

const SuggestionSchema = z.object({
  suggested_content: z.string().min(10, "Minimal 10 karakter"),
  reason: z.string().min(10, "Minimal 10 karakter"),
  email: z.string().email("Email tidak valid").optional().or(z.literal("")),
})

function CorrectionForm() {
  const form = useForm({ resolver: zodResolver(SuggestionSchema) })

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        <FormField
          control={form.control}
          name="suggested_content"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Teks yang benar</FormLabel>
              <FormControl>
                <Textarea {...field} rows={6} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
        <Button type="submit" disabled={form.formState.isSubmitting}>
          {form.formState.isSubmitting ? "Mengirim..." : "Kirim"}
        </Button>
      </form>
    </Form>
  )
}
```

---

## Content Rules

- **UI language:** Indonesian primary. English only for technical labels (`API`, `MCP`, `slug`).
- **Regulation titles:** Always display full Indonesian title. Abbreviations (`POJK`, `SEOJK`) only in badges/chips.
- **Numbers:** Indonesian locale — `1.234.567` (period as thousands separator).
- **Dates:** `28 Maret 2022` format — never ISO or English month names in UI.
- **Pasal references:** `Pasal 1 ayat (2)` — never `Article 1(2)`.
- **Disclaimer:** Every page with regulation content must include: `Informasi ini bukan nasihat hukum. Selalu verifikasi dengan sumber resmi OJK.`

---

## Do / Don't

| Do | Don't |
|----|-------|
| `bg-[--background]` (#F5F5F0) for page background | Pure white page background |
| `border border-[--border]` on cards | Shadows on cards |
| Instrument Serif weight 400 for headings | Bold/semibold on serif headings |
| `font-mono` for article numbers and FRBR URIs | Sans-serif for article numbers |
| Warm stone neutrals (`stone-*`) | Cool neutrals (`gray-*`, `slate-*`, `zinc-*`) |
| `lucide-react` icons only | Heroicons, Phosphor, or other icon libraries |
| shadcn/ui components as the base | Building UI primitives from scratch |
| `size={16/20/24}` on Lucide icons | Mixing icon sizes randomly |
| One accent (Deep OJK Blue `#1B4F72`) | Additional accent colors |
| Indonesian UI strings | Mixing Indonesian and English within one string |
| `<StatusBadge>` component for regulation status | Inline status color styles |

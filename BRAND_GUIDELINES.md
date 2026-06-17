# Brand Guidelines

**Read this before any frontend work.**

---

## Identity

**regulasi.id** — grounded, authoritative, accessible. The platform serves compliance officers, legal teams, and founders who need to trust what they're reading. The design reflects that: clean, structured, no decorative noise.

---

## Color System

All colors are CSS custom properties defined in `apps/web/src/app/globals.css`. Never hardcode hex values.

### Primary palette

| Token | Value | Usage |
|-------|-------|-------|
| `bg-primary` | `#1B4F72` (Deep OJK Blue) | Buttons, links, active states, focus rings |
| `bg-background` | `#F5F5F0` (Warm Stone) | Page background — never pure white |
| `bg-card` | `#FFFFFF` | Cards, panels — provides lift over background |
| `bg-muted` | `#EFEFEA` | Subtle section backgrounds, disabled states |

### Status colors

| Token | Value | Status |
|-------|-------|--------|
| `text-status-berlaku` | `#1A6B3C` (Forest Green) | Berlaku (In force) |
| `text-status-diubah` | `#B45309` (Amber) | Diubah (Amended) |
| `text-status-dicabut` | `#B91C1C` (Red) | Dicabut (Revoked) |
| `text-status-tidak-berlaku` | `#6B7280` (Gray) | Tidak Berlaku (Expired) |

### Neutrals

Warm gray family only — never cool gray, slate, or zinc.

| Token | Usage |
|-------|-------|
| `text-foreground` | Body text (warm graphite) |
| `text-muted-foreground` | Secondary text, metadata |
| `border` | Borders and dividers |

### Accent — use sparingly

One accent color: `#2B6150` (Verdigris) for hover states on the primary blue. Do not introduce additional accent colors.

---

## Typography

Three fonts, each with a single purpose:

| Font | Variable | Weight | Usage |
|------|----------|--------|-------|
| **Instrument Serif** | `font-heading` | 400 only | Headings (h1–h3) |
| **Instrument Sans** | `font-sans` | 400, 500, 600 | Body, UI, labels |
| **JetBrains Mono** | `font-mono` | 400 | Article numbers, code, FRBR URIs |

**Instrument Serif has no bold.** Use font size for heading hierarchy, never font-weight.

```css
/* Correct heading hierarchy */
h1 { font-family: var(--font-heading); font-size: 2.25rem; font-weight: 400; }
h2 { font-family: var(--font-heading); font-size: 1.5rem;  font-weight: 400; }
h3 { font-family: var(--font-heading); font-size: 1.25rem; font-weight: 400; }
```

---

## Layout & Spacing

- **Container max-width:** `1200px` centered
- **Page padding:** `px-4 md:px-6 lg:px-8`
- **Section spacing:** `py-12 md:py-16`
- **Card padding:** `p-6`
- **Border radius:** `rounded-lg` default, `rounded-xl` for hero cards
- **Grid:** 12-column. Sidebar layouts use `lg:grid-cols-[280px_1fr]`

---

## Components

### Cards

```html
<div class="bg-card rounded-lg border border-border p-6">
  <!-- content -->
</div>
```

No shadows on cards — use border. Only `shadow-sm` on floating elements (popovers, dropdowns).

### Buttons

```html
<!-- Primary -->
<button class="bg-primary text-primary-foreground rounded-lg px-4 py-2 hover:bg-primary/90">
  Cari Peraturan
</button>

<!-- Secondary -->
<button class="border border-border bg-background rounded-lg px-4 py-2 hover:bg-muted">
  Lihat Semua
</button>

<!-- Ghost (nav links, table actions) -->
<button class="text-muted-foreground hover:text-foreground hover:bg-muted rounded-md px-3 py-1.5">
  Filter
</button>
```

### Status badges

```html
<span class="text-xs font-medium px-2 py-0.5 rounded-full bg-green-50 text-status-berlaku border border-green-200">
  Berlaku
</span>
```

### Regulation type chips

```html
<span class="font-mono text-xs bg-muted px-1.5 py-0.5 rounded text-muted-foreground">
  POJK
</span>
```

### Search input

```html
<input class="w-full border border-border rounded-lg px-4 py-3 bg-background focus:outline-none focus:ring-2 focus:ring-primary/50 font-sans" />
```

---

## Iconography

Use [Lucide React](https://lucide.dev) exclusively. Size: `16` (inline), `20` (standalone), `24` (hero/empty state).

```tsx
import { Search, FileText, ChevronRight } from "lucide-react"
```

---

## Content Rules

- **UI language:** Indonesian primary. English for technical labels only (`API`, `slug`, etc.)
- **Regulation titles:** Always display in full Indonesian. Never abbreviate `Undang-Undang` to `UU` in body text (only in chips/badges).
- **Numbers:** Indonesian locale — full stop as thousand separator, comma as decimal (e.g., `1.234,56`)
- **Dates:** `DD Month YYYY` in Indonesian (e.g., `28 Maret 2022`)
- **Pasal references:** `Pasal 1 ayat (2)` — not `Article 1(2)` or `Art. 1.2`
- **Disclaimer:** Every page displaying regulation content must show: `Informasi ini bukan nasihat hukum. Selalu verifikasi dengan sumber resmi OJK.`

---

## Do / Don't

| Do | Don't |
|----|-------|
| Use `bg-background` (#F5F5F0) as page background | Use pure white `#FFFFFF` as page background |
| Use borders to separate content | Use shadows for depth on cards |
| Use Instrument Serif for headings at weight 400 | Use bold/semibold on heading font |
| Use `font-mono` for regulation numbers and FRBR URIs | Use sans-serif for article numbers |
| Keep status colors semantic (green=berlaku, red=dicabut) | Use status colors decoratively |
| Use one accent color (Deep OJK Blue `#1B4F72`) | Add new accent colors without design review |
| Keep UI in Indonesian | Mix languages within a single UI string |

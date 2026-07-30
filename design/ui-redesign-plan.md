# TrimAURA UI Redesign Plan — ✅ COMPLETED

## Status: ✅ All changes deployed to Modal

The warm cream palette visual overhaul has been completed and deployed. See [PLAN.md](../PLAN.md) for full project status.

---

## Scope: Visual Upgrade Only (No Backend Changes)

| Feature | Status |
|---|---|
| Warm cream palette (`#EDE9E3`, gold accents) | ✅ Include |
| Circular template swatches (horizontal scroll) | ✅ Include |
| Pill-shaped URL input (30px radius) | ✅ Include |
| Green upload state + "READY TO PROCESS" | ✅ Include |
| Download-all icon button in CTA row | ✅ Include |
| Simplified drawer (remove title tabs) | ✅ Include |
| Simplified vault list (cleaner styling) | ✅ Include |
| Results section — simple clip grid (no ranking) | ✅ Include |
| **Ranked results with scores + TOP PICK badge** | **❌ Postponed** |
| **DeepSeek clip scoring (model + pipeline)** | **❌ Postponed** |

---

## Phase 1: CSS — Complete Theme Overhaul (`public/styles.css`)

### Color Palette
```css
--bg:#EDE9E3; --card:#FBF9F6; --hairline:#DDD5C8;
--ink:#1C1917; --ink-dim:#8A8378;
--gold:#C9A056; --gold-deep:#9C7530;
--green:#3A9D5E;
```

### New Components
| Component | CSS Class | Description |
|---|---|---|
| Phone frame (desktop) | `.frame` | 390×844 rounded container, 40px radius |
| Profile | `.profile`, `.avatar`, `.avatar-mark` | Diamond logo in circle |
| Stats | `.stats-row`, `.stat`, `.stat-sep` | 3 stats with separators |
| Section labels | `.section-label`, `span.hint` | Uppercase with gold hint |
| URL field | `.url-field` | Pill shape (30px border-radius) |
| Upload card | `.upload-card` | Green border when file selected |
| Style chips | `.style-row`, `.style-chip`, `.style-swatch` | Horizontal circular swatches (52px) |
| CTA row | `.cta-row`, `.cta`, `.icon-btn` | Generate + download-all + settings |
| Simple results | `.result-grid`, `.result-card` | **NEW** — unranked clip thumbnails |
| Vault items | `.vault-item`, `.vault-thumb`, `.vault-name`, `.vault-meta`, `.vault-status` | Clean list |

### Removed
- Desktop grid layout (3×2 → horizontal circles)
- Body tint on template select
- Sticky CTA, ambient glow pseudo-element
- Breathe animation on avatar

---

## Phase 2: Frontend HTML (`public/index.html`)

### New Layout (top → bottom)
```
.frame (390px container for desktop preview)
  .scroll
    .profile                  → Avatar + "TrimAURA" + tagline
    .stats-row                → 3 animated counters
    .section-label            → "New short"
    .url-field                → Google Drive URL pill input
    .divider-or               → "OR"
    .upload-card              → File upload with green "READY TO PROCESS"
    .section-label            → "Style" + active template name
    .style-row                → Horizontal circular template chips
    .cta-row                  → [Generate shorts] [download-all] [settings]
    .progress-track           → Upload/render progress
    .section-label            → "Results" + clip count
    #resultsList              → **NEW** simple clip thumbnails (no scores)
    .section-label            → "Clip vault" + pending count
    #historyList              → Simplified vault list
```

### Removed Elements
- Template grid (3×2) → replaced by circular chips
- Body tint/template attributes
- 3D perspective stage wrapper
- Settings modal → replaced with inline or simplified panel

### Kept Elements
- Drawer (simplified: remove title tabs)
- Toast notification
- PWA install button
- ServiceWorker registration
- Animated counters (updated font sizes)

---

## Phase 3: JavaScript Changes

### 3a. Results Section — Simple Grid
- After job completes, fetch clips from `GET /api/jobs/{jobId}`
- Render each clip as a simple card: thumbnail placeholder, title, duration, download button
- No scoring, no ranking, no TOP PICK badge
- Wire: click card → open drawer, click download → downloadSingleClip

### 3b. Style Picker — Circular Chips
- Load templates from `/api/templates`
- Render as horizontal scrollable circular swatches
- Active chip: gold ring (2.5px white + 4.5px gold border)
- Update template name hint on selection

### 3c. Upload Flow
- Keep XHR upload with real progress
- After job completes → render results section
- Auto-scroll to results

### 3d. Vault Simplification
- Remove action buttons (view, download-all, generate) from vault items
- Click vault item → open drawer
- Clean status badges (pill style)

---

## Phase 4: Drawer Simplification
- Remove title tabs (curiosity/direct/question)
- Show main curiosity title only
- Keep: video player, title text, clip meta, download, copy title, copy hashtags, refresh SEO
- Keep: clip nav dots for switching between clips

---

## Phase 5: Implementation Order

| # | Task | Files | Est. Time |
|---|---|---|---|
| 1 | Write new CSS theme | `styles.css` | 45min |
| 2 | Restructure HTML layout + new elements | `index.html` | 30min |
| 3 | JS: Circular style chip picker | `index.html` | 15min |
| 4 | JS: Simple results rendering | `index.html` | 15min |
| 5 | JS: Drawer simplification | `index.html` | 15min |
| 6 | JS: Wire results → playback | `index.html` | 10min |
| 7 | Polish, vault cleanup, responsive | `styles.css`, `index.html` | 20min |
| | **Total** | | **~2.5 hours** |

---

## Edge Cases
- **Mobile**: No `.frame` wrapper → full-width native layout
- **Template images**: Use gradient backgrounds as fallback
- **No clips yet**: Hide results section until first job completes
- **Single clip**: Show single card in results
- **Old jobs**: Show in vault as before, click opens drawer

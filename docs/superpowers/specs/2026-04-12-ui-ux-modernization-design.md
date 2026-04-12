# TaxFlow AI — UI/UX Modernization Design Spec

**Date:** 2026-04-12
**Status:** Approved
**Scope:** Theme system, responsive layout, top bar redesign, component updates, micro-interactions, settings, notifications, onboarding, analytics dashboard

---

## 1. Theme System (Dark / Light / System)

### Architecture

A `ThemeProvider` React context wraps the app at the root layout level. It manages three states: `light`, `dark`, `system`.

**Initialization:**
1. Check `localStorage` for key `taxflow-theme`
2. If absent, default to `system`
3. If `system`, read `window.matchMedia('(prefers-color-scheme: dark)')` and subscribe to changes
4. Apply `data-theme="light"` or `data-theme="dark"` on `<html>`

**Exports:** `useTheme()` hook returning `{ theme, resolvedTheme, setTheme }` where `theme` is the user preference (`light` | `dark` | `system`) and `resolvedTheme` is what's actually rendered (`light` | `dark`).

### CSS Token Architecture

Replace all hardcoded colors with semantic tokens resolved via `data-theme` attribute.

```css
[data-theme="light"] {
  --color-bg:               #f5f5f7;
  --color-surface:          #ffffff;
  --color-surface-secondary:#f5f5f7;
  --color-surface-tertiary: #e8e8ed;
  --color-text:             #1d1d1f;
  --color-text-secondary:   #6e6e73;
  --color-text-tertiary:    #86868b;
  --color-divider:          rgba(0, 0, 0, 0.1);
  --color-nav-bg:           rgba(255, 255, 255, 0.72);
  --color-nav-border:       rgba(0, 0, 0, 0.1);
  --color-chat-user:        #e8edf2;
  --color-chat-assistant:   #f5f5f7;
  --color-form-header:      #1E3A5F;
  --color-shadow:           rgba(0, 0, 0, 0.12);

  /* Badge dark-on-light tints */
  --badge-pending-bg:       #f3f4f6;  --badge-pending-text:     #4b5563;
  --badge-progress-bg:      #dbeafe;  --badge-progress-text:    #1d4ed8;
  --badge-review-bg:        #ffedd5;  --badge-review-text:      #c2410c;
  --badge-complete-bg:      #dcfce7;  --badge-complete-text:    #15803d;
  --badge-filed-bg:         #f3e8ff;  --badge-filed-text:       #7e22ce;
}

[data-theme="dark"] {
  --color-bg:               #000000;
  --color-surface:          #1c1c1e;
  --color-surface-secondary:#2c2c2e;
  --color-surface-tertiary: #3a3a3c;
  --color-text:             #f5f5f7;
  --color-text-secondary:   #a1a1a6;
  --color-text-tertiary:    #6e6e73;
  --color-divider:          rgba(255, 255, 255, 0.08);
  --color-nav-bg:           rgba(29, 29, 31, 0.72);
  --color-nav-border:       rgba(255, 255, 255, 0.08);
  --color-chat-user:        #2c2c2e;
  --color-chat-assistant:   #1c1c1e;
  --color-form-header:      #2a4a6f;
  --color-shadow:           rgba(0, 0, 0, 0.4);

  /* Badge light-on-dark tints */
  --badge-pending-bg:       rgba(142,142,147,0.2);  --badge-pending-text:   #a1a1a6;
  --badge-progress-bg:      rgba(10,132,255,0.2);   --badge-progress-text:  #64d2ff;
  --badge-review-bg:        rgba(255,159,10,0.2);    --badge-review-text:    #ffd60a;
  --badge-complete-bg:      rgba(48,209,88,0.2);     --badge-complete-text:  #30d158;
  --badge-filed-bg:         rgba(191,90,242,0.2);    --badge-filed-text:     #bf5af2;
}
```

Register as Tailwind v4 theme utilities via `@theme` in `globals.css`:

```css
@theme {
  --color-bg: var(--color-bg);
  --color-surface: var(--color-surface);
  --color-surface-secondary: var(--color-surface-secondary);
  /* ... etc for all tokens */
}
```

This enables usage like `bg-surface`, `text-primary`, `border-divider` throughout components.

### Theme Toggle Component

Location: Top bar, right side, between deadline badge and user avatar.

Behavior: Click cycles `system -> light -> dark -> system`. Icons:
- System: monitor/display icon
- Light: sun icon
- Dark: moon icon

Styling: `w-8 h-8 rounded-lg` ghost button, icon `w-4 h-4`, color `--color-text-secondary`, hover `bg-surface-secondary`.

Persistence: `localStorage.setItem('taxflow-theme', theme)` on every change.

### Component Migration

Every component replaces hardcoded colors with semantic tokens:

| Current | New (Tailwind class) |
|---|---|
| `bg-white` | `bg-surface` |
| `bg-[#f5f5f7]` | `bg-surface-secondary` or `bg-bg` |
| `text-[#1d1d1f]` | `text-primary` |
| `text-gray-500` / `text-gray-600` | `text-secondary` |
| `border-gray-200` | `border-divider` |
| `bg-[#e8edf2]` (chat user) | `bg-chat-user` |
| `bg-[#f5f5f7]` (chat assistant) | `bg-chat-assistant` |
| `bg-[#1E3A5F]` (form header) | `bg-form-header` |
| `rgba(0,0,0,0.8)` (nav) | `bg-nav` (via var) |

---

## 2. Responsive Layout & Breakpoints

### Breakpoint Definitions

| Name | Width | Layout | Panels Visible |
|---|---|---|---|
| Desktop XL | `>=1280px` | Full 3-column | Client sidebar + Chat + Work panel |
| Desktop/Laptop | `1024-1279px` | 2-column | Client sidebar + Chat. Work panel behind toggle |
| Tablet | `768-1023px` | 1-column + drawers | Chat only. Both sidebars behind toggles |
| Mobile | `<768px` | Single panel + bottom tabs | One panel at a time |

### Desktop XL (>=1280px)

No structural change from current layout. Sidebar `w-72`, chat `flex-1`, work panel `w-96`.

### Desktop/Laptop (1024-1279px)

- Work panel collapses out of the flow
- A floating toggle button appears top-right of chat area: document icon with badge count for pending review items
- Toggle slides work panel in as overlay from right, `w-96`, with `bg-black/30` backdrop
- Chat panel expands to fill the full width between sidebar and right edge
- Client sidebar stays visible at `w-72`

### Tablet (768-1023px)

- Both sidebars collapse out of the flow
- Top bar gains a hamburger icon (left side) for client sidebar
- Work panel toggle button remains (right side)
- Both panels open as overlays with backdrop
- Client sidebar overlay: `w-80`, slides from left
- Work panel overlay: `w-96`, slides from right (capped at `calc(100vw - 48px)`)
- Chat panel is full-width
- Top bar stats condense: counts only, no labels

### Mobile (<768px)

Complete layout replacement:

**Bottom Tab Bar (fixed, `h-14`, `z-40`):**

| Tab | Icon | Label | Content |
|---|---|---|---|
| Clients | people icon | Clients | Full-screen client list |
| Chat | chat bubble icon | Chat | Full-screen chat + sticky input |
| Documents | folder icon | Docs | Full-screen document list |
| Returns | file-text icon | Returns | Full-screen return preview |

Active tab: icon scales `1.1`, shifts to `--color-apple-blue`, label visible. Inactive: `--color-text-tertiary`, label hidden (icon only) to save space.

Content below top bar (`h-10`) and above tab bar (`h-14`). Each tab renders its panel as a full-screen view.

Client selection in Clients tab auto-switches to Chat tab.

Top bar slims to `h-10`: logo left, current client name (tappable, truncated), theme toggle right.

### Panel Overlay Mechanics

All overlays share:
- Backdrop: `bg-black/30`, tap to dismiss
- Slide animation: `transform: translateX()`, 300ms `cubic-bezier(0.4, 0, 0.2, 1)`
- Backdrop fade: 200ms
- Swipe to dismiss: left for client sidebar, right for work panel
- Body scroll lock when overlay is open

### Touch Targets

All interactive elements on tablet/mobile meet minimum `44px` tap target (Apple HIG):
- Sidebar client cards: `py-4 px-4`
- Search input: `h-12`
- Bottom tab buttons: `h-14` full-width touch zone
- Chat input: `min-h-[48px]`
- Modal buttons: `h-11`

---

## 3. Top Bar Redesign

### Glass Effect (Theme-Aware)

**Light mode:**
```css
background: rgba(255, 255, 255, 0.72);
backdrop-filter: saturate(180%) blur(20px);
border-bottom: 0.5px solid rgba(0, 0, 0, 0.1);
```

**Dark mode:**
```css
background: rgba(29, 29, 31, 0.72);
backdrop-filter: saturate(180%) blur(20px);
border-bottom: 0.5px solid rgba(255, 255, 255, 0.08);
```

Height: `h-12` (desktop/tablet), `h-10` (mobile). Position: `sticky top-0 z-50`.

### Content Layout by Breakpoint

**Desktop XL / Desktop (>=1024px):**
```
[Logo] TaxFlow AI     |     12 clients . 5 filed . 3 review     |     [chart] Apr 15 [sun/moon] [JD]
 (left)                      (center, text-secondary)                  (right, actions cluster)
```

- Left: Logo icon (blue `#0071e3` in both modes) + "TaxFlow AI" in `text-primary`
- Center: Stats as muted `text-secondary`, separated by midpoint dots (`\u00B7`)
- Right cluster: Dashboard icon button, deadline pill (red/orange tint, `rounded-full`), theme toggle, user avatar

**Tablet (768-1023px):**
```
[hamburger]  [Logo] TaxFlow AI     |     [chart] [Apr 15] [sun/moon] [JD]
```

- Hamburger icon added left (opens client sidebar overlay)
- Stats removed from bar (accessible in dashboard)
- Deadline condensed to date-only pill

**Mobile (<768px):**
```
[Logo]     Sarah Johnson v     [sun/moon]
```

- Logo left, current client name center (tappable dropdown or links to Clients tab), theme toggle right
- Avatar, stats, deadline, dashboard all move to other locations (bottom tabs, dashboard, settings)

### Logo

The "T" icon stays `#0071e3` (Apple Blue) in both themes as a brand anchor. App name text uses `text-primary`.

---

## 4. Component-Level Updates

### Chat Bubbles

- User: `bg-chat-user` (light: `#e8edf2`, dark: `#2c2c2e`)
- Assistant: `bg-chat-assistant` (light: `#f5f5f7`, dark: `#1c1c1e`)
- Text: `text-primary`
- Timestamps: `text-tertiary`
- Max-width: `max-w-[min(70%,560px)]` on desktop, `max-w-[85%]` on mobile
- New message animation: `translateY(8px) -> 0` + `opacity 0 -> 1`, 200ms ease-out

### Chat Input

**Desktop/Tablet:** Unchanged structure. Colors migrate to tokens: `bg-surface`, `border-divider`, `focus:border-[#0071e3]`. Quick chips below input.

**Mobile (<768px):**
- Sticky above bottom tab bar
- Quick chips hidden behind `+` button; opens horizontal scrollable chip strip, slide-up 200ms
- Send button only renders when input is non-empty (conditional `opacity` + `scale` transition)
- Attachment button always visible
- Textarea grows to max `160px` then scrolls internally

### Client Sidebar

- Background: `bg-bg` (light: `#f5f5f7`, dark: `#000000`)
- Active client card: `bg-surface` + `border-l-2 border-[#0071e3]` + `shadow-sm`
- Search: `bg-surface`, `border-divider`, `focus:border-[#0071e3]`
- "+ New Intake" button: stays `bg-[#0071e3] text-white`
- Mobile full-screen: cards get larger padding `py-4 px-4`, search gets `h-12`

### Cards

- Background: `bg-surface-secondary` (was `bg-[#f5f5f7]`)
- Border radius: `rounded-xl` (was `rounded-lg`)
- Shadow: theme-aware — light uses current Apple shadow, dark uses stronger `0 4px 24px var(--color-shadow)`

### Modals

- Background: `bg-surface`
- Width: `w-full max-w-[640px] mx-4` (was hardcoded `w-[640px]`)
- Mobile: full-screen bottom sheet, `rounded-t-2xl`, slides up from bottom
- Backdrop: `bg-black/50` both modes
- Desktop animation: `opacity 0->1` + `scale(0.97)->1`, 200ms
- Mobile animation: `translateY(100%)->0`, 300ms ease-out, dismissible by drag-down

### Buttons

- Primary: `bg-[#0071e3] text-white` — unchanged, consistent across themes
- Secondary: light `bg-[#1d1d1f] text-white`, dark `bg-[#f5f5f7] text-[#1d1d1f]` (inverted)
- Ghost: `text-primary`, hover `bg-surface-secondary`
- Pill: border color `border-[#0066cc]` stays; text and border adapt to `text-primary` in dark mode
- Press feedback: `scale(0.98)` for 50ms on all variants

### Inputs

- Background: `bg-surface`
- Border: `border-divider`, focus `border-[#0071e3]`
- Text: `text-primary`
- Placeholder: `text-tertiary`
- Mobile minimum height: `h-11` (44px)

### Badges

Light mode: current colors unchanged.

Dark mode: saturated tints on dark surface:
- Pending: `var(--badge-pending-bg)` / `var(--badge-pending-text)`
- In Progress: `var(--badge-progress-bg)` / `var(--badge-progress-text)`
- Review: `var(--badge-review-bg)` / `var(--badge-review-text)`
- Completed: `var(--badge-complete-bg)` / `var(--badge-complete-text)`
- Filed: `var(--badge-filed-bg)` / `var(--badge-filed-text)`

### Form Renderers (W-2, 1099-INT, Generic)

- Header: `bg-form-header` (light: `#1E3A5F`, dark: `#2a4a6f`)
- Field cells: `bg-surface`, `border-divider`
- Field labels: `text-tertiary`
- Field values: `text-primary`
- Currency amounts: stay semantic (green for refund, red for owed)

### Progress Bar

- Track: `bg-surface-tertiary`
- Fill colors: unchanged semantic palette (blue, green, orange, red, gray)

### Tabs

- Active: `text-[#0071e3] border-b-2 border-[#0071e3]` — unchanged
- Inactive: `text-secondary hover:text-primary`
- Active indicator: animated slide via `translateX` + `width`, 200ms
- Divider: `border-divider`

---

## 5. Micro-Interactions & Transitions

### Panel Transitions

```css
.panel-overlay {
  transform: translateX(var(--direction));
  transition: transform 300ms cubic-bezier(0.4, 0, 0.2, 1);
}
.panel-backdrop {
  opacity: 0;
  transition: opacity 200ms ease;
}
```

### Theme Transition

Temporary class on `<html>` during toggle:
```css
html.theme-transitioning,
html.theme-transitioning * {
  transition: background-color 300ms ease, color 200ms ease, border-color 200ms ease !important;
}
```
Applied for 400ms via JS timeout, then removed. Prevents transition side-effects during normal interaction.

### Message Animations

- New message: `translateY(8px)->0` + `opacity 0->1`, 200ms ease-out
- Typing indicator dots: 1s cycle (slowed from 0.7s), staggered 150ms between dots
- Message list on load: instant, no stagger animation

### Sidebar & List Items

- Client card hover (desktop only): `translateY(-1px)` + shadow increase, 150ms
- Active client switch: background crossfade 200ms, blue border fade-in 150ms
- Accordion expand/collapse: `grid-template-rows: 0fr -> 1fr`, 250ms ease

### Modals

- Desktop: `opacity 0->1` + `scale(0.97)->1`, 200ms
- Mobile sheet: `translateY(100%)->0`, 300ms ease-out
- Backdrop: fade 200ms

### Tabs

- Active indicator slides via `translateX` + `width`, 200ms

### Buttons

- Hover: `brightness(1.1)` + `scale(1.02)` primary only, 100ms
- Press: `scale(0.98)`, 50ms
- Focus ring: fade-in 150ms

### Bottom Tab Bar (Mobile)

- Active icon: `scale(1.1)` + color shift to blue, 150ms
- Panel switch: crossfade 150ms (no slide — tabs are peers)

### Excluded

- No page-level route transitions
- No staggered list load animations
- No parallax or spring physics
- No scroll-triggered animation

---

## 6. Functional & UX Improvements

### Keyboard Navigation

| Shortcut | Action |
|---|---|
| `Cmd/Ctrl + K` | Quick client search (spotlight overlay) |
| `Cmd/Ctrl + N` | Open New Intake modal |
| `Escape` | Close any overlay, modal, panel, or spotlight |
| `Tab` | Focus management through sidebar -> chat -> work panel |

**Spotlight Search:** Centered overlay (`max-w-lg`), auto-focus input, filters client list as-you-type, Enter selects top result, arrow keys navigate. Theme-aware colors. Backdrop `bg-black/30`.

### Empty States

Each panel gets a purposeful empty state with illustration placeholder, descriptive text, and primary action:

- **No client selected (chat area):** "Select a client to start" + "New Intake" button
- **No documents:** "Upload W-2s, 1099s, and other documents" + upload button
- **No messages:** "Ask a tax question about [Client Name]" + 3 suggested starter questions as chips
- **No returns:** "Documents need to be uploaded and reviewed before generating a return"

Illustrations are simple SVG line art, theme-aware (stroke uses `--color-text-tertiary`).

### Toast Notifications

Position: top-right (desktop), top-center (mobile).

Behavior:
- Slide in from right (desktop) / drop from top (mobile)
- Auto-dismiss after 4 seconds
- Hovering pauses the timer
- Max 3 stacked, oldest dismissed when exceeded
- Types: `success` (green left border), `error` (red left border), `info` (blue left border)

Styling: `bg-surface`, `rounded-xl`, `shadow-lg`, left color bar `3px`, icon + title + optional description, close `x` button.

Screen reader: `aria-live="polite"` container.

### Smart Scroll (Chat)

- Auto-scroll to newest message on send/receive
- If user has scrolled up (more than 100px from bottom), auto-scroll stops
- A floating "New messages" pill appears at bottom-center of chat area
- Click pill to scroll to bottom
- Pill: `bg-surface rounded-full shadow-md px-3 py-1.5 text-sm`, fade-in 200ms

### Loading States (Skeletons)

When API is fetching, show pulsing skeleton placeholders:
- Chat: 3 rounded rectangles (alternating widths) with `animate-pulse` in `bg-surface-tertiary`
- Client list: 4 skeleton cards (avatar circle + name bar + status bar)
- Work panel: skeleton lines (header bar + 6 content lines of varying width)
- Dashboard: skeleton metric cards + skeleton chart areas

### Active Client Persistence

Store in `localStorage`:
- `taxflow-active-client` — client ID
- `taxflow-active-tab` — work panel tab (documents / returns / filed)
- `taxflow-active-mobile-tab` — bottom tab bar selection

Read on mount, restore state. Clear when client is deleted.

### Accessibility

- All interactive elements: proper `aria-label` attributes
- Theme toggle: `aria-label="Switch to dark mode"` (dynamic based on state)
- Panel toggles: `aria-expanded`, `aria-controls`
- Tabs component: `role="tablist"`, `role="tab"`, `role="tabpanel"`, `aria-selected`
- Modals: `role="dialog"`, `aria-modal="true"`, focus trap
- Toasts: `aria-live="polite"` region
- All colors: minimum 4.5:1 contrast for text, 3:1 for UI elements (verified for both themes)
- Focus-visible: blue outline ring, `2px offset-2`, only on keyboard navigation (`:focus-visible`)
- Skip-to-content link (visually hidden, shown on focus)

---

## 7. Settings, Notifications, Onboarding & Analytics Dashboard

### 7.1 Settings Page

**Access:** User avatar in top bar -> dropdown menu -> "Settings". On mobile: avatar tap or dedicated settings icon in profile area.

**Layout:**
- Desktop: Full-screen overlay with centered card `max-w-2xl`, height `max-h-[calc(100vh-96px)]`
- Left nav sidebar within the card for section navigation
- Mobile: full-screen bottom sheet, sections stack vertically as accordions

**Sections:**

**Profile**
- Fields: Name, email, firm name, role (all read-only with "Edit" button)
- Avatar: circular display with "Upload" placeholder button
- All placeholder data, editable UI wired to local state only

**Appearance**
- Theme picker: 3-option segmented control (Light / Dark / System) with live preview swatches
- Density toggle: Comfortable (default) / Compact — adjusts base font size and spacing scale
- Both persist to `localStorage`

**Notification Preferences**
- Table of categories (see Section 7.2) with toggle switches
- In-app column: functional toggles
- Email column: disabled toggles with "Coming soon" tooltip

**Tax Defaults**
- Default tax year: dropdown (2022-2025)
- Default filing status: dropdown (Single, MFJ, MFS, HOH, QSS)
- Default state: dropdown (50 states + DC)
- Pre-fills New Intake modal

**Keyboard Shortcuts**
- Reference table: two columns (shortcut, action)
- "Customize" button: disabled, placeholder for future

**Data & Privacy**
- "Export Client Data" button: placeholder (shows toast "Coming soon")
- "Clear Local Cache" button: clears all localStorage, reloads
- Session info: login time placeholder, session ID placeholder

**About**
- Version: `0.1.0`
- "What's New" link: placeholder changelog
- "Send Feedback" link: placeholder
- "Replay Onboarding Tour" button: resets `onboarding_complete` flag and triggers tour

### 7.2 Notification System

**Bell Icon (Top Bar):**
- Position: right cluster, between dashboard icon and theme toggle
- Badge: red dot (unread count > 0) or number badge if > 9
- Click: dropdown panel (desktop `w-80 max-h-96`), full-screen sheet (mobile)

**Notification Panel:**
- Header: "Notifications" + "Mark all read" button
- List: each entry has icon (type-specific), title, description (optional), relative timestamp, unread dot
- Empty state: "All caught up" with checkmark illustration
- Footer: "View all" link (placeholder — scrolls to show more in same panel)
- Dismiss on click outside (desktop) or drag-down (mobile)

**Notification Types:**

| Category | Icon | Example |
|---|---|---|
| Document | upload icon | "W-2 uploaded for Sarah Johnson" |
| Extraction | scan icon | "Data extracted from 1099-INT — ready for review" |
| Return | file icon | "Draft return generated for Mike Chen" |
| Message | chat icon | "New response for Sarah Johnson's query" |
| Deadline | clock icon | "April 15 deadline — 8 returns pending" |
| System | info icon | "TaxFlow updated to v0.2.0" |

**Placeholder data:** 5-6 hardcoded notification entries with varying types and read/unread states.

### 7.3 Onboarding Flow

**Trigger:** First visit (detected via `localStorage` key `onboarding_complete`). Also re-triggerable from Settings > About > "Replay Tour".

**3-step spotlight walkthrough over the real UI:**

**Step 1 — "Meet your workspace"**
- Spotlight: dims everything, highlights the full 3-panel layout
- Tooltip card: floating, positioned top-center
- Text: "Your clients are on the left. Chat with the AI tax agent in the center. Review documents and returns on the right."
- Demo client "Demo Client" pre-loaded so panels are populated
- Buttons: "Next" (primary) / "Skip tour" (ghost)

**Step 2 — "Start with a client"**
- Spotlight: highlights the "+ New Intake" button in the sidebar
- Tooltip card: positioned to the right of the button
- Text: "Add a new client to begin. Upload their W-2s and 1099s, and the AI agent will help prepare their return."
- Buttons: "Next" / "Skip tour"

**Step 3 — "Ask anything"**
- Spotlight: highlights the chat input area
- Tooltip card: positioned above the input
- Text: "Ask tax questions in plain English. The agent pulls from IRS rules, instructions, and publications to give you sourced answers."
- Button: "Get Started" (primary) — dismisses overlay, sets `onboarding_complete = true`

**Spotlight implementation:**
- Full-screen overlay `fixed inset-0 z-[60]` with `bg-black/60`
- Cutout around highlighted element using CSS `clip-path` (calculated from element's `getBoundingClientRect()`)
- Tooltip card: `bg-surface rounded-2xl p-6 shadow-xl max-w-[360px]`
- Arrow pointer from card to highlighted element
- Step indicator: 3 dots at bottom of card (filled/outline)

**Mobile adaptation:** Spotlight still works, but tooltip repositions to avoid overflow. On very small screens, tooltip becomes a bottom sheet instead of a floating card.

### 7.4 Analytics Dashboard

**Access:**
- Desktop: Chart icon button in top bar right cluster. Also shown as default view when no client is selected.
- Mobile: 5th bottom tab icon (chart icon) OR accessible from top bar icon (either approach works; recommend top bar icon to keep 4 tabs clean).

**Decision: Access the dashboard via the top bar chart icon on all breakpoints, and as the default "no client selected" state in the chat area.** This avoids adding a 5th tab on mobile and keeps the tab bar focused on core workflow.

**Layout:** Occupies the chat panel area. Scrollable. Responsive grid.

**Row 1 — Summary Metrics (4 cards)**

Desktop: 4-column grid. Tablet: 2x2 grid. Mobile: 2x2 grid.

| Metric | Value | Accent | Subtext |
|---|---|---|---|
| Total Clients | 67 | blue | +3 from last month |
| Returns Filed | 42 | green | 63% of season |
| Pending Review | 12 | orange | 5 urgent |
| Revenue | $148,500 | green | +12% YoY |

Card styling: `bg-surface rounded-xl p-5`, large value `text-3xl font-semibold`, label `text-sm text-secondary uppercase`, trend `text-xs` with up/down arrow and color.

All values hardcoded placeholder.

**Row 2 — Filing Pipeline (full width)**

Horizontal funnel visualization:

```
Intake (8) -> Documents (12) -> Review (15) -> Filing (18) -> Complete (14)
```

Each stage: column with count, colored bar segment proportional to count, stacked avatar circles (max 3 visible + "+N" overflow). Clickable — filters client list (placeholder interaction: shows toast "Filter coming soon").

Desktop: horizontal bar. Mobile: vertical stack.

Styling: `bg-surface rounded-xl p-5`, stage bars use semantic colors (gray -> blue -> orange -> blue -> green).

**Row 3 — Two-column split (stacks on mobile)**

**Left Column: Deadline Timeline**

Vertical timeline with:
- `Apr 15, 2026` — Individual returns (8 clients) — **red accent (overdue/imminent)**
- `Jun 15, 2026` — Estimated Q2 payments (3 clients) — orange accent
- `Sep 15, 2026` — Extension deadline (2 clients) — yellow accent
- `Jan 15, 2027` — Estimated Q4 payments (1 client) — gray accent

Each entry: date pill (left), connecting vertical line, description + client count (right).

**Right Column: Recent Activity Feed**

Chronological list, max 10 items:
- Upload icon — "Sarah Johnson's W-2 uploaded" — 2h ago
- Scan icon — "Data extracted from Mike Chen's 1099-INT" — 5h ago
- File icon — "Draft return generated for Lisa Park" — 8h ago
- Chat icon — "New response for David Kim's query" — 1d ago
- Person icon — "New client James Wright added" — 1d ago

Each entry: `icon (text-secondary) | description (text-primary) | timestamp (text-tertiary)`.

"View all" link at bottom (placeholder).

**Row 4 — Season Progress (full width)**

Horizontal segmented progress bar:
- "Tax Season 2025: 42 of 67 returns filed (63%)"
- Segments: Filed (green, 63%) | In Review (orange, 18%) | Pending (gray, 19%)
- Legend below with dot + label + count for each segment

Styling: `bg-surface rounded-xl p-5`, bar `h-3 rounded-full`, segments with smooth width transitions.

---

## 8. New File Inventory

### New Components

| File | Purpose |
|---|---|
| `components/providers/theme-provider.tsx` | ThemeProvider context + useTheme hook |
| `components/layout/bottom-tab-bar.tsx` | Mobile bottom navigation |
| `components/layout/panel-overlay.tsx` | Shared overlay wrapper for sidebar/work panel |
| `components/layout/theme-toggle.tsx` | Sun/moon/system toggle button |
| `components/ui/toast.tsx` | Toast notification component + ToastProvider |
| `components/ui/skeleton.tsx` | Skeleton loading primitives |
| `components/ui/spotlight.tsx` | Onboarding spotlight overlay |
| `components/ui/empty-state.tsx` | Reusable empty state component |
| `components/settings/settings-modal.tsx` | Settings page modal/sheet |
| `components/settings/profile-section.tsx` | Profile settings section |
| `components/settings/appearance-section.tsx` | Theme + density settings |
| `components/settings/notifications-section.tsx` | Notification preference toggles |
| `components/settings/defaults-section.tsx` | Tax default settings |
| `components/settings/shortcuts-section.tsx` | Keyboard shortcut reference |
| `components/settings/about-section.tsx` | Version, changelog, tour replay |
| `components/notifications/notification-bell.tsx` | Bell icon + dropdown panel |
| `components/notifications/notification-item.tsx` | Single notification row |
| `components/onboarding/onboarding-tour.tsx` | 3-step spotlight tour |
| `components/dashboard/analytics-dashboard.tsx` | Full analytics dashboard (replaces current dashboard) |
| `components/dashboard/metric-card.tsx` | Single metric card |
| `components/dashboard/filing-pipeline.tsx` | Horizontal funnel |
| `components/dashboard/deadline-timeline.tsx` | Vertical deadline timeline |
| `components/dashboard/activity-feed.tsx` | Recent activity list |
| `components/dashboard/season-progress.tsx` | Segmented progress bar |
| `lib/hooks/use-media-query.ts` | Responsive breakpoint hook |
| `lib/hooks/use-local-storage.ts` | localStorage state hook |
| `lib/hooks/use-keyboard-shortcut.ts` | Keyboard shortcut registration |

### Modified Components (all existing files)

Every existing component gets theme token migration (hardcoded colors -> semantic classes). Additionally:

| File | Key Changes |
|---|---|
| `app/layout.tsx` | Wrap in ThemeProvider, ToastProvider |
| `app/page.tsx` | Add responsive layout logic, breakpoint-driven panel visibility, bottom tab bar |
| `styles/globals.css` | Full token rewrite with `[data-theme]` selectors, animation keyframes |
| `components/layout/top-bar.tsx` | Glass effect, responsive content, hamburger, avatar dropdown with settings |
| `components/layout/client-sidebar.tsx` | Overlay mode for tablet/mobile, touch targets |
| `components/layout/chat-panel.tsx` | Smart scroll, empty state, responsive input |
| `components/layout/work-panel.tsx` | Overlay mode, toggle button |
| `components/chat/chat-input.tsx` | Mobile sticky bar, collapsible chips, conditional send button |
| `components/chat/message-bubble.tsx` | Theme tokens, max-width cap, slide-in animation |
| `components/chat/message-list.tsx` | Smart scroll behavior, skeleton loading |
| `components/chat/typing-indicator.tsx` | Slowed animation timing |
| `components/ui/button.tsx` | Theme tokens, press scale feedback |
| `components/ui/card.tsx` | Theme tokens, rounded-xl, theme-aware shadow |
| `components/ui/modal.tsx` | Responsive (centered vs bottom sheet), theme tokens |
| `components/ui/input.tsx` | Theme tokens, mobile min-height |
| `components/ui/badge.tsx` | Theme-aware badge colors via CSS variables |
| `components/ui/avatar.tsx` | Theme tokens |
| `components/ui/progress.tsx` | Theme-aware track color |
| `components/ui/tabs.tsx` | Sliding active indicator, theme tokens |
| `components/clients/intake-modal.tsx` | Responsive width, mobile sheet, theme tokens |
| `components/documents/document-viewer-modal.tsx` | Responsive width, mobile sheet, theme tokens |
| `components/forms/w2-form.tsx` | Theme-aware form header and field colors |
| `components/forms/form-1099-int.tsx` | Theme-aware form header and field colors |
| `components/forms/generic-form.tsx` | Theme-aware form header and field colors |
| `components/forms/form-renderer.tsx` | Theme tokens |
| `components/returns/return-preview.tsx` | Theme tokens, responsive layout |
| `components/dashboard/dashboard.tsx` | Replaced by analytics-dashboard.tsx |

---

## 9. Implementation Priority

Recommended build order (each step produces a working, testable state):

1. **Theme system** — Provider, tokens, globals.css rewrite, toggle component
2. **Component token migration** — All existing components swap to semantic classes
3. **Top bar redesign** — Glass effect, responsive content, avatar dropdown
4. **Responsive layout shell** — Breakpoint logic, panel overlay mechanics, page.tsx restructure
5. **Bottom tab bar** — Mobile navigation
6. **Chat input mobile** — Sticky bar, collapsible chips
7. **Modal responsive** — Bottom sheet on mobile
8. **Micro-interactions** — Panel transitions, message animations, button feedback, tab indicator
9. **Empty states + skeletons + toasts** — UX polish components
10. **Smart scroll + keyboard shortcuts** — Chat scroll behavior, Cmd+K spotlight
11. **Settings page** — All sections with placeholder data
12. **Notification system** — Bell icon, dropdown, preferences
13. **Onboarding tour** — 3-step spotlight walkthrough
14. **Analytics dashboard** — All sections with placeholder data
15. **Accessibility pass** — ARIA attributes, focus management, contrast verification

# Deep Space Glassmorphism Design System

> This document defines the visual standards for the "Deep Space" aesthetic. It is designed to be content-agnostic and reusable across various web projects.

## 1. Core Philosophy

- **Theme:** "Deep Space" - Dark, immersive, and premium.
- **Materiality:** Glassmorphism. Elements are semi-transparent layers floating in space.
- **Lighting:** Everything emits its own light. Use inner glows, drop shadows, and vivid gradients to create depth.
- **Motion:** Interfaces should feel alive with subtle pulses, fades, and hovers.

## 2. Color System

### Backgrounds

| Token | Value | Usage |
|-------|-------|-------|
| `bg-gradient` | `linear-gradient(135deg, #0f172a 0%, #1e1a78 100%)` | Main body background |
| `glass-bg` | `rgba(255, 255, 255, 0.03)` | Card background |
| `glass-border` | `rgba(255, 255, 255, 0.08)` | Card borders |
| `glass-highlight` | `rgba(255, 255, 255, 0.1)` | Hover states/Active borders |

### Accents

| Token | Value | Usage |
|-------|-------|-------|
| `accent-cyan` | `#06b6d4` | Primary brand color, active states, key data |
| `accent-purple` | `#8b5cf6` | Secondary accent, gradients |
| `accent-glow` | `rgba(6, 182, 212, 0.4)` | Box-shadows for active elements |

### Semantic Status

| Token | Hex | Usage |
|-------|-----|-------|
| `status-ok` | `#10b981` (Emerald-500) | Healthy, Online, Success |
| `status-warn` | `#f59e0b` (Amber-500) | Warning, High Load, Degraded |
| `status-error` | `#ef4444` (Red-500) | Offline, Error, Critical |

### Typography Colors

| Token | Value | Usage |
|-------|-------|-------|
| `text-main` | `#f0f6fc` | Headings, primary content |
| `text-muted` | `#94a3b8` | Metadata, labels, secondary text |

## 3. Typography

- **Primary Font:** Inter (UI, Body)
- **Heading Font:** Outfit (Headings, Branding)
- **Monospace:** JetBrains Mono (Data, IPs, Logs)

### Scale

| Element | Size | Weight | Notes |
|---------|------|--------|-------|
| H1 (Page Title) | 24px | 700 | Text Gradient (`#fff` -> `#cbd5e1`) |
| H2 (Card Title) | 14px | 600 | Uppercase, Tracking 1px |
| Body | 15px | 400 | |
| Small/Meta | 12px | 500 | |

## 4. UI Components

### Glass Cards

The fundamental building block of the layout.

```css
.card {
  background: rgba(255, 255, 255, 0.03);
  backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 24px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
}
```

**Interactions:** On hover, cards should lift (`translateY(-4px)`) and increase brightness.

### Navigation Tabs

Pill-shaped, floating navigation.

- **Container:** Glass background, full rounded corners (`border-radius: 50px`).
- **Inactive Item:** Transparent background, muted text.
- **Active Item:** Cyan background, dark text, glow shadow.

```css
.tab-active {
  background: var(--accent-cyan);
  color: #0f172a;
  box-shadow: 0 0 20px rgba(6, 182, 212, 0.4);
}
```

### Status Indicators

Do not use flat colors. Use "Orbs" that glow.

- **Shape:** Circle, 6px-8px.
- **Effect:** `box-shadow: 0 0 8px currentColor`.
- **Animation:** Pulse opacity/shadow for "live" statuses.

### Data Bars

- **Track:** `rgba(255,255,255,0.1)`
- **Fill:** Always use a gradient (e.g., Cyan -> light Cyan) for depth.
- **Animation:** Smooth width transitions (`transition: width 1s cubic-bezier(...)`).

## 5. Layout Patterns

### Mesh Background

To avoid a boring flat background, use a subtle rotating mesh or gradient blob behind the glass content.

```css
body::before {
  background: radial-gradient(circle, rgba(76, 29, 149, 0.15), transparent 60%);
  /* Animation: slow rotate */
}
```

### Grid vs Tabs

- **Dashboard View:** Responsive Grid (`grid-template-columns: repeat(auto-fit, minmax(400px, 1fr))`).
- **Focused View:** Centered container (`max-width: 1000px`) with Tab navigation.

## 6. Implementation Checklist

- [x] Import Outfit and Inter from Google Fonts.
- [x] Set `box-sizing: border-box` globally.
- [x] Ensure `backdrop-filter` is supported or provided with a fallback background.
- [x] Use CSS Variables for all colors to allow easy theming adjustments.

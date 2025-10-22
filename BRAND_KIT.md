# Brand Kit — National Archives Discovery Clone (clio)

This brand kit defines the visual identity for the project and provides ready‑to‑use assets. It mirrors the gradients and tokens already used in `web/static/css/main.css` to keep the web UI and documentation consistent.

## Brand Essence
- Professional, research‑grade, trustworthy
- Clean typography, ample white space, bright gradient accents

## Naming
- Product name: clio (lowercase)
- Repository: National Archives Discovery Clone

## Logos and Assets
- Full wordmark + symbol: `logos/combined-logo.png`, `logos/combined-logo-no-background.png`
- Symbol only: `logos/symbol-logo.png`, `logos/symbol-logo-no-background.png`
- Wordmark only: `logos/text-logo.png`, `logos/text-logo-no-background.png`
- App UI assets: `web/static/images/logo.png`, `web/static/images/logo-symbol.png`, `web/static/images/favicon.png`

Usage guidance:
- Prefer the full wordmark on light backgrounds.
- Use the symbol only (square) for small sizes (≤48px) and favicons.
- Maintain clear space equal to the height of the “o” in the wordmark around the logo.
- Do not alter colors or stretch/squash the logo; scale proportionally.

## Color System
Primary gradient (brand):
- Cyan: `#1B9BD7`
- Blue: `#2E7AC5`
- Purple: `#7B5EA7`
- Magenta: `#B64896`
- Pink: `#D64398`

Neutrals:
- `--white: #ffffff`
- `--gray-50: #f9fafb`
- `--gray-100: #f3f4f6`
- `--gray-200: #e5e7eb`
- `--gray-300: #d1d5db`
- `--gray-400: #9ca3af`
- `--gray-500: #6b7280`
- `--gray-600: #4b5563`
- `--gray-700: #374151`
- `--gray-800: #1f2937`
- `--gray-900: #111827`

CSS gradients (reference):
- `--gradient-brand: linear-gradient(135deg, #1B9BD7 0%, #7B5EA7 50%, #D64398 100%)`
- Hover: `--gradient-brand-hover: linear-gradient(135deg, #1585bc 0%, #694d8f 50%, #b9397f 100%)`

## Typography
- UI/Docs Sans: Inter (preferred) or Segoe UI / Roboto / Helvetica Neue / Arial
- Weights: 400 (regular), 600 (semibold), 700/800 (headings)
- Web import (already in `base.html`): Google Fonts Inter

Pairing suggestions:
- Headings: Inter 700/800
- Body: Inter 400/500
- Small UI labels, badges: Inter 600

## Iconography
- Bootstrap Icons (CDN) used in UI (see `base.html`).
- Use outline or filled variants consistently per component.

## Imagery
- Background hero: `web/static/images/archive-background.jpg` (muted; content overlay uses a white screen blend for readability).

## Components (tokens reflected in CSS)
- Buttons: Primary uses brand gradient with hover elevation
- Cards: White, rounded (`--radius-xl`), soft shadows (`--shadow-md/--shadow-xl`)
- Badges: Uppercase, `--radius-full`

## Accessibility
- Minimum contrast: 4.5:1 for text on backgrounds
- Focus states: visible `outline` styles are included in CSS
- Avoid gradient text for long body copy; reserve for short headings/accents

## Favicons and App Icons
- Favicon: `web/static/images/favicon.png` (symbol-only variant recommended)
- For new sizes, export square 512×512 and 180×180 from the symbol logo.

## Usage Examples
- README badges and hero use brand colors 
- Web nav uses `logo.png` (48px height) with gradient accents in hover states

## Attribution and Licensing
- Branding assets are provided for this project’s use. Redistribution or adaptation should preserve project attribution.

## Change Management
- Any changes to colors, typography, or logos should be reflected both in this document and in `web/static/css/main.css` to avoid drift.

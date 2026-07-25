# Anti-Slop OSS Privacy — DESIGN.md

## Direction

brutalist

## Stack

Stack 3 — OSS / Privacy-first:

- Open Design (nexio) — local-first, BYOK
- Taste Skill (VARIANCE / MOTION / DENSITY)
- ux-ui-agent-skills (DTCG tokens + WCAG 2.2 audit)
- Refactoring UI (methodology)

## Anti-Slop Checklist

- [ ] Primary typeface is NOT Inter / Roboto / Arial / Space Grotesk.
- [ ] No single centered hero section with one button.
- [ ] No decorative gradient blob left / top.
- [ ] No three equal cards with equal padding and icon top.
- [ ] No flat gray text (#666666–#999999) on pure white.
- [ ] No generic 8px/card shadows (`0 4px 6px`, `shadow-md`, etc.).
- [ ] Motion uses transform / opacity / filter / clip-path only.
- [ ] Scroll animations use stagger / transform, not blanket fade-in.

## Privacy Constraints

- All design-system files stay on local machine.
- API keys are user-provided (BYOK).
- No cloud upload of client assets without explicit approval.

## Typography

- Display: Druk Wide / Thunder / Arial Black
- Body: Neue Montreal / Helvetica Now
- Mono: SF Mono / Inconsolata

## Color System

- Background: #FFFFFF
- Surface: #F3F3F3
- Text: #000000
- Muted: #333333
- Accent: #FF2A00
- Border: #E5E5E5

## Motion

- Easing: cubic-bezier(0.87, 0, 0.13, 1)
- Allowed properties: transform, opacity, filter, clip-path
- VARIANCE, MOTION, DENSITY knobs from Taste Skill.

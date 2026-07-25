# Anti-Slop Solo Frontend — DESIGN.md

## Direction

editorial

## Stack

Stack 1 — Solo Frontend:

- Anthropic Frontend Design Skill (base hygiene)
- Impeccable (audit / polish)
- Motion / Framer Motion (animations)
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

## Typography

- Display: Playfair Display / Tiempos Headline
- Body: Plus Jakarta Sans / Suisse Int’l
- Mono: JetBrains Mono

## Color System

- Background: #FCFCF9
- Surface: #FFFFFF
- Text: #1A1A17
- Muted: #73736E
- Accent: #8B3A3A
- Border: #E8E8E6

## Motion

- Easing: cubic-bezier(0.16, 1, 0.3, 1)
- Allowed properties: transform, opacity, filter, clip-path
- Respect prefers-reduced-motion.

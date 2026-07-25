# Anti-Slop Team Claude Design — DESIGN.md

## Direction

swiss

## Stack

Stack 2 — Team Claude Design:

- Claude Design (canvas + /design-sync)
- Brand compliance
- Impeccable (PR review)
- Transitions.dev (curated transitions)
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

## Design System Import

Source: GitHub repository containing design_tokens.json + component library.
Sync command: `/design-sync` in Claude Code.
Brand compliance policy: enforced at platform level.

## Typography

- Display: Helvetica Now Display / Neue Haas Grotesk
- Body: Geist Sans / SF Pro Text
- Mono: Geist Mono

## Color System

- Background: #FAFAFA
- Surface: #FFFFFF
- Text: #0A0A0B
- Muted: #6B6B75
- Accent: #0055FF
- Border: #E5E5E8

## Motion

- Easing: cubic-bezier(0.25, 0.1, 0.25, 1)
- Allowed properties: transform, opacity, filter, clip-path
- Transitions: curated set from Transitions.dev with prefers-reduced-motion.

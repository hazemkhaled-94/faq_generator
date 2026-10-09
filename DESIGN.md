---
# gstack: design-md-format=spec
name: Q&A Generator
description: An operator's ledger for a seven-stage document pipeline. Dense, quiet, one purple accent; a figure and the rows it counts share one screen.
colors:
  primary: "#A100FF"          # accent on the light ground
  primary-on-dark: "#C2A3FF"  # accent on the dark ground
  on-primary: "#FFFFFF"
  on-primary-dark: "#16121D"
  figure: "#460073"           # metric values, light ground
  surface: "#FFFFFF"
  surface-raised: "#F7F4FB"
  surface-dark: "#16121D"
  surface-raised-dark: "#1F1A2A"
  text: "#1A1A1A"
  text-dark: "#EDEAF2"
  text-muted: "#6A6A6A"       # 65% of text over the ground
  border: "#E4E1EA"
  border-dark: "#332C45"
  table-header: "#E6DCFF"
  table-header-dark: "#2E1A45"
  sidebar: "#460073"
  sidebar-dark: "#340056"
  error: "#A32020"            # deletion only
  error-on-dark: "#F08A8A"
typography:
  display:
    fontFamily: Graphik, Arial, Helvetica, sans-serif
    fontWeight: 700
    fontSize: 1.5rem
    letterSpacing: -0.03em
  heading:
    fontFamily: Graphik, Arial, Helvetica, sans-serif
    fontWeight: 600
    fontSize: 0.95rem
    letterSpacing: -0.01em
  body:
    fontFamily: Graphik, Arial, Helvetica, sans-serif
    fontSize: 14px
    lineHeight: 1.5
  label:
    fontFamily: Graphik, Arial, Helvetica, sans-serif
    fontWeight: 600
    fontSize: 0.86rem
    letterSpacing: 0.02em
  figure:
    fontFamily: Graphik, Arial, Helvetica, sans-serif
    fontWeight: 700
    fontSize: 1.5rem
    fontFeature: tnum
  mono:
    fontFamily: Source Code Pro
    fontFeature: tnum
rounded:
  md: 8px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.md}"
  button-danger:
    borderColor: "{colors.error}"
    textColor: "{colors.error}"
    rounded: "{rounded.md}"
  panel:
    borderColor: "{colors.border}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
  table-header:
    backgroundColor: "{colors.table-header}"
---

# Q&A Generator

## Overview

**Creative North Star:** an industrial ledger. Every number on a page can be
followed to the rows behind it, and both are on screen together.

**Product context:** a Streamlit console for one or two operators. It runs a
seven-stage pipeline (upload, parsing, chunking, extraction, topics, questions,
assessment) and audits what each stage wrote.

**Mode per surface:** Operate, on every page. The "How it works" folds are
Read.

**Key characteristics:**

- One page per stage, all laid out the same way.
- Figures first, then the controls, then the table that the figures count.
- The purple marks structure only: section labels, figures, the sidebar.
- No page scrolls before its table.

## The fold

The one hard rule. At **1440×900**, a listing page shows its table, with at
least eight rows, before any scrolling.

| Band | Budget |
|---|---|
| Header: page title, product name, rule | ≤ 56px |
| Overview: one strip of figures. Assessment's is the one two-row band: the kind shown and the disagreements filter, then the figures | ≤ 72px of content |
| Service: queue verbs and state line, then its three folds in one row | ≤ 120px |
| Search and filters: search, filters, pager | one row, two on Questions |
| Table | everything left |

Measured on 2026-10-01, the table panel starts at 471px on Passages, Facts
and Topics, 535–538px on Assessment and Questions, and 572px on Documents.
System health fits its figures and services table, and its components table
starts in the fold.

What is shown only on request (a picked row, an open fold) may push below the
fold. What a page opens with may not.

## Colors

**Strategy:** Committed. One purple accent sits on neutral grounds. Red is
spent on deletion and nothing else.

**Light or dark:** light by default, because the console is used at a desk in
daylight. Dark follows the toolbar menu or the OS. Every pair in
`styles.css` is written light-first with `light-dark()`. Neutrals are mixed
from `currentColor`, so they follow whichever theme is active.

## Typography

The brand stack is Graphik, falling back to Arial. Arial would be a weak choice
for a display face. Here the hierarchy comes from size and weight, and Arial is
the brand's own substitute. Ids and digests use Source Code Pro, which ships
with Streamlit, so no font is downloaded. Figures use tabular numerals so that
columns of numbers line up.

The base size is 14px (`theme.baseFontSize`). Every rem-based measure in
Streamlit and in `styles.css` scales from it.

## Layout

There is one column, at most 1320px wide, beside the sidebar. Sections are
bordered panels with the label drawn inside the border. A panel never holds
another bordered box.

## Elevation & Depth

None. Hairline borders and the table-header tint are the only layering.

## Shapes

All corners use one 8px radius (`theme.baseRadius`). The only round shape is
the queue spinner.

## Components

| Component | Rule |
|---|---|
| Panel | `page.panel`. Label 0.95rem/600 in purple, then content, with a gap of about 8px. |
| Figures | `page.stats`. Unbordered inside the Overview panel, and each carries a tooltip. |
| Queue row | `stage.service`, `pipeline.panel`. A horizontal container. The verbs are sized to their labels, with the state line muted beside them. Disabled verbs stay readable and say why in their tooltip. |
| Folds | `page.folds`. Analysis, How it works and Configuration share one row while closed. An opened fold stacks them all at full width. |
| Search and filters | `catalog.find`. One panel; the search box comes first and widest, the pager last, and the controls wrap only when a row is full. |
| Table | `page.table`. A Streamlit dataframe with single-row selection, filled with the tinted header. |
| Deletion | `stage.removal`. A red panel; the first click arms it and a separately labelled second click acts. |

## Do's and Don'ts

- Do: measure every changed page at 1440×900 before calling it done.
- Do: put new content in an existing fold or behind a selection.
- Do: give every figure a tooltip that says what it counts.
- Don't: add a second accent colour, a shadow or a gradient fill.
- Don't: nest a bordered box in a panel.
- Don't: size a button by column width, or its label will truncate.

## Motion

- **Approach:** minimal-functional.
- **The one authored moment:** the queue spinner, which runs while a stage has work in flight. It slows down under `prefers-reduced-motion`.

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-10-01 | Initial design system created | Created by /design-consultation from the existing theme and design knowledge. Tables sat 74–255px below a 900px fold on seven of eight pages. |
| 2026-10-01 | 14px base, merged header, one Search and filters panel, unbordered figures | Buys back the vertical space the fold rule needs. |
| 2026-10-01 | Labels at 0.86rem, section labels at 0.95rem | At a 14px base the earlier 0.7rem labels came out under 12px. |
| 2026-10-01 | A service's folds share one row; Analysis moved into the service panel | Three stacked folds cost about 90px on every listing page. |

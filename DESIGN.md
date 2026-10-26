---
# gstack: design-md-format=spec
name: FAQ Generator description: An operator's ledger for a seven-stage
document pipeline. Dense, quiet, one purple accent; a figure and the rows it
counts share one screen. colors: primary: "#A100FF"          # accent on the
light ground primary-on-dark: "#C2A3FF"  # accent on the dark ground
on-primary: "#FFFFFF" on-primary-dark: "#16121D" figure: "#460073"           #
metric values, light ground surface: "#FFFFFF" surface-raised: "#F7F4FB"
surface-dark: "#16121D" surface-raised-dark: "#1F1A2A" text: "#1A1A1A"
text-dark: "#EDEAF2" text-muted: "#6A6A6A"       # 65% of text over the ground
border: "#E4E1EA" border-dark: "#332C45" table-header: "#E6DCFF"
table-header-dark: "#2E1A45" sidebar: "#460073" sidebar-dark: "#340056" error:
"#A32020"            # deletion only error-on-dark: "#F08A8A" typography:
display: fontFamily: Graphik, Arial, Helvetica, sans-serif fontWeight: 700
fontSize: 1.5rem letterSpacing: -0.03em heading: fontFamily: Graphik, Arial,
Helvetica, sans-serif fontWeight: 600 fontSize: 0.95rem letterSpacing: -0.01em
body: fontFamily: Graphik, Arial, Helvetica, sans-serif fontSize: 14px
lineHeight: 1.5 label: fontFamily: Graphik, Arial, Helvetica, sans-serif
fontWeight: 600 fontSize: 0.86rem letterSpacing: 0.02em figure: fontFamily:
Graphik, Arial, Helvetica, sans-serif fontWeight: 700 fontSize: 1.5rem
fontFeature: tnum mono: fontFamily: Source Code Pro fontFeature: tnum rounded:
md: 8px full: 9999px spacing: xs: 4px sm: 8px md: 12px lg: 16px xl: 24px
components: button-primary: backgroundColor: "{colors.primary}" textColor:
"{colors.on-primary}" rounded: "{rounded.md}" button-danger: borderColor:
"{colors.error}" textColor: "{colors.error}" rounded: "{rounded.md}" panel:
borderColor: "{colors.border}" rounded: "{rounded.md}" padding: "{spacing.md}"
table-header: backgroundColor: "{colors.table-header}" ---

# FAQ Generator

## Overview

The console is an industrial ledger for one or two operators. Every number
on a page can be followed to the rows behind it, and both are on screen
together. It runs the seven-stage pipeline (upload, parsing, chunking,
extraction, topics, questions, assessment) and audits what each stage wrote.
Pages are Operate mode; the "How it works" folds are Read mode.

- One page per stage, all laid out the same way.
- Figures first, then the controls, then the table the figures count.
- Purple marks structure only: section labels, figures, the sidebar.

## The fold

At 1440x900, a listing page shows its table, with at least eight rows,
before any scrolling.

| Band | Budget |
|---|---|
| Header: page title, product name, rule | 56px or less |
| Overview: one strip of figures (Assessment: two rows, the kind and disagreements filter, then the figures) | 72px of content or less |
| Service: queue verbs and state line, then its three folds in one row | 120px or less |
| Search and filters: search, filters, pager | one row, two on Questions |
| Table | everything left |

Measured on 2026-10-01, the table panel starts at 471px on Passages, Facts
and Topics, 535-538px on Assessment and Questions, and 572px on Documents.

Content shown on request (a picked row, an open fold) may push below the
fold. Content shown on opening may not.

## Colors

One purple accent sits on neutral grounds. Red marks deletion only.

The theme is light by default and follows the toolbar menu or the OS for
dark. Every pair in `styles.css` uses `light-dark()`.

## Typography

The font stack is Graphik, falling back to Arial. Ids and digests use Source
Code Pro, which ships with Streamlit. Figures use tabular numerals; the base
size is 14px (`theme.baseFontSize`), and every rem-based measure scales from
it.

## Layout

One column, at most 1320px wide, sits beside the sidebar. Sections are
bordered panels with the label inside. A panel never holds another
bordered box.

## Elevation & Depth

None. Hairline borders and the table-header tint are the only layering.

## Shapes

All corners use one 8px radius (`theme.baseRadius`). Only the queue spinner
is round.

## Components

| Component | Rule |
|---|---|
| Panel | `page.panel`. Label 0.95rem/600 in purple, then content, about 8px apart. |
| Figures | `page.stats`. Unbordered inside the Overview panel, each with a tooltip. |
| Queue row | `stage.service`, `pipeline.panel`. Verbs sized to their labels and a muted state line. Disabled verbs stay readable and give the reason in their tooltip. |
| Folds | `page.folds`. Analysis, How it works and Configuration share one row while closed. An opened fold stacks all three. |
| Search and filters | `catalog.find`. One panel: search box first and widest, pager last. |
| Table | `page.table`. A Streamlit dataframe with single-row selection. |
| Deletion | `stage.removal`. A red panel. The first click arms it and a separately labelled second click acts. |

## Do's and Don'ts

- Do: measure each changed page at 1440x900.
- Do: put new content in an existing fold or behind a selection.
- Do: give every figure a tooltip saying what it counts.
- Don't: add a second accent, a shadow or a gradient.
- Don't: nest a bordered box in a panel.
- Don't: size a button by column width.

## Motion

Motion is minimal. The queue spinner runs while a stage has work in flight
and slows under `prefers-reduced-motion`.

## Decisions Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-10-01 | Initial design system | Tables sat 74-255px below the fold on seven of eight pages. |
| 2026-10-01 | 14px base, merged header, one Search and filters panel, unbordered figures | Recovers the vertical space the fold rule needs. |
| 2026-10-01 | Labels at 0.86rem, section labels at 0.95rem | At a 14px base, 0.7rem labels came out under 12px. |
| 2026-10-01 | A service's folds share one row, with Analysis in the service panel | Three stacked folds cost about 90px on every page. |

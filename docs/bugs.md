# Known bugs

The defects the pipeline still has. Each one is accepted: its entry gives the
symptom, the measured effect, why it stays, what a cure would cost and what
would reopen it. [changelog.md](changelog.md) lists what each release fixed,
newest first.

The QA pass of v0.5.3 brought every open item to an end state and accepted
133 of them. The deep QA pass of v0.5.5 accepted 25 of its own items. This page holds the 158 accepted items, by
category:

| Category | Items | Meaning |
|---|---|---|
| [Failed bar](#failed-bar) | 82 | Designs were built and measured against a bar written beforehand, and none passed. 19 are fixes withdrawn in v0.5.3 and 8 fixes withdrawn in v0.5.5 |
| [Cost](#cost) | 65 | A cure needs a model call per row, a new service, a migration or a rework larger than the effect |
| [Not measured: budget](#not-measured-budget) | 6 | A cure changes what is written and needs a model arm that v0.5.3's model budget did not cover |
| [Domain-specific](#domain-specific) | 3 | Only a rule fitted to one corpus would cure it |
| [Upstream](#upstream) | 2 | A dependency must change first |

Within a category, entries run in pipeline order: parsing and passages, facts
and topics, questions and the release, then the platform. Each carries its
register id: `C-` and three digits for the final review of 2026-10-22, `N-`
for the QA pass of 2026-11-01 (`N-001` to `N-083`) and for the deep QA pass
of v0.5.5 (`N-101` to `N-157`), and `K-001` for one entry with no other id.
Older ids follow in brackets where an earlier review named the item.

Figures come from hand reviews of full runs of the *Laws of the Game
2026/27* (football rules), German and English, and from one earlier run over
16 certification syllabi. Replays and arms ran on two corpora, each German
and English: the football corpus (30 PDFs of the v0.5.1 build) and the shop
corpus (50 consumer-information PDFs). The fact replays of v0.5.5 also read a
third copy, the football rules in German and English with facts only, so they
cover 20,888 stored facts. [measurements.md](measurements.md)
holds the runs' own figures. "Usable" means a reviewer verdict of good or
minor. Reviewer verdicts are model judgements, accurate to about five points.
"Release rows" are rows of the release of 2026-10-13 unless another run is
named. "n" counts the rows a figure reads.

## Failed bar

Each design named here was built, measured against a bar written before the
measure, and taken out. A tightening may refuse at most 35% usable or correct
rows. The 19 fixes withdrawn in v0.5.3 failed a replay, an arm, a Nightly
run or the third round of review; their entries give the replay's, the
arm's, the run's or the reviewers' numbers. The 8 withdrawn in v0.5.5 failed
a passage arm, a fact replay, the reviewers' probes or the third round of
review, and their entries say which.

### C-007: Restored regulation clauses can read worse

v0.5.2 restored the clauses that the converter's bookmark pass turned into
headings: 52 of 54 such items across two regulations had reached no passage.
Of the 33 passages the restore changed, 3 read worse (bar 2): a wrong section
path or a lost lead-in.

- Why accepted: 52 clauses reaching no passage was the larger loss, so the
  restore shipped. The one generic repair, carrying a restored clause's
  lead-in to its sub-items, misfired on 33 of 90 bank-terms probes and was
  withdrawn in v0.5.2.
- Cure: a lead-in rule that holds on bank layouts.
- Reopens: a carry design that passes the passage bar and the 90 probes.

### C-047: A list cut from its lead-in

A lead-in cut from its list moves into the list's passage when both fit the
budget, otherwise into the heading trail. Only a paragraph or a list item
ending in a colon is taken for a lead-in. 32 passages on the v0.2.2 and
v0.3.0 rebuilds still lost a lead-in, so their items lose the context they
depend on. A page join recreated one budget cut (passage 1755 into 1756).

- Why accepted: two designs were withdrawn. In v0.5.2 a list item ending in
  a colon headed its sub-items across a page break: it restored 5 passages
  but lost an outer list's lead-in when sub-items were cut. In v0.4.4 a
  lead-in set as a heading was read as a paragraph: it reached sibling
  sections it does not introduce. Most cases continue at depth 0 after a page
  break, which no rule reached.
- Cure: a carry that keeps outer lead-ins, measured by the passage bar.
- Reopens: such a carry passing the passage bar.

### C-097: Table passages with a major defect

25 of 50 labelled table passages carry a major defect.

- Why accepted: reading a table's section path from a heading absorbed into
  its first row (v0.5.2) left the share at 0.50 of 50, against a bar under
  0.24.
- Cure: a table reading that halves the share, measured on labelled tables
  of both corpora.
- Reopens: such a reading.

### C-120: Nested lists flattened when every item wraps

Nested lists are flattened when every item wraps, so a sub-condition reads as
a sibling rule.

- Why accepted: measuring one line by the document's shortest list item
  (v0.5.2) fixed 4 of 14 tagged cases, where 9 were needed. Its numbering
  guard read `(3)`, `3.` and `3)` as one numbering, and its fine-print
  threshold failed at +20%.
- Cure: a nesting rule that holds over ±20% of its threshold.
- Reopens: such a rule passing the passage bar.

### C-127: Picture pages named as unread text

The parse note names a picture page with a title as text it could not read:
14 of 30 football documents, 29 pages.

- Why accepted: two designs were withdrawn. In v0.5.2, counting a picture
  page as unread only with no body text left a rotated scan unnamed. In
  v0.5.3, counting the words outside the top and bottom margins as body text
  cut the named set to 7 documents and 11 pages (shop 0 before and after).
  Round 1's reviewers found that a scan stamped with a watermark across its
  body was then no longer named. With a watermark rule added, moving its
  limits by 20% named 7 documents and 14 pages at one end and 8 and 20 at
  the other, against the bar's "the same named set". The lead withdrew it.
- Cure: a body-text reading whose named set holds over ±20% of its limits
  and still names a stamped scan.
- Reopens: such a reading.

### C-140: Text a converter nests in a picture reaches no passage

Text a converter nests inside a picture reaches no passage, so a sentence set
in a box drawn as a figure is never asked about. operations.md's Production
deployment asks for it to be measured on the shop corpus before production.
(BL-D4-picture, FIX-R165, QAB-preprocessing-12.)

- Why accepted: writing clause-like picture text into the passage made 5 of
  26 changed passages read worse in v0.5.2 (bar 2). In v0.4.0, of 171
  passages changed, about 90% of the added lines were diagram labels and
  about 8% page numbers. About 90% of picture text on the football PDFs is
  labels.
- Cure: a reading that tells a boxed sentence from a label or help-box
  boilerplate on both corpora.
- Reopens: a design that changes passages with at most 2 worse.

### C-160: A contact line in the foot is dropped

A foot line holding the running name and a bare phone number
(`Musterbank AG | 0800 123 456`) is dropped as page furniture, so the hotline
number reaches no passage. Neither corpus has such a line.

- Why accepted: keeping a foot unless its other fields are page numbers
  (v0.5.2) kept a running foot printing a date in 12 of 20 probes.
- Cure: a foot reading that tells a contact field from a date or edition
  field.
- Reopens: a corpus that loses a contact number this way.

### C-182: Page numbers stand as passages on two-page spreads

On PDFs that print two pages a sheet, some page numbers stand as passages of
their own (`1`, `3`, `9` in two football spreads), because page-number
offsets are read per PDF page.

- Why accepted: reading offsets per printed page (v0.5.2) removed them, but
  also read single pages printing a page and a sheet number as spreads, and
  dropped margin figures such as 25.
- Cure: a reading that tells a spread from a page with two numbers.
- Reopens: such a reading.

### C-282: A second tier under an empty table label joins the row above

In a fee table, a second tier written under an empty first cell merges into
the row above, so two fees fuse into one row and one table fact. Neither
corpus's tables were traced to it, though bank price lists use the layout.

- Why accepted: no rule tried separates it from a wrapped row that opens on
  a bracket or a German noun.
- Cure: a reading of table wraps that does not rest on letter case.
- Reopens: such a reading.

### C-284: Diagram labels printed in view are passage text

Illustrations print their captions as text, and the chunker keeps all body
text. The parser drops clipped text only where the visible page lacks the
same character in the same place (v0.3.6). The v0.3.0 rebuild held 17
passages with diagram labels and 10 with clipped text, and 6 released
questions cite passages that still carry hidden labels. A label printed in
view is body text.

- Why accepted: the one rule tried for picture text, keeping only clause-like
  text, made 5 of 26 changed passages read worse in v0.5.2 (bar 2).
- Cure: a reading that tells a label from a sentence inside a figure.
- Reopens: with C-140.

### C-368: Section paths are wrong at scale

Section paths are wrong on 0.072 of passages on the v0.5.1 build, mostly from
the converter's heading levels. The workbook shows no section, so a wrong
path reaches a tester only through a heading word written into a fact.
(FIX-R40, FIX-R10: parser passes for a two-column page and for a title that
re-levels chapters, shown only on synthetic fixtures.)

- Why accepted: every heading setting of the converter moved 200 or more
  right paths to fix about 160 wrong ones. v0.5.2 fixed the letterhead trails
  only.
- Cure: a level ranking, numbering first, measured by the passage bar.
- Reopens: such a ranking passing the bar.

### C-419: Only a drawn stroke of 2 pt or more strikes text out

Only a drawn horizontal stroke of 2 pt or more is read as striking text out.
A full stop struck by a shorter stroke, or words struck by a font attribute
as in tracked-change exports, stay as current text. The 38 struck passages
of the football corpus are all drawn strikes, and all are removed.

- Why accepted: a relative stroke length read a 1.5-pt mark over a decimal
  comma as a strike.
- Cure: a strike reading that leaves marks over numbers alone.
- Reopens: a corpus that marks superseded wording another way.

### N-002: A line-end hyphen is dropped before the repair reads it

The converter drops a hyphen at the end of a printed line before the
project's repair reads it: *Online-Händler* becomes *OnlineHändler*, and
*14-30* becomes *1430*. On the 80 PDFs, 65 football and 31 shop forms are
fused this way.

- Why accepted: in v0.5.3 an assembler kept the hyphen and the repair closed
  `x- Y` where the next line opens on a capital or a digit. The passage arm
  held (436 of 1,959 football and 39 of 545 shop passages changed, every
  letter kept, fused forms 65 to 4 and 31 to 12). The third review then
  found that a formula region with no text, which the converter passes as an
  empty list, raised in the assembler, so a whole document was refused where
  v0.5.2 parses it. By the third-round rule the fix was withdrawn with N-014
  and N-041. The re-run after the withdrawal equals v0.5.2 on all 80 PDFs.
- Cure: the same converter change with an empty region guarded, and its
  passage arm and three rounds of review again.
- Reopens: that change passing its third review.

### N-014: A hanging hyphen before a coordinator is mended into one word

A hanging hyphen before a coordinator the joining table lacks is mended into
one word: *Kreditrespektive*, *firstthrough*, *créditet*.

- Why accepted: its fix completed the table's German and English rows and
  marked the converter's line breaks, inside N-002's change, and was
  withdrawn with it.
- Cure: as N-002.
- Reopens: with N-002.

### N-041: The broken-word mend lists its letters by hand

The broken-word mend lists its letters by hand (A to Z and the German
umlauts). In French or Polish one word broken at a line is mended, and the
next, broken beside an accented letter, stays broken.

- Why accepted: its fix read letters by Unicode class inside N-002's change,
  and was withdrawn with it.
- Cure: as N-002.
- Reopens: with N-002.

### N-103: A list item cut at a page break is not joined

A list item that a page break cuts mid-sentence stays two items: the
converter makes its rest a marker-less item of the next page's list, and the
page join takes only a paragraph as the second half. The first item ends
mid-sentence and the rest prints under a dash at level 0, so a fact's
evidence is half a rule. The four converted football PDFs hold 7 items cut
this way, and stored build passages 4000 and 4010 show it.

- Why accepted: withdrawn in v0.5.5. Its fix joined such a rest to its item.
  The blind reader read its 9 added football joins as printed, against v0.5.4
  worse in all 9, with the shop corpus unchanged, and one reviewer passed it.
  In the third round the other reviewer found a new wrong join: two separate
  bullets without markers on a two-column page were fused at the column
  break, because the rest's edge was read against the page's leftmost item.
  A medium finding after the third round withdraws a fix. Its three commits
  were reverted, and the helpers N-102 uses stay.
- Cure: a join that reads a rest's edge against its own column.
- Reopens: such a join, keeping two items without markers at a column break
  apart, passing the passage arm of both corpora and a blind reading.

### N-105: A body paragraph that repeats a running foot reaches no passage

A body paragraph whose text equals a running head or foot is moved to the
furniture layer wherever it sits on the page, so a contact line that the foot
also prints reaches no passage. C-160 is the foot's own line; this is the
body's copy of it, dropped by another rule. The stored corpora hold no such
paragraph in the body area: the 4 found all sit in a margin.

- Why accepted: withdrawn in v0.5.5. Its fix took such a paragraph as a
  running item only inside the top or bottom margin of its page. The passage
  arm changed 19 football passages and 0 shop passages, and the blind reader
  found the fix printing as the page in 2 of 19 and reading worse in 11: a
  chapter title that the converter reads as body text and the running head
  repeats moved from the trail to the end of the previous chapter's passage,
  or into a passage of its own under the wrong trail. The bar was that every
  changed passage only gains body text.
- Cure: a rule that keeps a body-area paragraph equal to a running foot as
  passage text, and leaves a title the converter reads as body where v0.5.4
  puts it.
- Reopens: such a rule passing the passage arm of both corpora.

### N-123: A list of short lines in an unconfigured language takes a configured one

A list passage whose items are each under 40 characters, in French, Polish
or Greek, is labelled German or English and extracted by that pipeline,
because the line-by-line reading counts a short line for neither side.
Such a passage should be kept and left unread. Instead the model writes
facts from it, the wrong language's pipeline checks them and reads its
words, which enter that language's topic vocabulary; a re-chunk repairs it
once a fix ships. N-004's fix covered paragraphs only. Not measured on the
stored corpora, which are German and English only.

- Why accepted: withdrawn in v0.5.5. Its fix read a passage of short lines
  joined, through the all-language reading the document gate uses. That
  labelled a French, Polish, Greek, Dutch or Swedish list of short items as
  no language (13 red tests green), and moved 0 of 2,506 passages of the
  passage arm and 0 of 2,790 stored passages at the gate's 0.56, 0.7 and
  0.84. Both reviewers then found German and English lists of food and drink
  loanwords, the shape of a cafe, bakery or menu price list, read as Italian,
  French or Spanish and no longer extracted: 10 of 12 probes for one, and 8
  of 24 lists at 0.7 for the other, against the bar's clause that such lists
  keep their language. The joined reading's confidence does not separate the
  two (loanword lists 0.75 to 0.95, the foreign lists 0.87 to 1.00), so no
  move of the bar cures it.
- Cure: a reading that tells a foreign list of short items from a list of
  loanwords in a configured language, for example from the passage's
  neighbours or the document's other lists.
- Reopens: such a reading passing the 13 tests of v0.5.5 and the reviewers'
  loanword, dish, coffee and place-name lists in German and English at the
  three bars.

### C-015: A fact may drop its sentence's scope

Validation does not check that a statement keeps its sentence's scope. A
fact validates when it drops a restrictive clause, a negation, "only", one
condition of two or most of a list. 8 such facts were confirmed by hand, and
4 questions on them were released. The atomic prompt keeps conditions,
exceptions and *only* in the statement, which lowered the share of facts
dropping a scope word in both languages.

Three checks were measured and none shipped:

| Check | Result | Bar |
|---|---|---|
| Deterministic marker check | Right on 50 of 109 flagged facts (46%) | 80% |
| NLI entailment check | Right on 10 of 60 sampled | |
| Repair reader (v0.5.0), replayed on 2,861 validated facts | Found 52% of drops (bar 50%); 30% of changed facts had dropped scope (bar 80%); 63% of repairs correct (bar 80%); broke 2.0% of complete facts (bar at most 1%) | see left |

Most false flags added the section heading as a situation. One class held
up: a limit stated in a sentence the fact does not cite (0.68 precision, no
harm, about a quarter of the drops).

- Why accepted: every check failed its bar.
- Cure: a reader precise enough to refuse only real drops. A design asking
  only for the limit stated in an uncited sentence is the next step.
- Reopens: a reader passing precision 0.80 and harm at most 1% in each
  language.

### C-021: `unresolved_reference` refuses sound facts

`unresolved_reference` refuses a pronoun whose antecedent sits earlier in the
same statement when a verb-first condition or a gerund puts both in one
clause: 21 of 77 wrong refusals. A pronoun or *dies* pointing into a German
verb-first condition, or an English *this* standing for an *if* clause, is
refused the same way. A German title setting a product before its noun
(*Kreditkarten Bedingungen 2025*) leaves *Diese Bedingungen* refused, a
conservative miss chosen over a misfire. (NEW-extract-nlp-4.)

- Why accepted: six readings freed 47 wrong refusals but also admitted 46 of
  119 sentences that must stay refused, and resolved pronouns no reader
  could. They were withdrawn.
- Cure: coreference over competing antecedents.
- Reopens: a reading that frees them without that harm.

### C-025: Titled headings learn no reference link

Reference links learn only `word number` headings, so a titled heading
(*Article 17 ...*, *§ 5 Kündigung*) links nothing.

- Why accepted: two designs were withdrawn. In v0.5.2 a heading label took a
  title after its number, and read `iPhone 15 Pro` as a numbered section. In
  v0.5.3 a titled heading counted as a label only where its word heads a
  series of two or more numbers including 1 in its document. Its replay
  passed: football links went from 141 to 639 with none lost, shop stayed at
  1, and the bar's 8 product probes learned no word. The first review then
  found that 10 fair series probes (plan, zone, care grade and day series, in
  German, English, French and Greek) each learned a word, and the bridge
  check then refused correct claims in 9 of 10. 3 stored bridges were newly
  refused, all correct.
- Cure: a label reading that tells a document's section series from a
  numbered series of things.
- Reopens: such a reading passing the link replay, the product probes and the
  series probes.

### C-032: Digests change meaning

Digests (summaries and outlines) can change meaning, and read correct only
0.38 to 0.68 of the time.

- Why accepted: a local entailment check (v0.5.2) refused digests of which
  39% to 86% were sound, at every threshold from 0.2 to 0.9 and with two
  models (bar at most 35%).
- Cure: a reader that tells a sound paraphrase from a changed meaning, likely
  a model call per digest.
- Reopens: a check that refuses at most 35% sound digests.

### C-045: Bridge facts that are not bridges

Some bridge facts are not bridges: one of the two passages adds nothing.
(FIX-R7, FIX-R167, BL-D4-extract, BL-B10.)

- Why accepted: three designs were withdrawn. Refusing a bridge that one
  passage adds nothing to (v0.5.2) refused 43 of 189 bridges, 19 of them
  correct (0.44, bar at most 0.35). A judge caught a third of unsound
  bridges, and refusing them would remove questions 55 to 62% usable. The
  bridge test at extraction would refuse about 6 of 16 correct bridges
  against a bar of one, and bridge prompt 8 failed two of eight bars: 22% of
  correct parallel and contrast bridges refused (bar 15%), and 12 of 16
  drift controls repeated (bar 13).
- Cure: a reading of what each passage contributes.
- Reopens: a refusal passing the tightening bar.

### C-050: Glossary definitions and list items under a lead-in get no facts

Glossary definitions and list items under a lead-in get no facts, so they are
never asked about.

- Why accepted: three designs were withdrawn. Reading list passages under a
  lead-in without verbs (v0.5.2) wrote 26 new facts, 12 correct (0.46,
  against 0.73). The best glossary rule read 42 of 43 glossary passages, but
  14% of what it read were cross-references. Of two verbless-definition
  designs (v0.4.4), one admitted index lines and the other dropped
  definitions holding a figure.
- Cure: a reader of verbless definitions that tells a definition from an
  index line.
- Reopens: such a reader passing the arm bar.

### C-061: The cell reader composes nothing from some tables

The cell reader composes nothing from 14 of 50 table passages, and no model
reads them, so their values yield no fact.

- Why accepted: a model fallback on those tables (v0.5.2) wrote 60 facts, 44
  correct (0.733, floor 0.783), with 12 narrowed against at most 9.
- Cure: a table reading that passes the arm bar.
- Reopens: such a reading.

### C-094: The atomic prompt writes the heading into facts as their situation

Atomic prompt 12 writes a passage's heading into some facts as their
situation, about 0.2 points of correctness. Validated facts on the v0.4.0
rebuild read 85.6% correct against 86.7% on v0.3.0, within reader noise.

- Why accepted: three prompts were withdrawn. Prompt 15 (v0.5.2) cut heading
  frames from 51 to 1, but correct facts fell: 48 of 60 against 53 on the
  build, 45 against 55 on shop. Prompt 13 dropped the heading's scope
  (correct 0.917 to 0.793), and prompt 14 wrote 105 heading-as-situation
  facts (limit 59.5). Extraction stays at prompt 12. (FIX-R129.)
- Cure: a prompt that drops the frames without losing correctness.
- Reopens: such a prompt passing the arm on both corpora.

### C-130: A bridge naming its own passage's numbered heading is refused

A bridge that names the numbered heading its own passage sits under is
refused `not_bridging`, even where the passage's text makes that reference.

- Why accepted: freeing such bridges where the passage's text carries the
  label (v0.5.2) admitted 5, of which 3 were correct (bar 3.67).
- Cure: a reading of whether the reference is the passage's claim or the
  document's layout. No design exists yet.
- Reopens: a design that frees them with at most one wrong in five.

### C-158: Dotted clock times are not read as times

Figures are still read wrongly in some spellings: `1.234,567`, `8.30 Uhr`
against `08:30`, and `1000` against a German `1,000`.

- Why accepted: two designs were withdrawn. In v0.5.2 a dotted figure read
  as a clock time took `EUR 12.30` for a time. In v0.5.3 a dotted pair read
  as hours and minutes unless a currency, a share or a unit stood beside it.
  Its replay validated 4 more football facts, but 2 rested on section
  numbers read as times. The first reviewers found 22 of 22 probes (section,
  clause and article numbers, ratios, versions and dates, in German, English
  and Greek) validating a wrong fact that v0.5.2 refuses. Of 490 clock-shaped
  tokens stored, 441 are not times.
- Cure: a time reading that needs a time word or a time context, not just
  the shape.
- Reopens: such a reading that leaves the probes refused.

### C-173: `asserts_nothing` misses a mis-tagged verb

A statement whose finite verb the tagger mis-tags is refused
`asserts_nothing` ("no finite verb").

- Why accepted: reading such a word as a verb where the cited evidence uses
  it as one (v0.5.2) freed 4 of 5 correct facts on football but only 3 of 5
  on shop (3.25 needed, 2 vague).
- Cure: a reading that tells a mis-tagged verb from a vague verbless
  statement.
- Reopens: a design that passes both corpora.

### C-179: A different rule refused as a duplicate

A fact stating a different rule in the same words as a kept fact is refused
as its duplicate, because the check compares statements without their
headings.

- Why accepted: every design admitted mostly restatements. Comparing sections
  admitted 189 facts (45 sound), a different noun 84 (37 sound), and
  embedding with the heading trail freed 19 to 31 wrong refusals but made 71
  to 121 new twins.
- Cure: a reading of what makes two alike statements different rules.
- Reopens: a design that frees more sound facts than it makes twins.

### C-260: Number words read wrongly

A German count written in words can be validated against a different number,
and a number word outside the language's table is read as written. No row of
the v0.5.1 build was affected. (llm-nlp-12, FIX-R164.)

- Why accepted: validating spelled counts anywhere in the passage (v0.4.3)
  validated wrong counts. Reading German count words as units refused 2
  correct facts of 3. The tightening would refuse 5 more German facts, 4 of
  them correct, and orphan 13 questions.
- Cure: a count reading that passes in both directions.
- Reopens: such a design.

### N-009: A fact that flips a figure's sign passes

A statement that flips the sign of the cited figure passes
`unsupported_addition`.

- Why accepted: the v0.5.3 fix kept a minus sign that opens a figure and read
  signed values. Its replay changed 0 verdicts on 13,716 football and 2,838
  shop facts, since neither corpus holds a signed figure. The third review
  found that a sign said in words in the cited text signed the figure as
  written, not its value, and that a space-grouped amount after the sign word
  was not read. *minus 1.000 Euro* against *-1000 Euro*, *minus 0,5 %*
  against *minus 0,50 %* and *minus fünf Grad* against *-5 Grad* were refused
  where v0.5.2 validates them. Withdrawn by the third-round rule.
- Cure: a sign reading that reads spoken signs and grouped amounts on both
  sides.
- Reopens: such a reading passing the replay and the probes.

### N-011: Abbreviated label words name no reference

Headings numbered with an abbreviated label word (*Art. 5*, *Nr. 3*, *Sec.
7*) are no labels, so a bridge naming one is kept and the link pass learns no
reference.

- Why accepted: the v0.5.3 fix allowed a full stop after a label word. The
  stored corpora hold no such heading (0 of 525 bridges and 0 of 2,346 links
  change), so its bar passed on no evidence. The third review found that a
  one-letter heading with a full stop (A.2, B.2, P.2, S.2) became a label:
  *p. 2* and *S. 2* linked to P.2 and S.2, *A4 paper* and *level B2* were
  refused `not_bridging` where v0.5.2 validates them, and 11 of 14 probes in
  unconfigured languages linked a preposition or a conjunction.
- Cure: a label reading that needs more than a letter and a full stop.
- Reopens: such a reading passing the series and letter probes.

### N-018: Back-pointing words leave no unresolved reference

*The fee mentioned above*, *the listed fees*, *the previous rule* and *the
remaining accounts*, and their German forms, leave no unresolved reference.

- Why accepted: adding the back-pointing participles and adjectives to the
  pointing table newly refused 31 validated facts, of which 22 were correct
  (71%, bar 35%). The same words also mark sentences that point at nothing
  earlier in the text, such as a list on another document or a place above.
- Cure: a reading that tells a word pointing back in the text from the same
  word used otherwise.
- Reopens: such a reading passing the 35% bar.

### N-050: A fact that changes an amount's currency passes

A fact that changes the currency of an amount (5 USD for 5 EUR, $5 for €5, 5
Franken for 5 Euro) is validated. Whether a code counts depends on how each
language's tagger tags it.

- Why accepted: the v0.5.3 fix read every token a currency check accepts as
  a currency. The third review found that any capitalised word that is also
  an ISO code (AMD, PHP, CUP, AED, TOP, ALL), the region *Franken*, and
  *pounds* or *Pfund* from another sentence were judged a swap, refusing
  sound facts v0.5.2 validates in German, English and Greek. Its weight words
  were a German and English list with no language key.
- Cure: a currency reading that needs the token beside the figure and keys
  its words by language.
- Reopens: such a reading passing the replay and the probes.

### N-059: A space-grouped count reads as two figures

A count or measure grouped by a space (*8 000 Zuschauer*, *1 250 lx*, *12 000
customers*) is read as two figures: the sound fact in another spelling is
refused, and *12 customers* is validated.

- Why accepted: the v0.5.3 fix read such a run as one figure before a unit
  or noun. The fact replay changed 0 verdicts, and `figures()` changed 15 of
  35,519 texts, all correct. The third review found that the merged count
  left the claim's units, which the question gates read alone:
  `explains()` passed *9 000 Kundinnen* against a passage's 8 000, and *2 500
  Kunden* against 1 500, and `anchored()` turned false on *Gilt das ab 1 000
  Kunden?*.
- Cure: the same reading carried through the question gates.
- Reopens: such a change passing the fact, figure and question replays.

### N-129: A fact that gives the cited figure to another named party passes

An atomic fact that moves the cited fee or period to another party, one its
passage names in an uncited sentence, is validated in every configured
language: *Die Westbank erhebt ... 5 Euro* for a cited *Die Nordbank erhebt
... 5 Euro*, beside an uncited *Die Westbank verlangt keine Gebühr*. An
atomic fact's vocabulary is the whole passage, and the swap guard reads
figures only. Found on synthetic input, not measured on stored rows.

- Why accepted: withdrawn in v0.5.5. Its guard refused, as a swap, a name
  that only an uncited sentence holds, beside a cited name the statement
  dropped. It caught the 3 probe swaps and passed the 20 keep probes, but
  refused a sound lead-in statement that two existing tests pin, and the
  replay of 20,888 stored facts newly refused 23, about 21 to 22 of them
  sound on a reading of each row: an acronym spelled out (ESIS), a
  pronoun's antecedent, a heading's name. The bar was under 20, with at most
  1 sound. No repair within the design tells those from the swaps without a
  word list.
- Cure: a name reading that tells an acronym's expansion or a pronoun's
  antecedent from another party's name, for example through coreference.
- Reopens: such a reading passing the 20 keep probes and the two pinned
  lead-in tests, and newly refusing at most 1 sound row of the 23 the v0.5.5
  replay listed.

### N-135: A cited amount restated as a count passes

An atomic fact that restates a cited amount as a count of something else is
validated: *3 cards* for a cited *3 EUR*, *12 holders* for *12 EUR*. The swap
guard's pass over traded kinds reads only statement figures of a value kind
(a currency, a share, a period), and a count's noun is no asserted unit, so
nothing compares the count with the cited amount. German and English
misfire; French and Greek are refused at parse. Surviving mutants of the
swap guard showed it, and no stored fact does.

- Why accepted: four designs were built and measured offline in v0.5.5, and
  none was applied. Letting every noun kind into that pass newly refused 16
  to 17 stored facts, all sound (*14-tägige Bedenkzeit*, the EUR 100 000
  protection limit, the 5-8 second time frame, Article 10), and 15 of 25 or
  21 of 38 fair probes in two probe sets. A narrower variant refused 5
  stored facts, all sound. The narrowest count readings refused no stored
  fact and kept the other fair probes, but refused a currency written in a
  word its language's table lacks (*50 francs* for CHF 50, *100 Kronen* for
  SEK 100, *200 zlotys* for PLN 200, *500 Yen*), whose only cure is a
  currency-name vocabulary, the shape N-050 was withdrawn for. A replay
  changing 0 stored rows would pass on no evidence, as N-011's did.
- Cure: a count reading that needs no currency-name vocabulary.
- Reopens: a count reading that refuses the six wrong probes (among them 3
  replacement cards for 3 EUR, 12 holders for 12 EUR a year, 3 counters for
  3 weeks and 4 Filialen for 4 %), keeps every fair probe of both sets,
  currencies spelled as words in any language included, stays inert in
  French, Polish and Greek, and passes the fact replay of the three copies.

### N-140: A cited count restated as an amount or a share passes

The mirror of N-135: a statement that gives a cited count's digits to an
amount or a share is validated, as *An additional card costs 3 EUR* for a
cited *Up to 3 additional cards are issued; each costs 5 EUR*, or *10 %* for
*10 products*. The pass over traded kinds compares only figures the cited
text gives beside a value kind. No stored fact shows it.

- Why accepted: the same root as N-135 and the same cure, the count reading
  that N-135's designs failed to give without a currency-name vocabulary.
- Cure: as N-135.
- Reopens: with N-135.

### C-014: Welded two-passage questions pass every gate

Two-passage questions that weld two rules or two subjects under one question
pass every gate. 0.548 of released two-passage questions are usable (n 126),
against 0.841 overall, so they stay a slice to report apart.

Candidates in one document are ranked by likeness, and a second passage is
offered only where its closest fact is among the topic's closest 2% of fact
pairs (`QUESTIONS_MEETS_SHARE`). The weld share of accepted questions citing
two or more passages fell from 128 of 270 to 33 of 183 (18%), and 17 of 91
released. Likeness cannot separate two rules on one subject. 11 release rows
join two subjects with *and* under one question word and answer each in its
own half, so a chatbot answering one half is neither right nor wrong
(*How should tool metrics and test result communications be handled to
support stakeholders without harming the test team's credibility?*).
`compound` refuses a weld only where it carries two question words.

- Why accepted: four designs failed. A weld judge had precision 0.84 but
  recall 0.43 in German, and 36% of what it refused was usable (bar 35%).
  `asks_one` on the round trip's read (BL-B11) caught 2, then 8, of 35
  welds, half of its refusals usable. The parts reading's `one_question`
  flag (v0.5.2) called all 167 rows one question and caught 0 of 48 welds
  (bar 24). Of the 53 answers with three or more *and* or *und*, no lexical
  reading separates the 11 welds from the 42 sound dense answers.
- Cure: a reading that tells two questions from one dense answer, likely a
  verifier call per two-passage row (about 170 calls a trial).
- Reopens: a design that catches at least 24 of the 48 labelled welds with at
  most 35% of its refusals usable.

### C-017: The round trip refuses sound keys

The round trip refuses German derivations (*eine Verwarnung* against
*verwarnt*, question 3865), unit abbreviations and list keys: 74 of 105
`not_recoverable` refusals on the v0.3.0 rebuild were wrong, 57 usable,
against 38 of 125 on the v0.2.2 rebuild. `answer_incomplete` also refuses
terse keys and German names the tagger does not mark as proper nouns.

v0.5.5 cures part of the unit abbreviations. In German, as in English, a
figure is now paired with the unit written right after it (N-145), so a key
in *80 cm* or *30 kg* agrees with a recovery that writes the same unit after
the same figure: 12 stored German football keys, and one half of 2
two-part keys, moved from refused to agreed. A value key also asks back its
own lower-case or one-letter unit (N-157), so *5 m* no longer agrees with
*5 mm*, nor *je 10 kg* with *je 10 g*. Newly refused in v0.5.5, where
v0.5.4 agreed, unless the entailment rescue keeps the row on the round
trip: a recovery that spells the unit out, in every form for a key as short
as these and in German and English (*90 Meter* or *90 meters* for *90 m*, *5 metres* for *5 m*), and
one that joins the unit to the next word by a hyphen, in the value form
(*Das 5 m-Kabel* for *5 m*). *10 Kilogramm* for *10 kg* was refused before
too.

- Why accepted: keeping a key that names omitted items unless two are
  missing, with cited figures exempt (v0.5.2), kept 7 of 176 refusals, of
  which only 3 were usable (5.3 needed).
- Cure: a reading of what a key omits that is right more often than the
  gate.
- Reopens: a loosening that passes the replay bar.

### C-018: The entailment rescue scores a bare fragment

When the round trip fails, the NLI rescue scores the bare key, a fragment,
and so rescues few sound keys.

- Why accepted: scoring the question with the key (v0.5.2) rescued 30 rows,
  21 usable (0.70, floor 0.753). Earlier it would have rescued 7 usable rows
  and admitted 9 invalid or major ones. No model (`bge-m3-zeroshot-v2.0`,
  mDeBERTa-v3, xlm-roberta-large-xnli), hypothesis shape or threshold
  rescued more usable than bad rows in both languages without tuning to the
  173 stored rows.
- Cure: an NLI reading of question and key that rescues more usable than bad
  rows in both languages.
- Reopens: such a reading passing the replay bar.

### C-028: Keys naming only part of a list

Keys naming only part of a list can pass.

- Why accepted: holding every list-form key to the cited list's item count
  (v0.5.2) would refuse 385 accepted keys, 328 of them usable (0.85, bar at
  most 0.35). Reading such a key as incomplete (v0.4.3) refused 3 German
  rows, 2 of them usable. (FIX-R24.)
- Cure: a reading of which list a question asks for.
- Reopens: a tightening that refuses at most 35% usable rows.

### C-030: Unanswerable slots written beyond what the release takes

With a fixed `QUESTIONS_RELEASE_SIZE` the unanswerable share can end a row or
two in a thousand over `QUESTIONS_RELEASE_UNANSWERABLE`.
`QUESTIONS_UNANSWERABLE_SHARE=0.30` writes three times what the release
takes, at about USD 0.021 an unanswerable slot on link U against about USD
0.0086 for an average slot.

- Why accepted: capping inside the draw (v0.5.2) kept the same rows offline
  but broke two release invariants under property tests.
- Cure: a cap that holds on every draw path without breaking thread
  wholeness. Lowering `QUESTIONS_UNANSWERABLE_SHARE` saves the calls today.
- Reopens: such a cap.

### C-031: Distant-from-document phrasing entered the default at its bar

The distant-from-document phrasing entered the default at exactly its 0.80
conformance bar, and nothing after writing checks distance. About 300 of 426
released distant rows use the document's own words (held 0.410 in German,
0.633 in English).

- Why accepted: the v0.5.3 fix relabelled a distant row as similar when the
  share of its words the cited passages carry (held) passed a bar. Over 230
  labelled stored rows (football 150, shop 80), the football rows that stayed
  distant conformed 0.39, 0.36 and 0.33 at held bars of 0.56, 0.70 and 0.84,
  against a bar of 0.80; shop read 0.89, 0.89 and 0.82. Held does not
  separate them: 9 distant rows conform at held 0, and 66 that do not sit at
  a median held of 0.75.
- Cure: a reading of distance other than shared words, measured on labelled
  rows of both corpora.
- Reopens: such a reading reaching conformance 0.80 on both.

### C-035: Compound halves get no entailment rescue

A compound question's halves are checked by word recall without the
entailment rescue a single key gets, so sound compounds are refused, about 12
per 1,000 written.

- Why accepted: running the rescue on the failing half (v0.5.2) admitted 18
  of 68 refusals, 13 usable against 13.03 needed. The same rescue failed on
  whole keys (C-018).
- Cure: a rescue that passes on whole keys first, then on halves read in
  full.
- Reopens: with C-018.

### C-037: Released questions that read two ways

Some released questions can be read two ways, or their key answers another
reading: 7% of released rows were unusable as ambiguous on the final review.

- Why accepted: writer prompt 32 (v0.5.2) passed the arm bar on both corpora,
  which decides a change to what is written, but its own ambiguous tag went
  from 2 to 5 per 60 on the rulebooks. It shipped, confirmed on 2026-10-26.
- Cure: a writer or gate change that lowers the ambiguous tag.
- Reopens: such a change that does not fail the arm.

### C-038: Questions that need the document to make sense

Some released questions need the document to make sense (*in den Angaben*,
*this section*).

- Why accepted: writer prompt 32 (v0.5.2) lowered the not-standalone tag from
  5 to 3 per 60 on the rulebooks, short of its own bar, while passing the
  arm on both corpora. It shipped, confirmed on 2026-10-26.
- Cure: a change that reaches the bar.
- Reopens: such a change that does not fail the arm.

### C-044: Released keys the cited passages do not support

Some released keys are wrong or unsupported by the cited passages: 68 of
1,549 labelled accepted rows.

- Why accepted: a local entailment check refusing low-scoring keys (v0.5.2)
  refused rows 84% to 89% usable at every threshold (bar at most 35%).
- Cure: a reader that finds the bad keys without refusing sound ones.
- Reopens: one passing the tightening bar.

### C-046: The comparison gate refuses sound comparisons

`_contrasts` in [`gates.py`](../backend/question_generation/gates.py) splits
an answer at the seam between the two subjects the question names. A sound
comparison whose axis only the question names is refused (rows pinned as
expected failures). On the v0.3.0 rebuild 52 of the 62 `wrong_type`
refusals of comparisons were wrong, 37 of them usable, against 18 of 70 on
the v0.2.2 rebuild. Comparisons are nearly absent from the release.

- Why accepted: splitting at another seam (v0.5.2) admitted 78 rows, 28
  usable and 12 invalid (floor 0.751). Reading the two sides by order and
  parallel structure freed 43 rows that are 67% usable, under the pool's
  70%.
- Cure: the weld check's content reading (C-014).
- Reopens: a loosening that passes the replay bar.

### C-049: The release reads no quality signal

The draw reads only answerability, band, kind and thread. It drains any
bucket short of its quota: all 22 aggregations were released, 3 invalid.
Confidence quartiles give 46% to 58% usable, and ordering by confidence
would raise the release from 49% to 52% usable.

- Why accepted: the writer's confidence separates usable rows with AUC 0.565,
  against a bar of 0.65. Ranking unanswerable questions by evidence failed
  (C-060).
- Cure: a quality signal per row.
- Reopens: a signal reaching AUC 0.65.

### C-052: Space-grouped amounts in explanations

`explains()` does not read space-grouped amounts the way the passages' reader
does: a wrong one can pass, only one group is read, and a currency in
brackets after the amount (`12 500 (EUR)`) reads as two figures. No stored
text holds the bracketed shape (0 of 30,808). (QA-questions-1, -4.)

- Why accepted: two designs failed. Reading a space-grouped amount as one
  figure in every reader (v0.4.3) failed because a claim's figures and a
  passage's were read by two readers that fold the amount differently. In
  v0.5.3, `explains()` read both through the one figure reader. Over 1,838
  stored accepted rows with an explanation, 2 verdicts changed, both newly
  refused: a correct derived total (usable) and a wrong one (unusable). 1 of
  2 usable is 0.50, against at most 35%.
- Cure: a reading that tells a sound derived total from an invented one
  (C-421).
- Reopens: such a reading passing the replay.

### C-060: Unanswerable questions the passages answer

76 of the 158 accepted unanswerable questions of the 2026-10-13 run were
answerable, 8 of the 24 released ones. On the v0.5.1 build, 13 of 128
released unanswerable questions were answered by the corpus and 11 were
invalid. The `settles` verifier judgement (`make questions-rejudge` applies
it to stored questions) refuses 29 of the 76 and 3 of the 82 sound ones
(precision 0.91, agreement 0.68, `azure/gpt-4.1`). It still leaves about half
of the answerable ones as settling nothing: false-omission rate 0.53 in
German and 0.46 in English, against the 0.15 a release can carry.

v0.3.0 to v0.4.5 released none (`QUESTIONS_RELEASE_UNANSWERABLE=0`). v0.5.0
releases up to 0.10. On link U's calibration 19 of 60 kept out-of-corpus rows
and 20 of 60 base rows answered after all
([measurements](measurements.md#unanswerable-kinds-v050)), so up to about a
third of released unanswerable questions test a chatbot for saying no to a
question it should answer. `0` releases none.

- Why accepted: quoting, a fused probe of twenty passages, showing the writer
  more passages and a second model (0.39 and 0.34) did not close it. The
  unanswerable writer's reading (settles prompt 7) flagged 4 of 20 answered
  drafts. The writer returns no evidence of why its question is open on
  about 61% of drafts. Drawing silenced unanswerable questions last (v0.5.2)
  left 12 bad rows of 130 either way; ranking them by their evidence left
  0.12 in English against at most 0.10.
- Cure: release only questions a person confirmed, or write unanswerable
  slots as reason questions only. Both are open decisions.
- Reopens: a reading that keeps answered rows under 0.10 in each language.

### C-062: The about guard blocks the rescue on paraphrased questions

The about guard blocks the entailment rescue on paraphrased questions.

- Why accepted: widening its vocabulary to the section path, surface forms
  and earlier turns (v0.5.2) rescued 12 rows, 6 usable (0.50, 9 needed).
- Cure: a rescue that passes on whole keys first (C-018).
- Reopens: with C-018.

### C-063: A re-run topic pays for the same refusals again

A re-run topic replays the same plan over the same unspent facts and pays for
the same refusals.

- Why accepted: the v0.5.3 fix dealt last the facts a deterministic gate had
  refused, and seeded the plan with the questions a topic already holds. Its
  bar was that a first run stays unchanged. The queue credits a question to
  the topic of the passage it cites, not the topic that wrote it: 453 of
  3,885 football questions, and 35 to 38 of each shop snapshot's 221 to 235,
  cite only another topic's passages. So 23 to 32 of 41 football topics
  would start a first run as already asked. The refused-fact flag reads the
  same way, and its query took 27.5 s against 1.9 s for a 40-topic drain on
  12,000 facts. Withdrawn by the third-round rule.
- Cure: a queue that credits a question to the topic that wrote it, then the
  same plan change.
- Reopens: such a change that leaves a first run unchanged.

### C-116: The judge agrees with reviewers' labels near chance

The opt-in judge agrees with reviewers' usable labels at kappa 0.18, so its
verdicts are no quality estimate. It approves about 90% of questions that
reviewers found 62% to 69% usable, and the correction by reviewers' labels
(`make diversity LABELS=`) narrows a floor's intervals by under 3% with this
judge. The workbook says its counts are not a quality estimate. (BL-B15.)

- Why accepted: judge template 6 in v0.5.3 showed the key, the cited
  passages and the question type. On the 200 labelled judged football rows it
  reached kappa 0.238 (95% interval 0.085 to 0.380, bar 0.40), and on 60
  labelled shop rows 0.207 (interval -0.078 to 0.487, bar 0.30). The old
  template's stored verdicts read 0.178 on the same 200 (0.026 to 0.322).
  The trial cost USD 3.23 over 1,540 calls.
- Cure: a judge template or model calibrated against reviewers' labels on
  both corpora.
- Reopens: a template reaching kappa 0.40 on football and 0.30 on shop.

### C-122: A settles quote with `[...]` or a passage label reads as silent

A settles verdict whose quote holds `[...]` or a passage label is read as
silent, so some answered unanswerable questions are kept.

- Why accepted: splitting quotes at those marks (v0.5.2) newly refused 7
  rows, 4 of them usable (0.57, bar at most 0.35).
- Cure: a quote reading that refuses mostly answered rows.
- Reopens: such a reading passing the tightening bar.

### C-126: A two-item key read as a value

A two-item answer joined only by *and* or *und* is read as a value and never
checked for completeness: 8 accepted keys on the v0.3.0 rebuild, such as
question 3402. A comma- or semicolon-separated pair with no verb is read as a
list.

- Why accepted: in v0.5.3, with N-026, a key's items were counted from the
  parse's coordination. No stored round-trip recovery exists, so the cited
  facts' statements stood in for it, a crude bound since statements are
  wordier than a key. Over 4,569 stored questions, 164 rows changed form to a
  list and 64 were newly refused `answer_incomplete`. Of the 43 accepted
  among them (37 football, 6 shop), 35 were usable, 4 unusable and 4
  unlabelled: 0.90 of the 39 labelled, against at most 0.35. Holding list
  keys to the cited list's length (v0.5.2) failed the same way (C-028).
- Cure: the same count, replayed on stored round-trip recoveries, which a
  build has to record first.
- Reopens: such a replay refusing at most 35% usable rows.

### C-143: Near-twin questions

12 release rows were spare twins. The duplicate bar depends on what two
questions cite: a shared fact refuses at `QUESTIONS_DUPLICATE_SHARED_COSINE`
(0.88), a shared passage at `QUESTIONS_DUPLICATE_COSINE` (0.93), a different
question word raises the bar, and an answerable question is never the
duplicate of an unanswerable one. Twins that share only a passage and sit
below 0.93 still pass. They are pinned as expected failures in
[`test_question_verdicts.py`](../tests/regression/test_question_verdicts.py).
The release asks the verifier about each question's nearest neighbour and
keeps one of each pair it says want one answer. The v0.3.0 release still
held 19 twin groups (43 rows). The shared-fact bar also refuses sound
follow-ups (12 on the v0.3.0 rebuild, all wrongly).

- Why accepted: the closest cosine rule would reject 26 usable questions.
  Putting near questions to the same-answer read (v0.5.2) kept 22 of 50
  refusals, of which 15 were true duplicates.
- Cure: a design that frees wrongly refused follow-ups without admitting
  duplicates.
- Reopens: such a design.

### C-145: Questions naming a label or person no cited passage carries

About 0.6% of accepted answerable questions (8 released rows on the v0.5.1
build) name a label or a person no cited passage carries, or carry writer
meta-text.

- Why accepted: a table of the writer prompt's labels and a check for a
  person the passages lack (v0.4.3, BL-B8) refused 3 new rows, 2 of them
  usable. The check also refused an asker naming themselves in a premise.
- Cure: a reading of what the passages name that does not misfire on
  premises.
- Reopens: a 60-row arm reading more than 3 such rows.

### C-147: The written-count gate refuses a true count

A true count that only equals the number of facts cited, because each fact
states one item, is refused (*zwei Lernziele*, question 4255). The exemption
for stated counts reads the cited statements, not the cited passages. On the
v0.3.0 rebuild 4 of the 28 `malformed` refusals were this, all usable.

- Why accepted: keeping such a count where it counts a list (v0.5.2) cleared
  0 of the 5 usable refusals. A second design cleared 3, of which 2 were
  invalid.
- Cure: a reading of the cited passages that clears them without admitting
  invalid rows.
- Reopens: such a reading.

### C-149: `restates_question` refuses a sentence key around a one-word answer

`restates_question` reads a key written as a sentence around a one-word
answer as adding too few words: 9 of 24 such refusals on the v0.3.0 rebuild
were wrong, 8 usable.

- Why accepted: letting a non-why key pass on any new content word (v0.5.2)
  freed 13 of 17 usable football rows but only 3 of 5 on shop (3.33 needed),
  and it misfired in French and Spanish.
- Cure: a reading of the answer word inside an echoed sentence that holds in
  every language.
- Reopens: a design that passes both corpora.

### C-151: A count of one passage's list is stored as an aggregation

A count of the items of one passage's list is asked and stored as an
aggregation, so a release's type mix counts it as a two-fact question.

- Why accepted: refusing such counts removed rows 50% usable in v0.4.0, and 6
  of 9 newly refused rows were usable in v0.5.2 (bar at most 35%).
- Cure: a relabel to factoid instead of a refusal, never measured alone.
- Reopens: a relabel design and its replay.

### C-152: `heard()` reads a restating answer as silence

When the verifier answers an unanswerable question with a quote that also
says the question back, the answer reads as silence, so an answered question
can be kept as unanswerable. On the v0.4.0 rebuild it fired 4 times, 3
wrongly.

- Why accepted: drawing silenced unanswerable questions last (v0.5.2) left
  12 bad rows of 130 either way.
- Cure: a reading that tells a restating answer from a real one.
- Reopens: with C-060.

### C-155: Questions on a false premise stay off by default

Questions on a false premise are opt-in, so a default release tests only
refusals of what the corpus does not cover, not the correction of a wrong
premise. `QuestionKind.FALSE_PREMISE` stays named for a later design.

- Why accepted: the kind missed its bars twice: 4 of 20 accepted against 10
  in v0.4.0, and 5 invalid of 60 against 2 on link U in v0.5.0. Writer-side
  fixes ship uncalibrated.
- Cure: a settles step that can say a premise holds in a named case, and a
  probe of the passages near each cited one, both model-side with arms.
- Reopens: that design passing link U's bars.

### C-178: Padded two-passage questions that cite a bridge

A two-passage question that cites a bridge fact keeps both passages even when
one passage answers it, because the bridge rests on both and narrowing would
leave it citing nothing. 56 of 71 padded two-passage questions of the
v0.3.12 pool, and 21 of 37 of the v0.3.0 pool, cite a bridge.
`question_facts` has no passage column. The needs_both check relabels after
writing, and what it leaves, the bridge-cited rows, no writer feature reaches.
Two-passage questions are reported apart (C-014).

- Why accepted: refusing them fails the tightening rule, and making bridges
  stricter (C-045) failed its own bar in v0.5.2.
- Cure: a bridge check that passes its bar.
- Reopens: with C-045.

### C-180: Follow-up gates read ids, not content

A third turn's follow-up gates compare its facts with the root question's
only, and by id rather than content, so a turn repeating the second turn's
fact can pass. No effect on the release's usable share was measured.

- Why accepted: checking against every earlier turn would remove rows 53%
  usable, above the 35% a tightening may remove.
- Cure: a content reading of earlier turns.
- Reopens: such a reading passing the tightening bar.

### C-204: A model outage discards a topic's drafts

When the model becomes unavailable in the middle of a topic, its drafts are
discarded and paid for again on retry, about USD 1.35 a topic on the v0.5.1
build. No topic failed there, and a drain now stops after five model
failures in a row.

- Why accepted: keeping a topic's finished threads (v0.4.3, FIX-R88) was
  withdrawn because the retry duplicated questions.
- Cure: a slot index on stored questions and a migration.
- Reopens: outages that make topic retries a material share of spend.

### C-262: Nothing checks that a nonsensical question makes no sense

The nonsensical unanswerable kind has no check that its question makes no
sense: on link U 13 of 60 were coherent. The kind missed its bars and stays
off by default, so no release carries it.

- Why accepted: the kind's bars failed on link U (v0.5.0).
- Cure: a check of the kind, measured on link U's bars.
- Reopens: such a check that passes.

### C-263: The underspecified kind has no check of its own

The underspecified unanswerable kind has no check of its own: on link U 38
of 60 were plainly answerable. The kind missed its bars and stays off by
default.

- Why accepted: the kind's bars failed on link U (v0.5.0).
- Cure: a by-case check of the kind.
- Reopens: such a check that passes link U's bars.

### C-264: Questions embedded as written, passages case-folded

The answerable-elsewhere probe compares a question embedded as written with
passages embedded case-folded. (FIX-R55.)

- Why accepted: case-folding the question added one answering passage to the
  probe's 20 nearest, under the rule, set beforehand, of at least 2 in a
  language.
- Cure: an offline replay on the 19 labelled census rows, with the local
  embedder and no model call.
- Reopens: that replay bringing in at least 2 a language.

### C-357: Expert, novice and search-query phrasings stay opt-in

The expert, novice and search-query phrasings are opt-in, so a default
release holds none of them. (BL-A-expert, BL-A-short-query,
BL-A-long-query.)

- Why accepted: they left the default in v0.4.3. Expert's conformance was
  0.59, the short query was accepted on 29% to 31% of its slots, and the
  long one had too few rows.
- Cure: a labelled arm per category on a full build.
- Reopens: such phrasings being wanted.

### C-421: `explanation_unusable` refuses a figure in the heading or a derived total

An explanation whose figure stands in its passage's heading, or which states
a derived total, is refused `explanation_unusable`.

- Why accepted: reading figures from the heading trail and exempting computed
  totals (v0.5.2) admitted 28 of 48 refusals, but only 15 were usable (0.54,
  floor 0.751) and 5 were invalid. Smaller structural gates freed rows 4 of
  6 and 2 of 3 usable, under 70%.
- Cure: a reading that tells a sound derived total from an invented one.
- Reopens: a design that clears the floor.

### C-423: The free title rule refuses a question naming a subject title

`leaks_source`'s free title rule refuses a question that names a
subject-titled document's title as a substring. Its 12-character floor flips
the verdict on the shop corpus's subject titles within ±20% (N-061).

- Why accepted: refusing the title only where it is cited as a source (in
  quotes, or after a document noun, v0.5.2) still refused 4 of 7
  subject-naming rows. Leaving a title naming its page's subject to the
  phrasing judge (v0.4.3, BL-B1) admitted 6 invalid rows in 31 (bar 2 per
  60).
- Cure: a reading that frees subject titles while source-citing questions
  stay refused.
- Reopens: such a reading.

### K-001: One gold compound relabelled single

The needs_both check relabelled one gold compound question (row 4392) as
single-passage, because one passage stated every part it quoted.

- Why accepted: reading the citation instead would narrow only 34% of padded
  two-passage questions.
- Cure: a needs_both reading that tells a compound from a padded question.
- Reopens: more compound questions narrowed wrongly.

### N-026: A three-item key with one comma is read as a value

A key *A, B and C* with one comma is read as a value, so a German list, or an
English one without the serial comma, skips the completeness check.

- Why accepted: its fix counted items from the parse's coordination, with
  C-126, and failed the same replay: 35 of 39 labelled newly refused rows
  were usable.
- Cure: as C-126.
- Reopens: with C-126.

### N-028: `leaks_source` reads a service level before a figure as a document

`leaks_source` reads a service level named *Standard* before a figure
(*Standard 3-5 day shipping*, *der Standard 24h-Versand*) as a numbered
document.

- Why accepted: the v0.5.3 fix took the figure for a document number only
  where no unit or range follows it. A unit after a space was never checked
  (*Standard 20 GB*, *Standard 1 TB Tarif*). In the third review, 7 of 14
  German and English twins disagreed, and 10 of 57 service-level probes were
  still read as citing a source, as on v0.5.2. Withdrawn by the third-round
  rule.
- Cure: a document-number reading that reads units after a space, keyed by
  language.
- Reopens: such a reading passing the source replay and the probes.

### N-124: An English question naming one German compound is refused as German

An English question that names one German compound (*How long does the
Gewährleistung last?*, *Kündigungsschutz*, *Bürgeramt*) is refused as
written in German and rewritten, because lingua is 0.94 to 1.0 sure of
German on one such word. N-045's sure reading at 0.9 was measured on product
names without an umlaut. 0 of 3,885 stored football questions trip it.

- Why accepted: withdrawn in v0.5.5 after three review rounds. Reading the
  question without the words its cited facts hold lets the three cases of
  the hunt pass, but each round reopened a refusal the check exists for. In
  round 1 a French, Polish or Greek question copying names and figures fell
  under the 40-character floor and was kept (1,410 of 4,348 stored rows fell
  under it). In round 2, the rest read only where the full text names the
  other configured language, with a 10-character floor, 8 of 38 French
  probes carrying that language's terms were kept. In round 3, the rest's
  pick also read over every language, 11 of 95 refused probes were kept
  where the answer is worded in the facts' language. No stored question
  shows either the defect or the misfires.
- Cure: a language reading that tells a carried name from the question's own
  language, for example word by word against the facts' vocabulary.
- Reopens: such a reading passing the hunt's three cases and every refused
  probe of the v0.5.5 review rounds in French, Spanish, Dutch, Polish,
  Italian, Danish, Swedish and Greek.

### N-126: A German answer opening on a number compound is read as a count

A German answer that names a thing by a number compound
(*Zwei-Faktor-Authentifizierung*, *2-Faktor-...*, *Vier-Augen-Prinzip*) is
refused as the count of its cited facts, where the number equals that count.
The football build stores no such answer.

- Why accepted: withdrawn in v0.5.5 after three review rounds. Exempting an
  answer that opens on a hyphenated number compound from the count rule
  keeps *Zwei-Faktor-Authentifizierung* under a which-procedure question,
  but each round reopened count refusals. Round 1 skipped every number
  compound, so how-many answers *3-stufig* or *Three-stage process* were
  kept. Round 2 exempted only the bare-count arm, and how-often answers
  *3-mal* and *3-fach* were kept. Round 3 took a compound for a thing where
  the tagger reads a noun or its last part is capitalised, and *drei-mal*,
  *zwei-mal*, *2-malig* (tagged NOUN), *3-Mal* and *3-Fach* were kept. The
  German tagger's part of speech for an unknown hyphenated token does not
  tell a counted adverb from a noun.
- Cure: a reading that tells a number compound naming a thing from a counted
  adverb without the tagger's guess.
- Reopens: such a reading passing the hunt's cases and every count probe of
  the v0.5.5 review rounds.

### N-127: Football examples stay in a gate docstring and four test files

Football words and layout stay in a gate docstring and in four unit test
files, and N-058's guard reads backend source only, with a word list that
misses them. Nothing runs differently; N-058 recast such examples elsewhere
in bank, shop and administration wording.

- Why accepted: withdrawn in v0.5.5 after three review rounds. Recasting the
  docstring's and the tests' examples in bank, shop and office text, and
  adding the missed words to the guard, was reviewed three times. Round 1
  left a football measure in a docstring, and round 2 a German twin and the
  corpus's fines schedule. Round 3 found that the recast German range case
  (*Das Regal ist 100–110 cm hoch.* against *110 cm*) no longer tested the
  range rule: on v0.5.4 a German key in cm never agrees with a German
  sentence, so the test passed with the rule removed. That defect is N-145,
  fixed in v0.5.5: a German figure is now paired with the unit written after
  it, as an English one is. The tests and the docstring are v0.5.4's again.
- Cure: a recast in which every test still fails on its mutant, with a guard
  that reads casefolded words.
- Reopens: such a recast, every test failing on its mutant (the range rule,
  the NUM-tag rule, `enumerates`), no football term left in the touched
  files, and the guard reading casefolded words.

### N-035: The 10x sizing test's 95th percentile measures the runner

`make test-perf` holds a corpus ten times the reviewed one to twice the
reviewed one's dedup probe and fact write times. On the CI runner the
single-pass probe's 95th percentile read 1.99x, 16.61x, 2.26x, 11.51x and
2.63x, and passed once, over six Nightlies on one unchanged commit. The
Nightly's Ceilings job runs under continue-on-error, so a miss leaves it
green. C-011, the sizing of the shipped Postgres, is read through this test.

- Why accepted: the v0.5.3 fix ran CHECKPOINT after each load, dropped a
  warm-up, timed 600 probes and 200 writes, and held the median and the 95th
  percentile to 2x. Its bar was three Nightly Ceilings runs on one commit,
  every ratio within 2x and the spread between runs under 1.5x. On
  `d1694ad9` the medians held (probe 1.48x to 1.62x, write 1.14x to 1.25x),
  as did the warm probe (1.26x to 1.45x) and the write's 95th percentile
  (1.19x to 1.40x). The probe's 95th percentile read 2.29x, 9.30x and 1.83x:
  two runs over 2x, and a spread of 5.1x. The fix was withdrawn.
- Cure: time the probe on a runner with fixed resources, or hold only the
  medians to the bar.
- Reopens: three Nightly Ceilings runs on one commit with every ratio within
  2x and a spread between runs under 1.5x.

### N-120: `make backup` writes outside its folder through a key's dot-dot parts

`make backup` writes each object to `DIR/s3/<bucket>/<key>`, so a key with
`..` parts or a leading `/` writes outside the backup folder, anywhere the
operator's user can write, and a restore or verify of a tampered backup reads
the same joined paths from its manifest. It needs write access to the object
store first (C-296). SeaweedFS 4.44 refuses a key with `..`; AWS S3 and Azure
Blob accept one.

- Why accepted: withdrawn in v0.5.5 after three review rounds. Round 1
  checked the keys in backup and verify, and both reviewers found the
  restore half untested and a symlinked `DIR/s3` moving the check's own
  anchor. Round 2 anchored the check on the named folder and refused empty,
  dot and dot-dot key parts, which closed every bypass tried, and a reviewer
  found that a backup into a folder whose `s3` entry is a link copied
  nothing, exited 0 and verified as a match. Round 3 refused such a layout
  with exit 2, exited 1 on a left-out object and read only plain unlinked
  files. That closed it, and a reviewer found two regressions against
  v0.5.4: a Finder `.DS_Store` or AppleDouble file in `DIR/s3` made `make
  restore-backup` exit 2 with no object restored, after its `pg_restore` had
  already replaced the database, and a backup rotated with `rsync
  --link-dest` or deduplicated with hard links restored nothing.
- Cure: a key check that refuses every escaping key and still backs up,
  restores and verifies every folder v0.5.4 handles.
- Reopens: a key check that refuses every escaping key of the three rounds'
  probes (dot-dot, absolute, empty and dot parts, symlinked `s3` or bucket
  folders, manifest buckets) while a backup folder holding Finder or
  AppleDouble files, a hard-link rotated backup and a backup with a
  symlinked `s3` all back up, restore and verify as v0.5.4 does; or an
  object-store adapter, an Azure one, that stores keys with dot-dot parts.

## Cost

A cure exists or can be named, but it needs a model call per row, a new
service, a migration or a rework larger than the measured effect. Most of
these were not seen in either corpus, or touch only time or spend.

### C-146: A sentence cut at a page break after a full verb is not joined

A sentence a page break cuts right after a full verb (*The card costs* /
*€25 a year*) stays two half sentences, because a finite verb can also close
its clause and the tags cannot tell the two apart. No passage of either build
was traced to it.

- Why accepted: no measured effect.
- Cure: a geometry reading of the page join (a last line reaching the right
  margin with no closing mark), measured as a passage change on both
  corpora.
- Reopens: a build that shows such a cut.

### C-168: A failed upload writes no `ingest_events` row

An upload that fails on the object store writes no `ingest_events` row, so a
bulk upload during a store outage cannot tell from the server which files
failed. Nothing is lost or half-stored.

- Why accepted: nothing is lost or half-stored.
- Cure: a stored outcome, a migration and a 503 answer.
- Reopens: an object-store adapter that can fail apart from the API, such as
  an Azure store.

### C-220: A cut after a misread medial abbreviation stays

After an abbreviation the parser misreads inside a sentence (*gem.* for
*gemäß*), a sentence cut before a lower-case word stays, so a fact's evidence
can be half a rule. Neither corpus has such a passage, though bank terms use
*gem.* often.

- Why accepted: a broader rule, dropping a cut before a lower-case word after
  no full stop (v0.4.4), moved the cuts of 21 of 820 passages.
- Cure: a narrower rule reading the language's abbreviation table, with a
  passage and a facts replay.
- Reopens: a corpus that shows such a cut.

### C-259: A running head parted by single spaces names no chapter

A running head whose parts are separated by single spaces is read as one
field, so it names no chapter in the passages' heading trail. No passage of
either build was traced to it.

- Why accepted: no measured effect.
- Cure: comparing the head across pages to find the field that changes,
  measured as a passage change on both corpora.
- Reopens: a corpus that shows such a head.

### C-271: Two sentences read as one after an abbreviation and a figure

When an abbreviation is followed by a figure that ends a sentence (*gem. Abs.
3. Die Gebühr ...*), no cut is made, so a fact citing it cites both rules.
Neither corpus shows it.

- Why accepted: no measured effect.
- Cure: a splitter rule, measured by a passage and a facts replay on both
  corpora.
- Reopens: a corpus that shows such a sentence.

### C-278: A table row longer than the budget is cut mid-cell

A table row longer than the passage budget would be cut mid-cell, so its
cells reach no passage's grid and no table fact is read from it. No row of
either corpus is that long.

- Why accepted: no measured effect.
- Cure: keeping a row whole in one passage over the budget, measured as a
  passage change on both corpora.
- Reopens: a corpus that holds such a row.

### C-279: The digest and language reading leave out footnotes and picture text

The text a document's content digest and language are read from leaves out
table footnotes and picture text, so two PDFs differing only there are
refused as duplicates; the second stays with its uploader. No two documents
of either corpus differ that way.

- Why accepted: reading the passages' own text would change every stored
  digest.
- Cure: a digest over the passages' text, with every stored digest
  recomputed.
- Reopens: such a pair refused.

### C-280: A drawn soft hyphen mid-line is deleted

A soft hyphen (U+00AD) that a PDF draws in the middle of a line before a
lower-case letter is deleted, joining two words. Neither corpus has one.

- Why accepted: reading soft hyphens per document (v0.4.4) turned
  hyphenation points into hyphens.
- Cure: each glyph's drawn width from the PDF.
- Reopens: a corpus that shows such a join.

### C-285: An item nested at the top of a column stays flat

A list item nested right at the top of a new column stays at its parent's
level, so an exception can read as a sibling rule. The depth guard reads
indents within one column and cannot open a level there.

- Why accepted: it needs a nesting fix that passes its bar first, and C-120
  did not.
- Cure: indents carried across columns, after that fix.
- Reopens: with C-120.

### C-286: A German list item of English product names ends the chunk

A German list item made only of English product names is read as English,
and the passage is cut around it. No passage of the build was traced to it.

- Why accepted: not splitting inside a list would merge bilingual lists that
  print each item beside its translation.
- Cure: a rule that tells an island item from an alternating list.
- Reopens: such a rule.

### C-290: A new sentence splitter reaches stored passages only through a re-chunk

When a spaCy upgrade changes how sentences are split, stored passages keep
the old split until `make chunk-rerun`, and nothing records which splitter
cut a passage. A change of `NLP_MODELS` itself is reported by `make settings`
and `make doctor`.

- Why accepted: the cure is a schema change for an event a release note can
  name.
- Cure: the splitter version recorded on each passage.
- Reopens: a spaCy upgrade that moves sentence boundaries. Such a release
  says to re-chunk.

### C-300: The duplicate-content refusal has no unique index

Two files with the same text, parsed at the same moment by two parse
workers, can both be kept: the duplicate check reads before it writes, and no
unique index backs it. Their facts and questions would then be twins. The
production stack runs one parse worker.

- Why accepted: one parse worker cannot race itself.
- Cure: a partial unique index on the content digest, with a pre-check for
  databases already holding such a pair.
- Reopens: parse workers scaled out.

### C-427: A group heading at its children's level reads as their sibling

A group heading printed at the same size as the headings under it, differing
only in font family or colour, is read as their sibling, so their section
path lacks it. 4 passages showed it in the v0.3.0 review.

- Why accepted: reading family and colour as a level risks misplacing
  bold-family headings across many PDFs.
- Cure: C-368's numbering-first ranking, then a passage bar of its own.
- Reopens: once that ranking has shipped.

### N-143: A passage opening on a nested item reads its next sibling as a child

A passage that opens on a nested list item strips only that first line's
indent, so the next sibling reads as its child. The text is kept; only the
first item's depth is lost. 36 of about 2,500 football passages open this
way once v0.5.5 nests lists across page breaks, against 29 on v0.5.4.

- Why accepted: the cure re-indents the first line of every passage that
  opens on a nested item, a change of stored passage text that needs its own
  passage arm and blind reading, and the last review round of v0.5.5's
  parsing fixes went to N-102's page edge.
- Cure: the first line keeping its indent, measured as a passage change on
  both corpora.
- Reopens: a re-chunk for another reason, or a passage arm that measures the
  change on both corpora.

### C-183: Kept facts with a pointer that resolves to nothing

Some kept facts carry a pointer that resolves to nothing, because the same
noun appears elsewhere in the statement. A lenient census counted 137 on the
v0.5.1 build, few in released rows.

- Why accepted: the closed-class gaps were fixed with N-017 and N-019 in
  v0.5.3 (N-018 was withdrawn). The rest needs coreference.
- Cure: a coreference reader, a new model or a call per fact.
- Reopens: a local coreference reader that passes the fact bars.

### C-189: German compounds fragment the topic vocabulary

German compounds enter the topic vocabulary whole, so a compound and its head
word count as different terms. The labelled topics of the v0.5.1 build show
no German deficit against English.

- Why accepted: no measured effect.
- Cure: a decompounder per language and a labelled ablation of at least 40
  topics.
- Reopens: German topics reading less coherent than English ones.

### C-232: A repair piece restating a kept fact is validated again

A repair piece that restates a fact the first extraction call already kept
is validated as a second fact: 7 of 10,468 validated facts on the v0.5.1
build. The question stage's duplicate gate refuses the twin questions they
seed.

- Why accepted: the duplicate gate stops the effect downstream.
- Cure: probing repair pieces against the passage's kept facts, a tightening
  that needs a labelled replay.
- Reopens: near-twin facts past a few per thousand.

### C-233: The fit picks its draw by a reading weakly tied to the labels

The topic fit keeps the best of eight seeded draws by its own coherence
reading, which is only weakly tied to how people label topics. It logs the
nearest-centroid share beside the kept draw, at about 48 s per language per
fit at the production corpus's size.

- Why accepted: choosing or reducing the draws needs labels no build has.
- Cure: a blind relabel of several refits on both corpora.
- Reopens: when such a relabel runs.

### C-234: `EXTRACTION_BRIDGE_PASSAGES` above 2 pays for unread passages

Raising `EXTRACTION_BRIDGE_PASSAGES` above its shipped 2 pays for passages
the bridge prompt never reads. The default is unaffected.

- Why accepted: removing the setting reaches the settings catalogue, the
  Facts page and several tests.
- Cure: removing the setting.
- Reopens: the next change to the bridge prompt.

### C-256: Saving a topic label computes every passage's topic twice

Saving one topic label recomputes every passage's dominant topic twice, so
label edits slow down on a large corpus. At the production corpus's size it
stays short.

- Why accepted: no measured effect at the planned size.
- Cure: restricting the read to the topic's passages, with an index.
- Reopens: label edits that time out.

### C-267: Title-cased English words reach the German vocabulary

Title-cased English words in German text, such as product names and
headings, enter the German topic vocabulary as nouns. The topics of the
v0.5.1 build show no visible effect.

- Why accepted: no measured effect.
- Cure: a language reading per token, since case cannot tell an English title
  word from a German noun.
- Reopens: German topics named by English words.

### C-270: A hyphenated English ordinal is misread

An English ordinal written with a hyphen (*twenty-first*) is not read as the
number it names, so a fact writing it against a passage's *21st* disagrees.
Neither corpus has such an ordinal.

- Why accepted: the tokenizer splits it into three tokens.
- Cure: a number reading over several tokens.
- Reopens: English contracts or dates that show it.

### N-112: An English figure spelled in two number words is refused

An English statement that spells the cited figure in two number words
(*twenty-five days* for *25 days*, *one hundred*, *two thousand EUR*) is
refused `unsupported_addition`, because each word is read alone. The reverse
direction validates. No stored refusal of this shape was found.

- Why accepted: the cure reads runs of number words on the statement side
  through per-language cardinal tables. The same family of number-word
  readings failed its bar before (C-260), and its sibling C-270 is accepted
  as cost. Models write the cited digits.
- Cure: a statement-side reading of number-word runs through per-language
  cardinal tables.
- Reopens: such a reading that passes the fact replay of both corpora and a
  probe set of number words used as pronouns and determiners (*one of*, *a
  hundred-year*) in German, English, French and Greek.

### N-113: A currency written as its ISO code is refused as an addition

A statement that writes the cited currency as its ISO code (*EUR 5* for *5
€*, *5,00 EUR* for *5 Euro*) is refused `unsupported_addition` for adding the
code. 0 stored facts write a code where their evidence writes the sign or the
name.

- Why accepted: the cure needs an identity table from ISO 4217 codes to
  currency signs and to each language's currency names. N-050's design for
  the opposite direction, any token a currency check accepts read as a
  currency, failed its third review on ISO codes that are also words (ALL,
  PHP, TOP).
- Cure: that identity table, keyed by language.
- Reopens: a currency identity reading that passes N-050's probes (ALL, PHP,
  CUP, *Franken*, *Pfund*) and the fact replay of both corpora.

### N-125: A German fact naming a one-word bank its passage never names passes

A German fact that names a bank the passage never names (*Westbank* or
*Kreisbank* for *Nordbank*) is validated, because the German tagger reads the
one-word name as a noun and the addition check asks the evidence for proper
nouns only. English refuses the same fact. No stored fact shows it.

- Why accepted: either cure costs more than an effect no stored row shows.
  The structural reading on hand, entity spans, flags 60 of 1,177 shop and
  120 of 1,879 football validated German facts, nearly all common nouns, far
  past the 35% tightening rule.
- Cure: a different German pipeline in `NLP_MODELS`, with every German
  reading recalibrated, or a model call per fact.
- Reopens: a German pipeline change in `NLP_MODELS`, or a name reading that
  refuses the *Westbank*, *Kreisbank* and *Ostbank* probes in bank, shop and
  administration sentences, keeps the sound *Nordbank* control, stays inert
  in French, Polish and Greek, and newly refuses at most 35% usable among the
  stored validated German facts of both corpora; or a stored German fact
  naming a party its passage does not name.

### N-138: A leading zero makes two figures for the duplicate gate

The duplicate gate reads *08:30* and *8:30* as different figures, because
`numbers()` keeps the leading zero that `numerals()` strips. Two statements
alike but for the padding are both admitted (cosine 0.9969 in the repro): a
duplicate fact stored, not a wrong one.

- Why accepted: stripping the padding in `numbers()` makes more statements
  count alike, a tightening of the dedup that needs a count over every stored
  fact pair above the duplicate cosine and a labelled sample of the newly
  refused rows. Its effect is a duplicate fact admitted.
- Cure: `numbers()` without the padding, measured by that count and sample.
- Reopens: a count over stored fact pairs above `EXTRACTION_DUPLICATE_COSINE`
  that shows padded and unpadded figures admitted as two facts.

### N-141: A stored line citation is read as its whole sentence

A stored line citation keeps its sentence's index, so the bridge extractor,
`make extract-revalidate` and unfold read the whole last sentence, uncited
lines included. A bridge on such a fact can be validated on an uncited line's
figure, and a re-judge can turn a refused fact validated. A variant of C-129.
No stored row has the shape: of 8 citations of a line alone (7 in the copy of
the football rules, 1 in the build), 0 changed on a re-judge in the
reviewers' replays.

- Why accepted: the cure changes what a stored citation means.
  `Citation.sentence_ids` would keep the index the model gave, past the end
  for a line, and every reader of stored citations (the bridge extractor,
  the re-judge, unfold, the lineage pages) would resolve it through the line
  rule, with the stored rows of earlier runs left in the old form.
- Cure: that stored form, read through the line rule everywhere.
- Reopens: a change to the stored citation form for another reason, or a
  stored line fact validated on its re-judge or its bridge by an uncited
  line.

### N-144: Some quoted headings of another document lose their link

Since v0.5.5 a quoted heading links to another document only where its
sentence names that document's full title (N-111). Such a link is still lost
where the sentence splitter breaks inside the quote, the sentence wraps over
lines, two named titles nest (a general and a product title, two editions),
or the title is written with an issuer, an abbreviation or a short form. The
head takes a sibling or a term link instead, and no wrong link is added. The
stored corpora show none of the shapes.

- Why accepted: each shape needs a change to how the link pass reads a
  sentence around a quote, and each such change took a review round in
  v0.5.5 and reopened another shape; the three rounds are spent. The loss
  falls back to a sibling or term link and writes no wrong fact, where the
  wrong links N-111 removes spent bridge calls on unrelated pairs.
- Cure: a reading of the sentence around a quote over the whole text, wrapped
  lines, nested titles and abbreviations.
- Reopens: a reference reading that links every round-3 probe of both facts
  reviewers as v0.5.4 does, while removing the cross-document label links
  N-111 removes.

### N-150: A cited date restated in another form of its language is refused

A fact that restates the cited date in another of its language's forms (*1.
März 2026* for a cited *01.03.2026*, *1 March 2026* for *2026-03-01*, and the
reverse) is refused `unsupported_addition`, because a numeric date is one
token whose day, month and year support nothing. A switch between two named
forms is fine: *1 March 2026* against *March 1, 2026* is validated both ways.
It fails on the safe side: a faithful fact is refused, and no wrong date is
validated.

- Why accepted: no stored refusal has the shape (0 of 699
  `unsupported_addition` refusals), so a replay can show nothing. The cure
  adds a date reader on the evidence side beside N-109's re-pairing check,
  and a misfire there would validate a re-paired date.
- Cure: a numeric date of three runs read on the evidence side as its day,
  its month, also by the month's name, and its year, with N-109's check kept
  as it is.
- Reopens: a corpus whose refused facts restate a cited date in another
  form, on which reading a numeric date's day, month and year on the
  evidence side passes the fact replay and N-109's tests.

### N-153: German rules naming a numeric date are misparsed

A German rule that names a numeric date is misread in three ways. In *Der
Sommerschlussverkauf endet am 01-11-2030.* the year with its full stop is
tagged a finite verb, so a faithful copy counts two claims and is refused
`not_atomic`. In *Der Antrag muss vor dem 05.07.2026 eingehen.* the *dem*
before the date is read as a reference that nothing resolves, and the copy is
refused `unresolved_reference`. And *Die neuen Kontogebühren gelten ab dem
01/09/2030.* is cut before *dem*, so a statement that re-pairs the date and
cites only the first half is validated, because N-109's guard reads only the
cited sentence. English never fails in the same sentences. About 1% of
German rules naming a numeric date are hit, mostly on the safe side: the
re-paired date passed in 2 of 528 drawn swaps citing the first half, and in
none citing the whole rule.

- Why accepted: three misreads with three causes: a year with its stop
  tagged a finite verb, a determiner before a dotted date read as a pronoun,
  and the parser's cut before a lower-case word, which is C-220's. 0 stored
  facts have the shape: the stored German football rules write dates in
  words, and the shop corpus with slashes.
- Cure: a numeric date read as one figure before predicates and references
  are counted, so it is never a verb and a determiner before it is no
  pronoun, and the re-pairing guard reading the whole passage's dates.
- Reopens: a corpus whose German facts write numeric dates and show one of
  the three misreads, on which reading a numeric date as one figure passes
  the fact replay.

### C-034: The parts reading narrows only some padded derived rows

The needs_both parts reading on derived questions (implication, aggregation)
narrows 11 of 19 padded rows and no honest one. 8 padded rows keep a citation
they do not need.

- Why accepted: narrowing them needs an arithmetic reading of which premises
  a conclusion rests on.
- Cure: one model call per derived row.
- Reopens: a deterministic reading of that.

### C-053: A compound question's halves are not read again

A compound question's halves are stored, but `make questions-reverify` does
not read them again: its re-check is rules-only, and checking a half needs
the verifier.

- Why accepted: the cost below.
- Cure: one model call per compound row on every reverify.
- Reopens: a rules-only reading of a half.

### C-132: Accepted questions ask another type than planned

About one accepted question in ten asks another type than the one planned,
so per-type figures in a release are off by about a tenth, though the
questions are often still usable.

- Why accepted: no deterministic reading tells the type a question really
  asks for every type and language.
- Cure: a model reading per row, or a new calibrated gate with 60-row arms on
  both corpora.
- Reopens: per-type scores becoming a release figure.

### C-134: Two parallel drains write twins of each other

Two question drains running at once can each write a twin of the other's
question. Both are verified and paid for, and the release's re-check keeps
one. Only spend is lost: at most two drains a database are supported, and no
twin reaches a release.

- Why accepted: no release effect.
- Cure: re-probing each row inside the store transaction, with a two-drain
  integration test.
- Reopens: more drains a database allowed.

### C-150: Explanation-form keys are not held to completeness

Explanation-form keys, mostly reasons, are never checked for completeness,
because the length of prose says nothing about how much it covers. A 60-row
read on the v0.5.1 build found 4 partial reason keys (0.93 complete, above
the 0.80 of all keys).

- Why accepted: the only separating bar passed at 7 rows.
- Cure: a model judgment of coverage per row.
- Reopens: a 60-row read of reason keys below 0.833 complete.

### C-154: The `off_topic` gate ships off

The `off_topic` gate ships off (`QUESTIONS_OFF_TOPIC_OVERLAP=0`), because
comparing an unanswerable question with one short passage's words refused
sound rows. It still records its share. The release's unanswerable rows read
0.891 usable with or without it.

- Why accepted: no release effect.
- Cure: a gate reading the whole corpus vocabulary, with a labelled arm and a
  threshold calibrated on both corpora.
- Reopens: released unanswerable questions drifting off the corpus's subject.

### C-157: Generated German writes ß where the corpus writes ss

Generated German writes ß where a Swiss-German corpus writes ss: 32 released
German rows. A reader or a judge scores them right; only a string-matching
scorer could miss.

- Why accepted: the cure is a regional spelling table, which the rule on word
  tables does not allow.
- Cure: a regional spelling table, which needs a change to that rule.
- Reopens: a customer that scores by string match.

### C-184: A refused unanswerable slot is rewritten as an answerable question

A refused unanswerable slot is rewritten as an answerable question that the
reason filter would not have dealt. The row is gated like any other, so only
some writer and verifier calls are spent. No release effect was measured.

- Why accepted: only spend is lost.
- Cure: none designed. It would save some writer and verifier calls.
- Reopens: unanswerable slots growing costly (see
  `QUESTIONS_UNANSWERABLE_SHARE`).

### C-261: A comma-spliced double question passes the compound gate

Two questions spliced with a comma under one question mark pass the compound
gate. None of 2,175 accepted rows on the v0.5.1 build has that shape, and 28
of the 30 rows sharing its surface form are valid German questions opening
with a premise.

- Why accepted: no measured effect, and the surface rule would refuse the
  premise form.
- Cure: a parse reading of two interrogative clauses that spares the premise
  form.
- Reopens: a build that shows such questions.

### C-292: A language held by one document gets no boilerplate filtering

The boilerplate filter reads repetition across documents of the same
language only (v0.3.0), so a passage and its translation are not furniture.
A language held by one document gets no filtering, and its furniture
passages reach the question writer: on the *Laws of the Game* corpus, one
document a language, 7 real furniture passages reach it. The extraction
prompt's rule against facts about the document itself keeps their facts out.
Each language of the v0.5.1 football build holds 15 documents.

- Why accepted: reading repetition across languages treated translations as
  furniture, the earlier bug.
- Cure: a furniture reading within one document.
- Reopens: a corpus with a single document in some language.

### C-293: The enumeration gate cannot tell a kind from a property

An enumeration answer listing two properties of one thing (*schnell und
kostenlos*) counts as two kinds, so 4 accepted enumerations on the v0.5.1
build overcount.

- Why accepted: the parse cannot tell a kind from a property.
- Cure: asking the verifier, already called, whether the items are kinds,
  which needs a question arm.
- Reopens: enumerations of properties growing.

### C-316: A gate turned off shares the "not run or not recorded" bucket

Questions written with the phrasing gate turned off are reported with rows
from before the gate existed, in one "not run or not recorded" bucket. A
fresh build with the gate on fills no row there.

- Why accepted: no effect on a build with the gate on.
- Cure: storing "off" for a disabled gate.
- Reopens: the gate run off.

### N-116: A German one-word company name anchors no question

Whether a German question names something turns on which bank it names.
`anchored()` counts names through PROPN, and the German tagger reads many
one-word company names (*Westbank*, *Ostbank*, *Kreisbank*) as NOUN, while
*Nordbank* and the English twins read as names. Such a question costs a
phrasing-judge call, and its unanchored verdict rests on the model alone;
this reading refuses nothing on its own. Measured on four names only.

- Why accepted: the same cause as N-125 on the question side, with the same
  cure: the name reading N-125 lacks.
- Cure: as N-125.
- Reopens: with N-125.

### N-128: An English value naming a German institution is refused as an action

An English value that names a German institution (*The Bundesamt für
Justiz*, *The Beitragsservice von ARD, ZDF und Deutschlandradio*) is refused
`wrong_form` as describing an action, because the English tagger reads *für*
and *und* as verbs. *The Federal Office of Justice* and the German *Das
Bundesamt für Justiz* pass.

- Why accepted: the design decided in v0.5.5, skipping a token that
  `nlp.analysis._foreign` marks, cannot work: `_foreign` marks only
  lower-case nouns of a language that capitalises its nouns, and `_acts`
  counts only VERB and AUX, so no token is both. The structural alternatives
  misfire or need what N-125 lacks: a verb between two proper nouns is the
  commonest English action shape (a company makes a product), and an
  entity-span reading of German words inside an English value needs a name
  reading the German and English pipelines do not give.
- Cure: a reading that marks German words inside an English value, a
  mixed-language tagger or N-125's name reading.
- Reopens: such a reading passing the stored answer-form replay with at most
  1 sound row newly refused.

### N-137: The release draw reads re-paired figures as a restatement

The release draw's restatement check reads two questions as restating each
other when they re-pair the same figures (*3 % for 12 months* against *12 %
for 3 months*), so one comparison candidate is dropped from the draw. No
wrong row is kept, and no stored draw shows it.

- Why accepted: the readers that tell a figure's kind and unit live in
  extraction, which question generation may not import, since the stages
  are independent. Moving them into `nlp` for one dropped candidate is a
  rework larger than the effect.
- Cure: those readers moved into `nlp`.
- Reopens: the figure kind and unit readers moving into `nlp` for another
  reason, or a stored release dropping a question as a restatement of
  another pairing.

### N-142: An archive restore can leave restored questions under an old release id

An archive restore keeps a restored question's old release id in its own
transaction, without the release lock N-114 added, so a draw committing
meanwhile can leave restored rows under the old id beside the new draw. Read
in the code, not run: it needs a restore and a release write within one
transaction's span, both operator commands, and the next draw repairs it.

- Why accepted: the archive service may not import question generation,
  since the stages are independent, so sharing the release lock means moving
  its key into a module both import, for a race no run has shown.
- Cure: the release lock's key in a module both import.
- Reopens: a restore reported leaving restored questions under an old
  release id beside a new draw, or the release key moving into a shared
  module for another reason.

### N-149: A key giving a range's ends apart never agrees with the range written whole

A key that gives a range's two ends apart (*zwischen 100 und 110 Euro*,
*between 100 and 110 days*) never agrees with a recovery that writes the
range whole, *100–110*, though the reverse pair agrees. `agrees()` splits the
recovery's ranges into their ends only when the key holds a range, so a key
of two values looks for 100 and 110 among the recovery's values and finds
the one token *100–110*. It fails on the safe side: a sound key is refused
`not_recoverable`, and no wrong key passes. 5 stored keys have the shape, 4
of them in accepted questions.

- Why accepted: a cure only adds readings to the recovery, so it can only
  loosen the round trip, and a loosening is calibrated on the verifier's
  recoveries, which the store does not keep. That needs a model arm, and 5
  stored keys cannot fill its 40-row floor.
- Cure: a recovery's ranges split into their ends also for a key of two or
  more values, with the present rule kept for a key of one value (*110 m* is
  not what *100–110 m* says).
- Reopens: a corpus with 40 or more keys giving a range's ends apart, or
  stored round-trip recoveries, on which that split passes the loosening
  bar.

### C-085: The API's reads, the pages and Dagster have no login

The api guards its writes and `/settings` with `API_TOKEN`, but its other
reads are open, and the Streamlit pages and Dagster have no login. All three
bind to 127.0.0.1.

- Why accepted: a login needs an identity provider or an authenticating
  proxy, a new service this release does not add. Exposing any of them
  beyond loopback stays forbidden.
- Cure: an identity adapter, such as Entra ID, behind the `Authenticator`
  port.
- Reopens: such an adapter.

### C-296: SeaweedFS and Redis accept any caller on the stack's network

Any container of the stack can read and write the object store's internal
services and Argilla's Redis, which carry no password. Nothing is published
beyond the host, so this needs a container already compromised. (FIX-R110:
an internal storage network was not run end to end.)

- Why accepted: the cure needs a scratch-stack proof this release did not
  run.
- Cure: an internal network reached only by the S3 gateway and Argilla, and a
  Redis password, proved on a scratch stack.
- Reopens: the Azure deployment, where managed services replace both.

### C-298: The parse worker holds owner and admin credentials

The parse worker holds the database owner role and the Phoenix admin secret,
so a parse compromised through a crafted PDF could drop the database or read
every trace.

- Why accepted: infrastructure work beyond a patch release.
- Cure: a data-only role for workers and an ingest-only trace key.
- Reopens: the Azure identity work, one identity per service.

### N-078: A Dagster stop is refused and the api answers it as done

A stop of a running Dagster run is refused with
`DagsterUserCodeUnreachableError` when the daemon launched the run, because
the webserver cannot reach the run's code server. The api records the stop,
and the run goes on until Dagster marks it cancelled after 180 s, so C-199's
forced cancel never fires. Seen on the scratch stack, and on v0.5.2 alike.
The production profile does not run Dagster.

- Why accepted: an orchestration change beyond this patch release.
- Cure: routing the termination through the daemon, or making the run's code
  server reachable from the webserver.
- Reopens: runs that must stop at once on the Dagster profile.

### C-200: The nightly schedule ignores Stop and `INGESTION_OPEN`

Once switched on, the Dagster nightly corpus schedule queues every stage at
02:00 even after an operator pressed Stop or closed ingestion. The schedule
ships off, and the production profile runs stages through `make
corpus-hosted`, not Dagster.

- Why accepted: no effect on the production profile.
- Cure: a schedule evaluation function sharing the arrivals sensor's rule,
  tested on a Dagster instance.
- Reopens: Dagster joining the production profile.

### C-207: The CI virtualenv cache key hashes the whole Makefile

Any Makefile edit invalidates the CI virtualenv cache, so the next CI run
reinstalls the dependencies. No result is wrong.

- Why accepted: only CI time is lost.
- Cure: moving the install recipe into a file the Makefile includes, and
  hashing that.
- Reopens: CI time mattering.

### C-242: `make diversity` reads one workbook up to five times

`make diversity` reads the same workbook up to five times, once per report
it builds. Every figure is right; only time is lost on large workbooks.

- Why accepted: only time is lost.
- Cure: reading each sheet once, which reworks five readers with their own
  read options.
- Reopens: a production workbook that makes the command slow to use.

### C-243: `GET /prompts` returns 1.46 MB unpaged

`GET /prompts` returns every version of every prompt in one response, 1.46
MB on the build, so the Prompts page is slow and grows with each version.

- Why accepted: only the page's speed suffers.
- Cure: the current versions by default and older ones on request, changing
  the route, its contract and the page.
- Reopens: the page becoming unusable.

### C-248: About 400 lines and pyLDAvis draw one figure

About 400 lines and the unmaintained pyLDAvis dependency draw one figure on
the Topics page that no stage reads, a maintenance and supply-chain cost.

- Why accepted: removing it changes what the page shows, a product decision.
- Cure: removing the figure and the dependency.
- Reopens: with the supply-chain work (C-297).

### C-249: The progress sensor misses smaller refits and fits outside Dagster

Dagster's progress sensor misses a refit to fewer topics and fits run outside
Dagster, so the topics asset shows an older fit. The production profile does
not run Dagster.

- Why accepted: no effect on the production profile.
- Cure: none designed, since the production profile does not run Dagster.
- Reopens: the orchestrated path returning to production.

### C-252: Language columns hold bare ISO 639-1 codes

Stored rows carry a two-letter language code, so script or region variants
of one language (Traditional and Simplified Chinese, Brazilian and European
Portuguese) cannot be told apart. German and English are configured, and a
language no configuration names is refused at parse.

- Why accepted: no configured language needs it.
- Cure: widening every language column and the per-language tables to BCP 47
  tags, in one migration.
- Reopens: such a language to be configured.

### C-297: Supply chain: unlocked Dagster image, unchecked installs, mutable tags

The Dagster image is not locked like the api's, installs are not
hash-checked, and images are pinned by mutable tags, so a retagged image or
a replaced wheel would enter a rebuild unnoticed.

- Why accepted: infrastructure work beyond a patch release, verifiable only
  in CI.
- Cure: locking and hash-checking every install and pinning images by
  digest.
- Reopens: the Azure container registry work.

### C-301: The prompt that wrote a question is not shown

Reviewers cannot see on the Questions page which prompt wrote a question; it
is recoverable through the row's trace in Phoenix. No data or quality effect.

- Why accepted: no data or quality effect.
- Cure: resolving the prompt from the stored trace id on the page.
- Reopens: reviewers needing it.

### C-302: An emoji shortcode in a filename draws as an emoji

A filename holding an emoji shortcode such as `:rocket:` draws as an emoji in
page messages. Nothing stored changes.

- Why accepted: nothing stored changes.
- Cure: escaping filenames wherever pages render them as Markdown.
- Reopens: reviewers confused by it.

### C-304: Four frontend helpers restate other code

Four frontend helpers restate code that exists elsewhere. They agree today,
so the cost is keeping copies in step.

- Why accepted: no behaviour differs.
- Cure: one copy of each.
- Reopens: the next rework of the frontend.

### N-079: Filebeat reads the hosted runner's plain-text log as JSON

Filebeat ships `logs/corpus-hosted.log`, the plain-text `make` output of
`make corpus-hosted`, through its ndjson parser. The runbook walk on the
release candidate logged 1,626 "Error decoding JSON" lines in Filebeat, one
for each line of that log, and those lines are not indexed as fields.

- Why accepted: proving a cure needs another scratch-stack walk with the
  logging profile, which this release did not budget.
- Cure: a Filebeat input that reads that file as plain text, or leaves it
  out.
- Reopens: the next scratch-stack walk with the logging profile.

### N-080: `make doctor` prints a download that fetches a whole model repository

The line `make doctor` prints for a missing encoder, `poetry run hf download
<repo> --revision <commit>`, fetches every file of the repository: about 8.9
GB for `intfloat/multilingual-e5-large`, with ONNX, OpenVINO and PyTorch
weights beside the ones the loader reads.

- Why accepted: finding the files each encoder needs, per encoder and
  revision, is a measurement this release did not make.
- Cure: `--include` patterns for the files each encoder needs.
- Reopens: that measurement.

### N-139: A restore puts back another deletion's copy of an object

Since v0.5.5 a restore of a chosen deletion puts back the archived copy
stamped nearest that deletion (N-119). For an object the chosen deletion
never archived, it still puts back another deletion's copy, so a restored
fit comes back beside another deletion's figure or model. v0.5.4 did the
same.

- Why accepted: the cure is a record of which objects each deletion
  archived, a list per archived transaction and so a schema change, from
  which a restore takes only those. A time window on the stamp fails,
  because document removal stamps its objects before `archived_at` and
  `make topics-delete` after it. A refit recovers the effect.
- Cure: that record of what each deletion archived.
- Reopens: a schema change to the archive for another reason, or a restore
  reported putting back another deletion's object.

## Not measured: budget

Each cure changes which facts or questions are written, so its bar is a model
arm on both corpora. v0.5.3 kept its model budget (USD 80) for the arms of
high and medium items, and these six low items were not measured.

### C-159: One capital in a lower-case query switches the case rule back on

In an opt-in search-query category, one capitalised brand in a lower-case
German query switches the noun-case rule back on, so the query loses its
nouns in the lemma gates. No default category reaches it.

- Why accepted: not measured: budget.
- Cure: a share rule, measured by a search-query arm (about USD 8).
- Reopens: search-query categories entering the default.

### C-269: Summary facts framed as "this section covers" yield questions about the document

A few summary facts are framed as *this section covers ...*, and the question
written from one asks about the document: 1 of 60 summary-cited questions.

- Why accepted: not measured: budget.
- Cure: a change to the digest prompt, measured by an extraction arm (about
  USD 4).
- Reopens: the next calibration of the digest prompt.

### C-141: Reason questions with no stated reason

A reason slot prefers facts whose evidence states a purpose (per-language
marker lemmas), and becomes another kind where the topic states none. The
filter passes a fact when a marker appears anywhere in its evidence. On the
v0.3.0 rebuild 29 of 62 accepted answerable reason questions and 20 of the 34
released ones had a circular key. On the v0.5.1 build about 1% of released
questions ask why where the cited passage states no reason.

- Why accepted: a bar on a reason key's new words was measured and held
  back: every bar that separates circular from sound reasons sits between
  two of one rulebook's own share values. Requiring the marker in the fact's
  own clause changes which questions are written. Not measured: budget.
- Cure: that requirement, measured with model arms on both corpora (about
  USD 7).
- Reopens: a question arm run for another change that can carry this one.

### C-148: A question naming the offer rather than its subject

A question can name the offer rather than its subject (*Welche Teststufen
werden in den Angaben genannt?*), which no corpus answers. 4 rows of the
2026-10-13 release did, and 3 of 1,273 released rows on the v0.5.1 build, 2
of them unusable. A gate in
[`gates.py`](../backend/question_generation/gates.py) refuses a *How many*
question whose answer is a count equal to the number of cited facts, in
digits or written out from two to twelve, and exempts a count a cited
statement states. It does not catch the offer-naming rows.

- Why accepted: not measured: budget.
- Cure: one more reading in the phrasing judge, with a calibrated arm on two
  corpora (about USD 12).
- Reopens: the next recalibration of the phrasing judge.

### C-153: The answerable-elsewhere probe cuts its rankings before fusing them

The probe for unanswerable questions the corpus answers cuts its vector and
word rankings to twice the limit before fusing them, so a passage deep in one
ranking can be missed. No released miss is traced to it.

- Why accepted: not measured: budget.
- Cure: a deeper read, measured by a settles replay on a database copy (about
  USD 1).
- Reopens: the next unanswerable replay.

### C-174: Compound and enumeration questions about the document

A few compound and enumeration questions ask about the document rather than
its content.

- Why accepted: not measured: budget. No design exists.
- Cure: a writer prompt change, with a calibrated arm on two corpora (about
  USD 12).
- Reopens: the next recalibration of the writer prompts.

## Domain-specific

Only a rule fitted to one corpus's layout or wording would cure these.

### C-096: Two document titles stay wrong

Two of 30 football document titles still do not name their document: one
keeps a previous edition's title, and one is clipped at a conjunction.

- Why accepted: the title rule that fixed the other ten (v0.5.2) is generic
  and holds over ±20% of its threshold. No generic rule reaches these two.
- Cure: a rule fitted to these two titles.
- Reopens: a rule that fixes them without changing the other 78 titles of
  both corpora.

### N-060: A web page's "Last checked" stamp stays in the last passage

A web page's *Last checked: dd/mm/yyyy* stamp stays in the last passage of
33 of the 50 shop documents, glued into the last German sentence. A one-page
print drops it as furniture.

- Why accepted: the furniture reading drops only what every page prints, and
  the stamp is printed once in the body flow. A rule reading the stamp's
  words would be fitted to one website, and a rule across documents needs a
  threshold only this corpus could set.
- Cure: a generic reading of furniture printed once a document.
- Reopens: such a reading, shown on a second corpus of printed web pages.

### C-266: Imprint, hotline and contact passages yield questions

Imprint, hotline and contact passages are dealt like any other, so some
questions ask for an address or a phone number.

- Why accepted: the only design skips passages dense in e-mail, URL, phone
  and postcode shapes. Their formats differ by country, and its threshold
  would be set on one site's pages.
- Cure: a reading of what a passage asks of its reader.
- Reopens: such a reading.

## Upstream

A dependency has to change before these can be cured.

### C-281: The converter reads a symbol-font bullet as ∞

Docling reads some PDFs' bullet glyph from a symbol font as `∞` (U+221E) or a
private-use character, and flattens a nested item. 235 list items in 47
football passages open on a stray sign. (NEW-qa-parse-1.)

- Why accepted: a local repair reading the glyph's font (v0.5.2) turned
  `€ 5,00` into `• 5,00` and stripped other one-character signs.
- Cure: Docling mapping symbol-font bullets to a bullet and keeping the
  nesting.
- Reopens: a Docling release that does.

### N-001: filelock 3.32.7 carries 13 accepted advisories

filelock 3.32.7 carries 13 advisories fixed only in 4.x, and litellm
(1.106.2, the locked release, and 1.108.0, the latest release on 2026-11-04)
requires filelock below 4.0. The 1.109.0rc1 pre-release allows filelock below
5.
Each advisory needs a second local account with write access to the lock's
directory, which the single-account backend containers do not have.

- Why accepted: the upgrade waits on litellm.
- Cure: both locks upgraded to filelock 4, and the entries deleted from
  `configs/audit-accepted.txt`.
- Reopens: a litellm release that allows filelock 4. The entries expire on
  2026-12-31 and are read again then.

## Reproducing this page

The counts are queries over `questions`, `facts`, `question_facts` and
`fact_passages`. The same rows come out of the workbook:

```bash
make questions-export OUT=audit.xlsx FILTER="--released"
```

Two analysts, working apart, confirmed each entry's mechanism in the code of
v0.5.2, and its figures come from the run, replay or arm it names. The
entries of v0.5.5 rest on a test or a probe that reproduces each, or for
N-142 a reading of the code, and their figures on the replay, arm or review round
they name.
Re-measuring means taking a corpus through again and rewriting this page and
[measurements.md](measurements.md).

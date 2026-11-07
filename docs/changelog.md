# Changelog

What each release fixed, newest first. Each entry names the defect and its
fix and, from v0.2.2 on, what was measured. [bugs.md](bugs.md) holds the
defects that stay, each accepted with its measured effect and its cost.

A fix changes what the next run writes. Stored rows improve only through the
re-runs that operations.md lists for
[v0.2.2](operations.md#upgrading-to-v022),
[v0.3.0](operations.md#upgrading-to-v030),
[v0.5.2](operations.md#upgrading-to-v052),
[v0.5.3](operations.md#upgrading-to-v053) and
[v0.5.5](operations.md#upgrading-to-v055). v0.5.4 needs no rerun.

## Fixed defects

Fixed defects by release, newest review first.

## Found by the deep QA pass of 2026-11-04

The deep QA pass after v0.5.4, the last of this QA cycle, read the code of
v0.5.4 again in six hunts: parsing and passages; facts, references and
topics; questions, the gates, the release and the export; the platform;
security and secrets; and language and domain. Four test tracks ran beside
them. T1 wrote tests that kill the mutants `make mutation` left alive, T2
wrote properties over the text readers, T3 wrote tests over the risky
branches the coverage report showed missed, and T4 ran the suite in random
orders and guarded it against hangs. Their findings and the reviewers' make
57 items, `N-101` to `N-157`. 30 were fixed, 2 closed and 25 accepted.

A fix has a test that failed before it and a bar written before its measure.
Two reviewers read each group of fixes to the code, in up to three rounds;
fixes to the tests alone were held to their own runs in three orders. A fix
that failed its bar or its third round of review was withdrawn, and its item
accepted: [bugs.md](bugs.md#failed-bar) gives its numbers.

Passage arms parse the 30 football and 50 shop PDFs once, replay the chunker
over them with and without the change, and a reader reads every changed
passage blind. Fact replays run the changed validation over the 20,888 facts
stored in three copies: the football build (13,716), the shop corpus (2,838)
and a copy of the football rules that holds facts only (4,334). Question
replays read the 4,348 stored questions, 3,885 of the football build and 463
of two shop runs.

### Fixed in v0.5.5

| Item | Defect | Fix | Measure and bar |
|---|---|---|---|
| N-101 | Across a page break, a list read the next page's indent off the previous page's column edge, so mirrored margins nested an outer item or flattened a sub-item | Each page's list indent is read off that page's own column edge. A page that holds only the list's items reads it off the nearest page of the same parity that has one, since facing pages mirror their margins. One commit with N-102 | As N-102. The 8 cases of its red test pass |
| N-102 | A list the converter splits at a page break lost its depth: the nesting read each list group alone, and Docling starts a new group on every page, so sub-items going on onto the next page fell to the outer level (stored passages 2836, 2906, 3984 and 4035) | A list that opens on a later page right where the one before it ends, with nothing between them, is walked as one list and goes on at the levels open there, each page's indent read off its own edge (N-101) | Passage arm: 37 football passages in 7 documents change their depth, 0 shop, and no letter or digit changes. Blind reader in the third round, on 44 changed passages that still held N-103's joins (since withdrawn): the fix as printed in 41, both in 1, neither in 2 (a page cut neither version joins), the fix worse in 0, v0.5.4 worse in 42. The 4 stored passages print their sub-items under their item. Bar: at least 90% at the printed depth, at most 2 worse, shop unchanged |
| N-154 | Before the release, the parsing branch flattened by one level a list going on at the top of the next page with only its sub-items there, at two indents: a regression of N-102's code that T2's properties found | Where no edge can be read for such a page, the edge before is kept when the page's leftmost item sits within half a step of a level open before. Otherwise the levels restart at level 0 | T2's repro and property pass, 3 red before. 4,154 tests pass. Passage arm: 0 passages differ from the branch before the fix on the 80 PDFs, and N-102 still changes 37 football passages in 7 documents |
| N-104 | When a table's rest was joined from the next page, the captions and footnotes the converter attached to the rest went to the furniture layer with it and reached no passage | The rest hands its footnotes, and the captions the table lacks, to the table. A caption repeating the table's (`X (Fortsetzung)` after `X`) or a footnote the table already holds is not printed again | Red tests green in German, English, French and Greek. On a fresh parse of the 80 PDFs, none of the 21 joined rests carries a caption or a footnote, so no document changes |
| N-106 | A passage stored as already extracted because no pipeline named its language stayed extracted after that language was configured, through both `make chunk-revocabulary` and a `chunk-rerun` that keeps its row | Such a passage goes back to `new` when either step gives it a language, unless a fact cites it, so `make extract-start` reads it | Red tests and their controls green; 120 integration tests pass. No stored passage is affected: 0 of the 2,504 passages of the 80 PDFs read as no language |
| N-152 | A German sentence stating an amount with thousands marks (*1.000,18 EUR*, *56.455,35 EUR an*) was cut after the figure, before its currency or the rest of its clause, because the splitter kept the parser's cut after a figure with no end mark on its line | The amount stays in one sentence with its currency and the rest of its clause. A sentence ending on a full stop (*5 EUR.*) never joins the next one this way | Red tests green. German bank sentences with a dot-grouped amount cut this way: 25 of 700 before, 0 after. A re-split of the 3,272 stored prose passages of the three copies moves 5 (0.15%), all English, each one join that a blind reader found right; no item-number or table-row cut moves, and the 15 facts on them keep their verdicts. Bar: no moved cut joins two sentences, under 1% of passages move |
| N-107 | The duplicate gate counted two statements alike when a figure kept its digits but changed its unit, its month or its pairing, so a different fact was refused as a twin | Two statements are twins only where the months, or the weekdays, both name share one, and where a value both state as a currency, a share, a period or a unit of time or measure reads the same on each side. 1 January and 1 July, 14 days and 14 weeks, 3 % for 12 months and 12 % for 3 months are apart. A date with its weekday, a range against its enumeration, and 5 mg/l against 5 mg per litre stay twins. SI symbols are read in every language, months, weekdays and units of time only where the language has a table | 14 German and English pairs apart both ways. The reviewers' restatement pairs alike both ways: 33 in the second round, and 45 of a later list once a unit is read up to its slash. French, Polish and Greek pairs as before. Replay of the 753 stored duplicate refusals: 0 freed (bar: under 20 freed, at most 1 restatement). 0 of 20,888 stored facts change |
| N-108 | A citation of a sentence and a list line of the next sentence took the whole range between them as evidence, so the swap guard read an uncited line's figure as cited | A list line cited together with the sentence before it is its own piece of evidence, so a statement lifting an uncited line's figure is refused `unsupported_addition`, as it is when the line is cited alone | Repro green in German, English, French and Greek. Fact replay: 0 of 20,888 verdicts change |
| N-109 | A statement that re-paired the digits of the cited clock times or dates was validated, because a time or a date was read as the set of its digit runs | A colon clock time with two-digit minutes, or a three-run date with its four-digit year at the same end, that the cited text writes only with its runs in another order is refused `unsupported_addition` ("13:30 to 9:00" for "9:30 to 13:00", "12-01-2026" for "01-12-2026"), for atomic facts. Hours are compared with hours and minutes with minutes, an hour the cited text writes alone counts as a time, and a 12-hour time is held modulo 12. Ratios, seasons, ranges, another convention's date, dotted times and 24:00 for 0:00 keep their verdict | The re-pairs refused in German, English, Polish and Greek. 30 keep probes of both reviewers, and the C-158 pins, validate as before. Fact replay: 0 of 20,888 change (bar: under 20 newly refused, at most 1 sound) |
| N-111 | A quoted span linked to a heading of any document, so a page quoting a button label or a term became a reference to another document's section of that name | A quoted heading links to a section of its own document, or of another document only where the quote's sentence, the quote cut out, names that one document's full title: every noun, name and adjective of it, as written or by its lemma. Where two documents' titles are named it links to neither. Numbered references are read as before | Link replay over 3,335 stored passages: 9 of 314 reference links removed (8 football, 1 shop), 0 added, no numbered link changed, and 15 heads take another best link. A blind reader of the 10 links the first version removed found 2 references the sentence makes to the other document's section and 8 terms or labels (bar: at most 3). Each title's words are read once a pass: 200 documents take 3.3 s, against 1.8 s on v0.5.4 |
| N-148 | A currency sign, a range's dash or another sign that the tagger tags a numeral was read as a number, so *The fee is 5 €.* stated the numbers 5 and €, and the same amount written *42,803.48 €* and *42803.48 €* stated different numbers to the duplicate gate and the restatement check | Of a sign the tagger calls a numeral, only a math sign (≤, ≥, ±, +) is still read; a currency sign, a dash or any other sign is no number. So *42,803.48 €* and *42803.48 €* state the same numbers, and a rule with *≥ 50 EUR* is never counted as its opposite with *≤ 50 EUR* | Red cases green, among them comparison-sign pairs in German, English, Polish and Greek. Of the 6 stored fact pairs the change reaches, none moves its duplicate or restatement verdict, and the 11 stored facts with a math sign read as on v0.5.4. The first version dropped the math signs too and failed its review; the second passed both reviewers |
| N-114 | Two release writes at once left the rows of both draws released, under two release ids | `release()` takes a transaction-scoped advisory lock first, so the second write waits for the first | Red test green; 35 integration and 1,806 unit tests pass |
| N-115 | The run comparison counted every restored question twice, once live and once from the archive | A restored question counts once, from its live row or else its newest archived copy | Repro green, and the 6 earlier tests of `runs.py` unchanged |
| N-117 | Two comments in the question code still said the trigger deletes a question whose last fact goes, which migration `4a7c2e91d3b8` replaced with a `source_changed` rejection, and the `questions.status` column comment said rejected questions are never deleted | Six texts say what the code does: a question that loses its last citation is rejected as `source_changed` and kept, and deleting a document, or what came from it, deletes its questions. Revision `c5a82e17d3f9` rewrites the column comment | tests/static green. The only change in the database is one column comment |
| N-133 | A German comparison answered in its plainest form, *X ist schneller als Y*, was refused as naming one thing, because no noun phrase was read for the term after *als* | A noun the comparison particle governs (`COMPARISON_TAG`, `KOKOM` in German) counts as a phrase when no chunk holds it. English already reads the noun after *than* as a chunk, and French, Polish and Greek read as before | Red German cases green; the English twins and the controls unchanged. Replay of the structural and type gates over the 4,348 stored questions: 0 verdicts change |
| N-134 | A German date-range key *1.–3. Mai* never agreed with a recovery saying *vom 1. bis 3. Mai*: the range's second end was read as the count 3 | The range's second end takes the ordinal stop its first end carries | Red German cases green; the English twin and a verbatim recovery unchanged; French, Polish and Greek give their earlier verdicts. None of the 4,348 stored keys holds such a range |
| N-145 | A German value key whose unit is written in lower case (*80 cm*, *30 kg*, *5 mm*, *10 km*) never agreed with a German sentence stating it, because the parse leaves a lower-case word out of a capitalised sentence's content lemmas | A figure is paired with the word written right after it, so such a key agrees with a recovery that writes the same unit right after the same figure, in German as in English. The unit is read past a no-break space, two spaces or a line break between it and its figure | Red cases green. Replay of the 3,281 stored keys against their cited statements: 14 German football rows move from refused to agreed and none the other way; no shop or English verdict changes. A blind reader found 14 of 14 usable (bar: 11, none invalid), and noted that two rest on a stored fact that misreads its page, an error of the fact stage |
| N-147 | The containment fallback of `agrees()` was a substring test, so a key *5 m* agreed with *5 mm* and *2 l* with *2 lb* | A key that ends in a figure's unit is found in a recovery only where that unit ends | 30 must-disagree cases and 36 guards pass in the value, list and explanation forms. Replay: 0 of 3,281 stored rows move |
| N-151 | An ordinal word past twelve that the tagger tags a noun or a name asserted no value, so *ab der dreiundvierzigsten Mahnung* agreed with *ab der 5. Mahnung* and *43 Mahnungen*, and *the seventieth reminder* never agreed with *the 70th reminder* | Such a word is the ordinal it names whatever its tag, as a cardinal from thirteen on already was | Red cases green; French, Polish and Greek stay as before. Replay: 0 stored rows move |
| N-155 | A German figure that the lemmatiser gave a letter (*3.948.006,39r*, a range *3667–5224r*) was kept as a content lemma, so a range key never agreed with its ends written apart | A figure is never a content lemma, whatever letter the lemmatiser adds. A proper noun holding no letter is read by its text, not by a lemma the German lemmatiser suffixed (*3965–4092-*), so a German range key the tagger calls a name also agrees with its ends written apart | Red tests green. The content lemmas of every stored German passage, fact and key of the three copies are unchanged. The proper-noun reading changes only a bullet or a slash in 17 stored passages, which no fact, key or cited statement holds, so no stored verdict moves |
| N-156 | The arithmetic check refused a correct total of two or more whole figures from 1900 to 2100 as a sum of years, whatever their spelling: *2.000,00 EUR* twice was not *4000,00 EUR*, nor *1,950* and *2,000 customers* *3,950* | A total is refused as years added together only where each figure is written as a year: four digits with no mark and no currency beside them. A unit word is not read, so *2000 kg* twice is still refused. The search stays linear in a passage's four-digit figures | Red cases green in five languages, and the year rule's own cases stay refused. The 69 stored aggregation keys keep their verdicts. The perf ceiling reads 8.4 ms, as on v0.5.4 |
| N-157 | A German key that capitalises its nouns dropped its own lower-case unit, and no key compared a one-letter unit, so *Der Versand kostet 5 EUR je 10 kg.* agreed with *... je 10 g.* | A value key asks back each unit it writes right after a figure, through N-145's pairing, so it agrees only with a recovery giving that unit beside that figure | Red cases green. Replay: no stored row newly refused, and one German row admitted (*410 bis 450 g*), which a blind reader labelled good |
| N-118 | `S3_BUCKETS` accepted the archive role on the same bucket as a live role, and an archive purge then deleted the live documents in it | Two roles that resolve to one bucket, a default name included, are refused when the setting is read, with a message naming both roles and the bucket | 4 red cases green. The shipped `S3_BUCKETS` resolves to five distinct buckets, and the contract, unit, static and smoke tests pass |
| N-119 | Restoring an older deletion put back the newest archived copy of each object, not the copy that deletion archived | A restore of a chosen deletion puts back the archived copy stamped nearest that deletion's `archived_at`, the latest chosen one's where two took the same key. A rollback of a failed delete still takes the newest copy | Red tests in German, English, French and Greek, and a document with its parsed form, green; 97 integration tests pass |
| N-121 | A passage deleted while extraction read it raised `Gone` out of the drain, as the judge did before C-136 | A row deleted (`Gone`) or claimed by another worker (`Lost`) while a drain fails or releases it is logged once as a warning naming the key and counted as no failure, so extraction's drain, `make extract` and `make corpus-hosted` take the next row instead of ending with a traceback | Red tests in German, English, Polish and Greek, and a queue raising `Gone` then `Lost`, green. An integration drain extracts the next document's passage with 0 failed |
| N-130 | Dagster's error text, the exception its storage raised, reached `GET /pipeline/runs` (the 503 detail) and `GET /pipeline` (`orchestration.detail`), both open reads, with the database's host, address and role | The orchestrator adapter logs Dagster's text under a trace id and answers with a fixed sentence naming the error's type and that id, on both reads and on the pipeline writes | Repro green. A refusal now reads, for example, `the orchestrator could not list its runs (PythonError); the api log holds why, trace <id>`, and the log holds the text under that id |
| N-131 | `make dagster-dev` ran plain `dagster dev`, which serves Dagster's webserver without `orchestration/serve.py`, so a cross-site GET could still run a GraphQL mutation on the host's UI | `make dagster-dev` is gone. The compose webserver serves the same code through `orchestration.serve`, with `compose.dev.yaml`'s source mounts on the development profile. A static test fails on any recipe, compose command, image command, workflow or script that starts the webserver another way. It reads text, so a start assembled at run time is not seen | The static test fails on v0.5.4 and passes. Starts planted in the Makefile, a script, a Containerfile and a YAML block list fail it |
| N-132 | `make ingest DIR=` read every PDF whole before the size limit applied, unlike `POST /documents`, which reads at most `MAX_FILE_SIZE_MB` plus one byte | A file whose size is past the limit is refused unread, and any other is read to at most the limit plus one byte, as `POST /documents` reads it. An oversized file with a name the database cannot store is refused `invalid_value` and the batch goes on | Red tests green. On v0.5.4 five of them fail by assertion: a 65,536-byte file read whole where 1,025 bytes are the most allowed |
| N-122 | The 2.8 s bound of `test_two_workers_on_different_languages_do_not_wait` measured the host, not whether one language's store waits on another's lock | The test asserts that the two scoring windows overlap. A second test gives both languages one lock and finds that they then do not | Passes alone and under a parallel full-suite run, and fails where one store waits on the other's lock |
| N-136 | The waits of `tests/static/test_hosted_profile.py` gave a background `make corpus-hosted` 30 s (20 and 60 s elsewhere), which a loaded host exceeded. In one random order 9 tests of the file failed, one through a process an earlier timed-out test left running | Each wait is a hang guard of 300 s, and every process a test started is reaped | The file passes alone and under both seeds that failed, 83 tests each. A run that never ends fails its own test and no other, and leaves no process behind |

### What the v0.5.5 fixes leave

The reviewers named these limits of the fixes above, and each holds on the
code of its fix.

- A figure and its unit (N-145, N-147, N-157). A unit that goes on after a
  slash still agrees with the unit alone: *5 km* with *5 km/h*, *5 m* with
  *5 m/s*, *10 kg* with *10 kg/m²*. A figure the sentence denies still
  agrees: a key *80 cm* with *Die Breite beträgt nicht 80 cm, sondern 90
  cm.* English already read both so, and German now does too. N-157 asks
  back a key's own unit in the value form only, as decided. The list and
  explanation forms are compared by the share of the key's words that comes
  back, so a unit missing from a whole sentence can pass where it is missing
  from a short key: *Der Versand kostet 5 EUR je 10 kg.* still agrees with
  *Der Versand kostet 5 EUR je 10 g.* in those forms, in German and English
  alike, while *5 EUR je 10 kg* is refused against *5 EUR je 10 g*. In the
  value form a German unit spelled out (*90 Meter* for *90 m*,
  *10 Kilogramm* for *10 kg*) or joined to the next word by a hyphen (*Das
  5 m-Kabel* for *5 m*) is refused. A German figure with one dot is read
  both as thousands and as a decimal, so a key *1.500 kg* agrees with *1,5
  kg*, as the English *1,500 kg* already agreed with *1.5 kg*.
- The arithmetic check (N-156) still reads *2000,- EUR* as a year, because
  the price dash stands between the figure and its currency. It refuses a
  sum as years only where every figure in it is a year, so a total that
  adds a year to amounts in the year band now passes: *3,950 EUR* from a
  fee of *1,950 EUR* and the *2000* of *since 2000*. v0.5.4 refused that
  total, but already let such a mix pass where an amount fell outside 1900
  to 2100.
- Number reading (N-148). A sign is read only where the tagger tags it a
  numeral, so where neither sign is tagged one, *≥ 5 °C* and *≤ 5 °C* still
  count alike; the probes found this in Polish and Greek sentences of the
  default parse, and in none of the German and English ones tried. German
  no longer reads the ASCII *+/-*, which its tokenizer splits, so *Die
  Abweichung darf +/- 0,5 mm betragen.* counts alike with the same sentence
  without it, as English already did. No stored passage or fact holds
  *+/-*, *+-* or *±*. Two amounts that differ only by their currency sign
  (*25 €*, *25 £*) count alike in the duplicate gate, as two ISO codes
  already did (*25 EUR*, *25 GBP*).
- Sentence cuts (N-152). A figure before a lower-case word on the same line
  no longer ends a sentence, so a heading that lost its line break joins
  the sentence after it: *Stand 2024 die Bank informiert.* is one sentence,
  a risk the decision accepted. A figure the parser left at the start of a
  line after a finished sentence (*(2) 3*) now joins the next line's
  clause. An all-capitals heading whose next word is also a currency code
  joins its sentence: *SECTION 12 ALL SALES ARE FINAL.*

### Closed and accepted in v0.5.5

N-110 and N-146 were closed as unreachable. No producer hands the bridge
check an index past a passage's last sentence, so N-110's input exists only
in a test built by hand; its variant on the real path is N-141. A Greek or
Polish text is refused at parse while no configuration names its language
([C-252](bugs.md#c-252-language-columns-hold-bare-iso-639-1-codes)), so
N-146's sentence never reaches the checker. 25 items were accepted, each
with its effect, its cure and what reopens it: 10 under [Failed
bar](bugs.md#failed-bar) (N-103, N-105, N-120, N-123, N-124, N-126, N-127,
N-129, N-135 and N-140), 8 of them fixes withdrawn in this release and two
whose designs were measured and never applied, and 15 under
[Cost](bugs.md#cost) (N-112, N-113, N-116, N-125, N-128, N-137, N-138,
N-139, N-141, N-142, N-143, N-144, N-149, N-150 and N-153). The bug page
holds 158 accepted items in all.

### Tests added in v0.5.5

Each track's new tests pass in three orders.

- T1, mutants. 181 tests in `tests/unit/questions` kill survivors of the
  question gates, and 84 over seven files those of planning, models,
  selection, balance and `extraction.validation`. Measured locally from a
  fresh `mutants/` on the two test branches, killed of generated: gates
  1,804 to 2,000 of 2,164, planning 237 to 245 of 253, models 60 to 68 of
  69, selection 680 to 758 of 791, balance 654 to 717 of 757, and
  `extraction.validation` 983 to 1,067 of 1,166. The six modules together
  kill 4,855 of 5,200, with 340 survived and 5 timed out, against v0.5.4's
  4,418 killed, 777 survived and 5 timed out. The Nightly on the release
  commit gives the figures of record, which replace these. Every survivor
  left is classified as killed, equivalent, a timeout, a real defect or
  unclassified with what was tried. The track's findings are N-133, N-134
  and N-135.
  <!-- v0.5.5 measure: release Nightly mutation -->
- T2, properties. 30 properties over the readers of figures, dates, units,
  ranges, references, sentence cuts, list depth and headings, in five
  languages: `tests/property` goes from 122 tests to 152. They pass at the
  `ci` and `nightly` profiles. Of the track's nine findings, N-148 to N-156,
  six are fixed above (N-148, N-151, N-152, N-154, N-155 and N-156) and
  three accepted for their cost (N-149, N-150 and N-153).
- T3, coverage. 94 tests in 26 new files over the risky branches the
  coverage report of v0.5.4 showed missed: parsing, validation, the gates,
  the draw, the export, deletion, the archive, migrations and the ports'
  error paths. The risky branches missed fall from 140 to 85. The track's
  one finding, N-146, is closed above.
- T4, order and hangs. Four random orders on v0.5.4 passed twice and failed
  1 and 9 tests of `tests/static/test_hosted_profile.py` under load, which
  is N-136. Its waits are hang guards now, every process a test starts is
  reaped, and the store-lock test asserts overlap rather than wall time
  (N-122). Five random orders on the release tree:
  <!-- v0.5.5 measure: five orders -->

## Found after v0.5.3, closed on 2026-11-04

The v0.5.3 session left four follow-ups: reference details the wiki lacked, a
Nightly that hung once for six hours, the filelock advisories accepted until
2026-11-30, and the machine's clean-up. Each ended fixed, closed with
evidence, or accepted with its reason. The wiki now carries the missing
details and matches the package READMEs v0.5.3 changed; two reviewers passed
it, with no broken link or anchor on any page. Their review also found four
repository pages that no longer said what the code does.

N-001, the filelock advisories, stays accepted in [bugs.md](bugs.md#n-001-filelock-3327-carries-13-accepted-advisories).
litellm 1.108.0, its latest release on 2026-11-04, still requires filelock
below 4.0, so `configs/audit-accepted.txt` accepts the 13 advisories until
2026-12-31, and the ten Dependabot alerts on them are dismissed as a tolerable
risk with that reason.

### Fixed in v0.5.4

| Item | Defect | Fix | Measure and bar |
|---|---|---|---|
| Nightly hang | One Every layer run on `d1694ad9` hung after its 371st test file and ran to GitHub's six-hour job limit, printing nothing about where it stopped | Each long job has `timeout-minutes`, at twice its longest recent green run rounded up to the next 10 minutes: Every layer 110, Real weights 20 and Ceilings 120 in the Nightly, Unit 60, Integration 30 and Smoke 30 in CI. Stack without mounts gets 30, so its own 15-minute wait can still fail and print the container logs. pytest's `faulthandler_timeout = 600` prints every thread's stack when a test runs longer than ten minutes. A Nightly started by hand takes an optional `seed`, which repeats a seeded order | `tests/static/test_workflows.py` pins each value, the stack option and the seed's path through `env`; its new cases fail on v0.5.3 and pass. Four local runs of the whole layer showed no hang and no stack dump: two in the hung run's order (seed 2807508786), 11,389 passed each; one with seed 3803804352, where two timing bounds failed under the load of a parallel gate run and passed alone; and one with seed 1547028867, 11,389 passed. The Nightly dispatched on the release commit with the hung run's seed is in the release notes. Closed as not reproducible, with the timeouts and the stack dump as its guard |
| Stale READMEs | `backend/question_generation/README.md` said a trigger deletes a question once its last citation is gone, and read a prompt back at a version no longer written. `backend/api/README.md` and `docs/operations.md` said deleting what was derived from a document takes only its passages and facts, and `frontend/README.md` that a re-chunk or re-extraction deletes the questions resting on it | Each page says what the code does. A question that loses a citation, its last one included, is rejected as `source_changed` and kept (migration `4a7c2e91d3b8`). Deleting what was derived from a document also deletes the questions, follow-ups and assessments resting on its passages (`delete_derived`). The read-back example names no version | Found by the wiki's two reviewers against the code; the doc tests in `tests/static` pass |

## Found by the QA pass of 2026-11-01

The QA pass after v0.5.2 put every open item into one register of 368 items:

- the open, deferred and withdrawn entries of the bug page;
- the 212 items the final review of 2026-10-22 left deferred or unfixed, and
  42 more the bug page named (`C-` and three digits);
- the root causes B1 to B30 of 2026-10-13 (`RCA-B1` to `RCA-B30`);
- one bug page entry with no other id (`K-001`);
- the filelock advisories (`N-001`), 75 findings of eight hunts over the code
  (`N-002` to `N-076`), one of the analysts (`N-077`), one of a review
  (`N-078`) and five of the walk through the production runbook (`N-079` to
  `N-083`).

Each item ended in one state. 101 were fixed, 134 closed and 133 accepted.
A fix has a test that failed before it, a bar written before its measure, and
two passing reviews. Three fixes, C-104, N-034 and N-036, read their bars on
the release commit's CI and Nightly runs, after the push: the GitHub release
notes give those results. N-035 read its bar there too, failed it and was
withdrawn. A fix that failed its bar or its third review was
withdrawn, and its item accepted: [bugs.md](bugs.md#failed-bar) gives its
numbers. A closed item was already fixed, a duplicate of another item, or no
defect on the code of v0.5.2 and later, each with its evidence.

Bars on what is written ran on two corpora, each in German and English: the
football corpus (30 PDFs of the v0.5.1 build) and the shop corpus (50
consumer-information PDFs). A replay runs the changed code over every stored
row of both. An arm writes 60 rows a corpus with the change and 60 without it
in the same round, and a reader labels them blind. "n" counts the rows a
figure reads.

The release also puts each infrastructure component behind a port, with
today's adapter as the default. [Swapping a
component](architecture.md#swapping-a-component) lists them.

### Fixed in v0.5.3: data safety and security

| Item | Defect | Fix | Measure and bar |
|---|---|---|---|
| C-106 | Document text reached the writer, verifier, phrasing and judge prompts unfenced, so a planted instruction was read as one | Those prompts send a document's text between `<material>` tags, with a tag-like opening escaped, under one line saying the text is never an instruction. Extraction, digest, bridge and topic-label prompts stay unfenced: fencing extraction too was withdrawn in v0.5.2, when it narrowed 10 of 60 facts against 7 (bar 9) | Arm with N-052, n 60 roots a side. Football, change against baseline: usable 49 against 52, keys correct 54 against 53, keys complete 50 against 56, invalid 1 against 2, conformance 0.870 to 0.974 a category. Shop: usable 47 against 48, keys correct 57 against 59, complete 47 against 48, invalid 1 against 1, conformance 0.893 to 1.0. Bar: keys correct and complete each at least the baseline minus 0.10, invalid at most the baseline plus 2 per 60, conformance at least 0.80. Holds on both; football's complete keys sit exactly at the edge |
| C-162 | Rolling back past revision `733a3eadef7c` archived every `rubric_` metric row and blocked any restore past it | The downgrade deletes the rubric rows with the archive trigger off, so none is archived and an earlier deletion can still be restored. operations.md says the scores are dropped for good | Archive and migration integration tests on Postgres: 23 of 23 pass, and the new case fails on v0.5.2. Bar: the red test, those tests and tests/static green |
| C-223 | The verifier rendered the passages four times and a thread three times | The verifier helpers that N-024 rewrote render each once. No commit of its own | Rendered prompts byte-identical to their pinned digests |
| C-257 | A queue verb's run parameter was written unquoted into a Markdown link | A run name is 1 to 80 letters, digits or `._:-` and answers 422 otherwise. The Grafana link quotes the run id, so a stored id with a bracket or a space no longer ends the link | Red tests green, with tests/unit/api, tests/frontend, tests/contract and tests/static |
| C-331 | Restored questions came back with no embedding, so a re-check skipped the duplicate veto | `make extract-embed` also writes a vector onto every question that has none, embedded from its text as the checker embeds a candidate | Integration on Postgres: 4 of 4 pass, and the new cases fail on v0.5.2 |
| C-420 | A refit's archived topics and memberships could never be restored, and they were the largest share of the archive | A refit no longer archives the topics and memberships it replaces: the archive trigger skips the tables the fit names in `qa.archive_skip`. Deleting a document or a wipe still archives memberships | Archive and migration integration tests: 23 of 23 pass, and the new cases fail on v0.5.2 |
| N-024 | The verifier's prompts were filled by chained `str.replace`, so a passage quoting a placeholder got the key under test written into it | Every verifier message, the same-answer one included, is rendered in one fill pass. A question or passage naming a placeholder is sent as written | Red test green. The 68 pinned prompt digests do not move |
| N-048 | A passage with no language was told "Write every statement in ." | The extraction message for such a passage leaves out the sentence naming a language. A language missing from the table is still named by its code | German and English messages byte-identical, so no extraction prompt digest or version moves. Reviewers: 88 of 96 rendered extraction prompts identical, the 8 others the no-language case |
| N-064 | A host command could reach no database, object store or collector but the local stack: the Makefile rebuilt their addresses from localhost after reading the env file | A host command keeps the database, backend, object store, collector, Phoenix and Argilla addresses that `ENV_FILE` or the environment names. It builds one from localhost and its published port only when it is unset. Where `DATABASE_URL` is given, the database it names must equal `APP_DB_NAME`, or every target that loads settings refuses and names both | 7 red tests green, tests/static green. Round-3 reviewer: 180 of 180 probe runs act only on the database the URL names |
| N-067 | Any web page the operator opened could launch, stop or re-trigger the pipeline through Dagster's GraphQL, by an `<img>` GET or a no-cors POST | The Dagster UI runs behind `orchestration/serve.py`. It accepts the hosts localhost, 127.0.0.1 and dagster-webserver, and answers 403 to GraphQL over GET and to a write the browser marks cross-site or same-site or that comes from another Origin. The UI's own posts and the api's calls by service name still run | Red tests green, with tests/unit/orchestration and the orchestrator contract suite |
| N-069 | A stage's unexpected failure stored the driver's own text (the object-store endpoint, the database host and role) on a row that open GETs serve | The row stores the exception's type and a trace id, at every stage and at extraction's two call sites. The whole traceback goes to the log under that id | Red test green, with tests/unit/stages |
| N-070 | An empty `APP_DB_NAME` passed every `CONFIRM` guard, and the destructive target then ran on the database libpq picks, the user's namesake | Every destructive target compares `CONFIRM` with the database `DATABASE_URL` names. It refuses, with exit 2, a URL naming no database or holding a percent-encoded database name or query key. The engine and the Alembic environment raise for such a URL | Guard cases and 4 engine cases fail before and pass after. Round-3 reviewer, 700 probe runs with nothing executed: 114 of 114 refuse without `CONFIRM`, 152 of 152 with an empty or unnamed database, 200 of 200 with mismatched names or query keys |
| N-071 | `make logs-wipe`, which `make wipe` runs, read an empty `APP_DB_NAME` as `ALL_DATABASES=1` and deleted every database's log stream without `CONFIRM` | It deletes every database's stream only under `ALL_DATABASES=1`, reads the database from `DATABASE_URL` and refuses an empty name | 2 red tests green, tests/static green |
| N-072 | Role passwords reached SQL and three more connection URLs as written: a quote broke `init.sh`'s first boot, and the doctor checked URL characters in `APP_DB_PASSWORD` alone | The init script hands each role password to psql as a variable. The doctor refuses URL characters in each of the four passwords compose puts into a URL, and names the setting | Red tests green |
| N-073 | `make setup` left `.env` and `configs/env/provider.env` readable by everyone (mode 644), with every password, `API_TOKEN`, the S3 keys, the Phoenix admin secret and the provider key | `make setup` creates both with mode 600 whatever the umask. `make doctor` warns when either is readable by group or others | Red test green |

### Fixed in v0.5.3: the swappable components

| Item | Defect | Fix | Measure and bar |
|---|---|---|---|
| C-081 | `GET /pipeline` timed out against a slow Dagster at the frontend's own 10 s | It waits three seconds for Dagster, then reports the queues with orchestration unavailable | Against a Dagster stalled 5 s it answers in under 4 s with the queue counts. Red test green, with tests/unit/api and the orchestrator contract suite |
| C-104 | The Dagster path had never carried a build, and CI never started the stack | Every GraphQL document the api sends is validated in-process against Dagster's own schema, and a renamed field fails the check. A CI job starts the stack and parses and chunks two PDFs through Dagster | 10 documents pass and a renamed field fails. Bar: that contract test, and the CI stack job green on the release commit, read on that commit's CI run. The GitHub release notes give the result |
| C-199 | Terminating a finished Dagster run was treated as a failure | Terminating reads the run's status, not Dagster's wording. A run already SUCCESS, FAILURE or CANCELED answers False, and a STARTED run that refuses is cancelled once with `MARK_AS_CANCELED_IMMEDIATELY` | Six tests with Dagster's real message pass. N-078, accepted in [bugs.md](bugs.md#n-078-a-dagster-stop-is-refused-and-the-api-answers-it-as-done), is the case where Dagster refuses before the status is read |
| C-208 | A lone closing reasoning tag was left in a reply | Inline reasoning is removed only from the start of a reply, or up to a lone closing tag that comes before the answer. An answer quoting a document that mentions such a tag is no longer cut | Eight red cases in German, English, French, Polish and Greek pass |
| C-218 | `instrument_llm`'s once-per-process flag was not thread-safe | The instrumentor is applied once, under a module lock, where eight threads at once applied it several times. The span exporter follows `OTEL_EXPORTER_OTLP_PROTOCOL` (grpc by default, or http/protobuf) and logs a refusal of any other value | Eight threads apply it once. Red test green, with tests/unit/telemetry |
| C-228 | The loop that archives a language's topic figure and model was copied three times | One function beside `TopicCatalog` archives them. The command, the route and a fit call it | 5 tests over the object-store fake, in German, English, French and Greek: the three callers archive the same keys |
| N-063 | The five bucket names were fixed in code, so `S3_BUCKETS` renamed nothing and the documented AWS path could not get its buckets | Every object-store call goes through an `ObjectStore` port. The bucket names come from `S3_BUCKETS` (names, or role=bucket), and a bucket is found by a HeadBucket per configured name, never by ListBuckets | 28 contract tests pass on an in-memory fake and on the S3 adapter, including a stand-in that refuses ListBuckets. The run against the gateway is in CI's blob integration tests |
| N-065 | An unwritable `LOG_DIR` was reported on stderr as a bare line, not on the stdout handler the docstring promised | With `LOG_FORMAT=json` stdout carries one JSON object a record, with the file's ECS fields. No file is written without `LOG_DIR`, and an unwritable `LOG_DIR` is a warning record on stdout | Seven red tests pass, with German, French, Polish and Greek messages |
| N-076 | The api took `.env.example`'s placeholder `change_me_api_token` as a real secret, and `make up` and `make upgrade` started the stack with it | The api treats a `change_me_` token as no secret: it refuses every write and settings read and logs why once. `make up` and `make upgrade` refuse to start while `.env` holds a `change_me_` value | 5 red tests and the `Authenticator` contract suite pass |

### Fixed in v0.5.3: parsing and passages

Passage bars re-parse and re-chunk the 30 football and 50 shop PDFs offline
and read every changed passage, up to 60: none may lose source text or mix
languages, and at most 2 may read worse.

| Item | Defect | Fix | Measure and bar |
|---|---|---|---|
| C-186 | A PDF whose header followed a few leading bytes was refused as an unknown type | The header is looked for in the first kilobyte, as the readers do, so a PDF behind a byte order mark or a newline a gateway put first is ingested. A header past 1,024 bytes stays unknown | Red tests green, with tests/unit/intake and the api tests. 1,024 NULs before `%PDF-` stay unknown |
| C-303 | Chunking resolved node references and listed the prose labels a second time | The chunker reads a node by reference, and the prose labels from `furniture.py` | 0 passages change on the 80 PDFs |
| C-356 | Tidying running heads took time quadratic in the pages when the head changed on most pages | The search for the heading a chapter opens on stops at the end of its page. 4,000 one-page chapters had taken 13 times as long as 1,000 | 0 passages change on the 80 PDFs. The chapters found are the old scan's on German, English, French and Greek fixtures |
| N-003 | A passage printed a list number the document does not print: a numbered paragraph grouped after lettered items read `4. 3 Die Geldstrafe ...` | A passage prints a list marker only where the document prints one. An item with none prints a dash | Passage bar: 35 passages change, all in 6 football documents, 0 on shop. 83 invented markers before, 0 after. Nothing else differs and none reads worse |
| N-004 | A passage in an unconfigured language inside a German or English document was labelled `de` or `en` and read by that pipeline | A passage surely in a language `NLP_MODELS` does not name reads no language. The reading goes line by line over every language at the document gate, and a table row or a name block counts for nothing | 2,504 passages of the 80 PDFs, same count after: 0 configured passages lose their language at the gate's 0.56, 0.7 and 0.84. Probes in French, Polish, Swedish, Dutch and Greek read none at all three. Queue integration: 74 pass, 3 fail on the first version |
| N-005 | One-page chapters on consecutive pages were read as guide words and named no chapter, so their articles lost the chapter from the trail | A one-page chapter among others in a row names its chapter when its page also holds the chapter's own heading, said by the only heading of its level on the page or by one opening on a number. A glossary of headings names none | Passage bar: 6 blocks change in 5 football documents, 0 on shop, text identical, none worse. Two articles gain their chapter |
| N-006 | A heading the converter cut into word fragments on one line headed its passages with its last fragment only, losing the article number | Fragments of one heading, on one line or wrapped onto the next with nothing between them in reading order, are read as one heading | 5 pairs joined on the 80 PDFs (articles 9 and 16 of one German regulation), the same set with each of the three spacing limits at -20% and +20%. Text identical, none worse |
| N-057 | A paragraph number printed in the left margin was read after its paragraph, so every following sentence opened on the previous paragraph's number | The margin number moves to the front of its item, found from the source words beside the item's box | Lines ending on their own margin number: 819 before, 0 after, in three football documents. 18 blocks change, 0 on shop. The word multiset of all 80 documents is identical, and every block reads better |

### Fixed in v0.5.3: facts, references and topics

Fact replays run the changed validation over the 13,716 football and 2,838
shop facts stored. The reference items read 16,272 stored facts of both
corpora. A tightening may newly refuse at most 35% correct facts. Figure
replays also read `figures()` over the 35,519 stored texts and the answer
reader over 9,663 stored question texts.

| Item | Defect | Fix | Measure and bar |
|---|---|---|---|
| C-054 | Deleting a document through the API or the pages did not replay the dedup on the production profile, where no extraction worker runs. A refusal whose twin went stayed refused (the trade-off "More citations, fewer questions") | `make corpus`, and so `make corpus-hosted`, replays the dedup for orphaned refusals after the digests and before the bridge pass | Red test green, with tests/static and the removal integration test |
| C-190 | `Ziffer 4 und 5 AGB` hid Ziffer 5 from the link pass and the bridge check | A number before a capitalised name after a document label is the section the label names, not a count. A currency code after it still counts | Link pass on football (1,924 links) and shop (429): 0 links change; no stored passage has the shape |
| C-205 | At `TOPIC_NUM_TOPICS=2` with sizing off, two passages no term tells apart failed the fit | They fall back to one topic | Red test green, with tests/unit/topics and tests/static |
| C-221 | The topic fit depended on the order passages were inserted | The fit reads its passages by document and position, not by id | Red test green |
| C-245 | `EXTRACTION_DUPLICATE_COSINE=0` also stopped writing passage embeddings | It turns only the duplicate refusal off. The stage still builds the embedder and writes vectors, and the setting's help says so | Red test green, with tests/unit/extraction and tests/static |
| C-250 | A refit placed every language's centroids, twice, in one transaction that locked every topic and fitted passage | A refit places the centroids of the fitted languages only, and only when a passage joined a topic | Integration test on Postgres: one placement statement, English centroids untouched; it fails on v0.5.2 |
| C-276 | A second `MISSING=1` bridge pass could add a bridge the first left out (QA-extraction-9). `make extract-bridge FORCE=1` dealt the pass afresh | A pass for the missing deals the links a whole pass deals, then drops those of topics already headed and of pairs a bridge rests on | The two former expected failures in `tests/property/test_bridge_reruns.py` pass. A new property test (the k-th group lost, then a pass for the missing, equals a clean pass, k 1 to 3) passes |
| N-012 | Two figures of the cited sentence traded between their kinds passed: 5 % for 12 months became 12 % for 5 months | A statement figure whose digits the cited sentences give only beside another currency, share or period is a swap and is refused | 0 verdicts change. A first version comparing every noun refused 108 stored facts, almost all sound, so the rule reads named kinds only |
| N-013 | Vulgar fractions (½ ¼ ¾) were not numbers, so 2¼ % for a cited 2½ % passed and the two counted alike in the dedup | A vulgar fraction beside a digit, one space from it or alone is read as its value by the figure reader, the number readers, the fact check and the question gates | 0 verdicts change: neither corpus holds a fraction character. The answer reader moves no stored key |
| N-015 | The bridge pass kept asking through a model outage after it had cleared the bridges, and exited 0 | A bridge pass stops with exit 75 after five links in a row the model could not answer, as a drain does. It deletes a topic's earlier bridges only once the model answers that topic's first link, and a pair's old bridge just before it writes the new one. An outage keeps the bridges of the topics it has not reached | Two stop probes (an outage after a narrowed pass, the spend cap) fail on the first version and pass. The property tests include a pass an outage stops |
| N-016 | The swap guard missed a figure lifted from an uncited sentence when no unit word stood beside it: years, clock times after "at", ages | A four-digit figure is a year only after since, seit, im, Jahr or a month name. After from, until, ab, bis, vor, nach, by, before or after a bare figure has no kind. A clock time with a colon keeps its kind | 0 verdicts change. `figures()`: 0 of 35,519 texts change; answer reader: 0 of 9,663 (the group's final replay, after N-009, N-050 and N-059 were withdrawn) |
| N-017 | A fact opening "The latter", "The former" or "Die letztere" was validated: the fact check's table lacked words the question side's table has | The fact check and the question side read one per-language table of words that point back | 0 of 16,272 verdicts change |
| N-019 | A statement whose whole subject was "Both", "Beide", "The others" or "Die anderen" was validated | Such an opening is an unresolved reference, in the modal, perfect and passive too. A singular person-generic subject (Anyone, Jeder, Man) is not | 0 of 16,272 verdicts change; 20 of 20 person-generic probes a language still validate. A first draft changed 37, almost all wrongly |
| N-020 | A fact citing a line of an `a)`, `(i)` or en-dash list in the last sentence was refused `evidence_absent`: the C-129 fix read only `-`, `*`, `•` and `1.` lines | One list-marker pattern (bullets, numbers, letters, roman numerals, bracketed or not) serves the sentence splitter, the quote check, the cited list lines and the item count | 9 of 2,518 stored passages change (7 item counts, 3 line cuts). The 10 stored `evidence_absent` refusals sit on unchanged passages |
| N-021 | The item count missed lettered, roman and en-dash list lines, so the cap's room and the index gate undercounted such lists | It counts them through the shared pattern of N-020 | 7 passages' counts change: 6 by one, 1 by two |
| N-037 | A German placeholder *es* before its zu-infinitive or dass clause was refused `unresolved_reference`, while its English twin was validated | Such an *es*, subject or object, is no reference. The clause it carries is read by its own words, so a condition holding a dass clause stays a reference | 17 stored refusals newly validated, 0 newly refused. Two readers: 14 of 17 correct (0.82) against the baseline 404 of 553 (0.73) minus 0.10 |
| N-038 | The placeholder's gender branched on the code `en`, so a configured French "Il est possible de ..." would dangle | The gender comes from a per-language table | Green with N-037's replay |
| N-042 | An amount grouped by an apostrophe (CHF 1'250.50, 1’000’000) was read as separate figures: a fact dropping the thousands passed and the faithful one was refused | A figure grouped by either apostrophe between a digit and exactly three digits is one figure for the figure reader, the number tokens and the fact check | 0 verdicts change; `figures()` and the number tokens unchanged on 35,519 texts: neither corpus prints the mark |
| N-043 | The fact check's source nouns were one mixed German and English list fitted to one corpus: "This section applies" passed as naming the document, "This clause" was refused | A demonstrative before section, clause, chapter or brochure points like any other and is exempt only where the document's own title names it. The list is gone | 0 of 16,272 verdicts change |
| N-044 | A configured Polish would crash every gate reading phrases: spaCy has no noun chunks for pl, cs, ro, hr, sl and lt either, not only ru, zh and uk | `phrases()` returns nothing where spaCy has no noun-chunk iterator | Red test green, with tests/unit/nlp |
| N-046 | An opening German *Sie* with a singular verb (*Sie gilt drei Jahre*, for die Karte) was read as the polite form wherever the passage addresses its reader, so the dangling fact passed | Such a *Sie* is the feminine third person and stays a reference | 0 of 16,272 verdicts change; 122 property tests pass |
| N-049 | A German fact moving a date to another month or weekday (1. Februar for 1. Januar) passed, because German tags those names as common nouns | Months and weekdays are read from a per-language table into their own claim field. On the cited side a range, a compound or the stem Sonn- supports the plain name, and an abbreviation counts only as the text writes one | 0 verdicts change |
| N-051 | A fact keeping a figure and changing its unit (3 weeks for 3 days, 4 g for 4 kg, 3 Jahre for 3 Monate) passed | A figure the cited text gives only beside another time unit or another SI symbol is a swap and is refused | 0 verdicts change. A first version comparing any noun refused 21 stored facts, all sound, so it reads a closed set of units |
| N-055 | The swap guard caught a period lifted from another sentence only across days, weeks and months | The time-unit table holds the whole closed class (second to year, Sekunde to Jahr) in each language | 0 verdicts change |
| N-056 | The swap guard read no kind for a currency's minor unit or a share's other spelling: 50 cents for a cited EUR 2 passed | A minor unit (cent, penny, pence, Cent) reads as its currency, and "per cent" as a share | 0 verdicts change |
| N-062 | A polite *Sie* opening a German fact was refused when an embedded clause before it had a plural subject | That *Sie* is the reader again | 0 rows change |
| N-077 | The ordinals past twelve branched on the code `en` and gave every other language German endings | They are composed from a per-language table beside the cardinals. A language with no row composes none | German and English ordinals byte-identical to v0.5.2; French, Polish and Greek compose none |

### Fixed in v0.5.3: questions, gates and the release

Gate replays run the changed gates over the 4,569 questions stored for both
corpora (3,885 football, 684 shop). Under 20 changed rows, each is read and
counted.

| Item | Defect | Fix | Measure and bar |
|---|---|---|---|
| C-036 | Follow-ups were written from the root's whole dealt sample and drifted to other documents, so many were refused `off_thread` | A follow-up is written from the facts its root cited, widened with unspent facts of the same passages | Follow-up arm, change against baseline. Share of written follow-ups refused `off_thread`: football 0 of 128 against 16 of 139 (0.115), shop 0 of 141 against 39 of 149 (0.262). Football, n 59 against 58: usable 49 against 49, keys correct 54 against 53, complete 52 against 49, invalid 1 against 1. Shop, n 60 against 57: usable 52 against 51, keys correct 52 against 52, complete 48 against 49, invalid 2 against 1. Bar: `off_thread` under 0.05, keys correct and complete at least the baseline minus 0.10, invalid at most the baseline plus 2, conformance at least 0.80. Holds on both |
| N-010 | `llm/spans.py` carried three relation fields nothing read, and its docstring promised a per-passage reading that does not exist | The fields and the promise are gone; the six relations and their meanings stay | tests/unit/llm and tests/static green, pyright clean |
| N-022 | `adds_up` refused a correct total of amounts in the millions with cents, on float rounding | The sum is compared with `math.isclose` at a relative tolerance of 1e-14 | 0 of 3,460 stored answerable keys change |
| N-023 | The count-of-citations rule read an amount, decimal, range or percentage key as a bare count and refused it as malformed | That rule and the lookup-or-sum check read a key's leading figure whole, so an amount, decimal or range is a value. A whole percentage still reads as a count | 0 of 4,569 verdicts change: the 14 stored number-of-facts refusals are bare integers |
| N-027 | `leaks_source`'s author-and-year rule refused a product or tariff named with its year (Mastercard Gold 2025) | A year after a product the tagger does not read as an organisation is no author-year citation. The rule half reads per-language tables (documents, attributions, author entities) with German and English rows alike | With N-047 and N-054: 2 of 4,569 verdicts change, both football English, shop 0. One newly admitted row is usable (1 of 1), one newly refused row unusable (0 of 1 usable) |
| N-029 | The temporal gate read German grouped amounts (1.900 EUR) and five-digit figures holding 2000 as periods | A figure counts as a period only as a whole year or a whole day.month(.year) | 0 of 4,569 verdicts change, with N-023 |
| N-030 | `make questions-rejudge` with a verifier that does not answer crashed with a traceback (exit 1) | It stops as a refused start (exit 3) | Red test green, with tests/unit/questions |
| N-031 | `make diversity BY=document` crashed with ZeroDivisionError on a workbook exported with `--no-citations` | It says, for each language, that the workbook carries no citations | Red test green, with tests/unit/assessment |
| N-039 | A question word was any token whose tag starts with W or PW, so a Dutch verb (WW) or Polish *powinien* would read as one | A question word is read from `PronType=Int` or the exact interrogative tags of the language's row (English WDT, WP, WP$, WRB; German PWS, PWAT, PWAV) | 0 of 4,569 verdicts change |
| N-040 | The question-form gate knew only the Latin `?`, so every Greek, Arabic, Chinese or Japanese question would be refused malformed | Each language's question mark comes from a table (German and English `?`). A language with no row is held to no mark | 0 of 4,569 verdicts change |
| N-045 | The language check took lingua's bare German-or-English pick, so a German question about an English-named product was refused as written in the other language | The gate refuses for language only on a sure reading, at the chunker's confidence of 0.9. A French or Polish question under German facts is still refused | 0 of 4,569 verdicts change at 0.72, 0.9 and 0.99. No stored question was refused for its language |
| N-047 | German *laut* (loud) was read as *laut* (according to), so "Wie laut ist der Staubsauger X5?" was refused `leaks_source` with no model call | *laut* as an adjective is no attribution, from the per-language tables of N-027 | As N-027: 2 of 4,569 change, one admitted usable, one refused unusable |
| N-052 | The writer prompts carried one corpus's vocabulary and gave, as worked right examples, questions the shop corpus answers | The writer and phrasing prompts give their worked examples from libraries, permits and leases, a domain neither calibration corpus covers | Arm with C-106, see its row: holds on football and shop |
| N-053 | The domain guard's word list named neither the football nor the shop corpus, so it passed the prompts N-052 names | The list names the syllabi in English and words of the football and shop corpora in German and English. A test pins that each pasted example of those corpora is caught | The guard fails 40 prompts of the version before N-052 and passes now |
| N-054 | `cites_source` refused a German question naming a directive, a guide or *gemäß der Vereinbarung* while the English twin went to the judge, and the reverse for other nouns | The rule half reads the per-language tables of N-027, with German and English rows alike | As N-027: 2 of 4,569 change, one admitted usable, one refused unusable |

### Fixed in v0.5.3: the platform, the workbook and the tests

| Item | Defect | Fix | Measure and bar |
|---|---|---|---|
| C-006 | On Linux bash a stop gave the row back at once, and a worker stopped during `make corpus` left the wait polling (the rest of C-006, FIX-R66, shipped in v0.5.2) | A second stop signal within 2 s of the first is the same stop, so the held row still finishes; only a later one gives it back. A `--wait` on a worker with pending rows, nothing in progress and no movement for the queue lease exits 75 and names the worker, so the chain stops and `make corpus-hosted` resumes later | Signals 10 ms and 1.6 s apart are one stop; 2.4 s and 3 s apart give the row back. The wait returns 75 after the lease on a fake clock, and a row in progress never gives up. tests/unit/stages and tests/static green |
| C-066 | The export built the whole workbook in the api's 512 MB and failed past about 13,000 questions | The workbook is written as it is read, in openpyxl's write-only mode, into a temporary file. The api holds a batch of questions, not the corpus | 20,000 questions peak under 2.5 times the 2,000-question peak and under 100 MB. On a copy of the build, the release export (1,273 questions, 83,069 cells) through the old and the new path differs only where intended: page numbers (2,353 of 2,353 rows), quoted formula signs (1,538 cells) and the Kind note (1). Within 330 groups of one passage, 1,750 Citations cells listed the same facts in another order, because the query left their order to the cursor; `72028444` orders them by fact id. Whole corpus, 3,885 questions: peak memory 133 MB against 366 MB. Bar: the same cells on both paths and under 512 MB at ten times the build |
| C-071 | An export of more than 65,535 questions failed on libpq's parameter limit | The judge's ids bind as one array | 70,000 ids bind as one parameter; the 70,000-question export test passes on a database |
| C-100 | The furniture filter ran a sequential scan for each candidate passage | Passages carry `nearest_foreign_cosine` and `nearest_foreign_doc`, the cosine to the closest passage of another document in the same language. Every writer of a vector, a language or a deletion keeps them exact under per-language locks taken in a fixed order, so the filter reads a column | On copies of the build and of shop upgraded with the change (`bf36e16a`), the same passages are filtered as on v0.5.2: 216 of 216 (1,973 passages) and 119 of 119 (545), 0 differences. EXPLAIN reads the column row by row with no subplan per candidate. `bridging()` 961 ms to 3.9 ms. Rescoring: 15 ms a store and 52 ms a document at 2,000 passages, 114 ms and 4.9 s at 20,000. Left, rated low by both reviewers: a delete overlapping a re-chunk of the same document that moves a passage's language, with a store into the new language, can leave one stale score |
| C-175 | A cell starting with `- ` became a live formula when edited or re-imported as CSV | Text starting with `=`, `+`, `-` or `@`, or with a tab or a return, is stored as text | Formula-sign cells quoted in German, English, French and Greek tests; 1,538 cells of the release export |
| C-239 | Kind=single held every unanswerable question, in the workbook and in `make diversity BY=kind` | The Kind heading explains what Kind holds | One heading note in the release export |
| C-240 | The Citations sheet's Page column mixed integers and text | Citations has First page and Last page, as integers | 2,353 of 2,353 rows of the release export agree as integers |
| C-241 | Nothing checked Excel's limit of 1,048,576 rows a sheet | A sheet past the limit continues in a numbered one beside it, and the diversity reader joins the parts | With the limit lowered to 3 the writer makes numbered sheets |
| C-244 | Elasticsearch health stayed yellow for good on a single node | Filebeat's index template sets `number_of_replicas` to 0. operations.md gives the one-time call for indices that exist | On the release candidate's scratch stack (`72028444`), `GET _cluster/health` read green after Filebeat's first event, with 0 unassigned shards. Bar: green after the first event on a stack started from the release |
| C-251 | Prompt versions sorted out of order (`12+cap4` before later plain versions) | The listing orders versions by the number they open with, then by the whole version. A version with no digits lists last | Unit test on the compiled ORDER BY and an integration order test pass |
| N-007 | `make ingest DIR=` died on the first file whose name is not valid UTF-8 and never ingested the rest of the folder | The ingest service refuses such a file as `invalid_value`, so the folder goes on and the command exits 1. The api still answers 400 `invalid_value` | Latin-1, cp1252 and ISO-8859-7 names between two good files: both good files ingested, exit 1 |
| N-025 | Workbook columns filled after the frame was built were cut at 32,767 characters with no mark | Every long cell is cut and marked | Long cells marked in German, English, French and Greek tests; no cell cut in the release export |
| N-032 | `make estimate` counted refused and failed documents as still to do, and projected passages, calls and spend for them | It counts documents waiting to chunk that parsing did not refuse or fail, and passages waiting for extraction, so a finished corpus estimates nothing | Red test green on the counting query |
| N-033 | The container probe leaked the docker client's socket, so a run without a container runtime failed a random unrelated test | The probe in `tests/conftest.py` closes the socket the client leaves behind, inside its own call | Red test green |
| N-034 | `make mutation` never ran a mutant: mutmut's copy lacked `configs/`, the rest of `backend/`, `compose.yaml` and the git repository the tests read | The six files are named under a link to `backend`, the copy takes what the selected tests read, and every line is mutated. A run that cannot start, or that hangs before its first checked mutant, fails the Nightly | On `planning.py`: 253 mutants, 237 killed (93.7%). Bar: one Nightly mutation run on the release commit that executes mutants for the six files and reports a score. The GitHub release notes give the result |
| N-036 | The Nightly's model quality job could never score a model: the repository had no `LLM_MODEL` variable and the job passed no provider key | The job runs only when the repository variable `LLM_MODEL` is set, so it shows skipped rather than passed, and its step receives the three Azure secrets. operations.md gives the owner's step | Static test green. Bar: the Nightly on the release commit shows the job skipped. The GitHub release notes give the result |
| N-058 | Football vocabulary sat in code comments and tests, and the regression suites pinning stored verdicts held football rows and no shop row | Backend comments use banking and retail examples, a static guard keeps the football words out of backend source, and the regression suites gain German and English shop rows | The guard passes; 4 shop question rows and 4 shop fact rows pass |
| N-068 | `make pipeline-stop` and `make pipeline-retry` exited 0 when the api refused them (401, 409, 500) and said the api was not answering | `make services`, `pipeline-status`, `pipeline-stop` and `pipeline-retry` exit non-zero and print the api's status and detail on a refusal. They say the api is not answering only when nothing connects | Four targets, three refusals and one outage, against a stub api |
| N-074 | `make doctor` passed when the api refused the host's `API_TOKEN`: the settings drift check read a 401 as an api that is not up | `make doctor` fails on any HTTP error of a reached api, naming `make up` after a change to `.env` for a 401, and warns only when the api cannot be reached | Stub 401 and 500 fail with the message; a refused connection warns |

### Fixed in v0.5.3: the documents and the production runbook

| Item | Defect | Fix | Measure and bar |
|---|---|---|---|
| C-013 | The go-live build ran through a private runner, and the documented path through the model stages was never followed | The runbook was walked on the release candidate (`72028444`) from a fresh clone, on a scratch stack with its own database, ports and volumes. Its five deviations are N-079 to N-083: three fixed below, two accepted in [bugs.md](bugs.md#cost) | Install, Docling's weights, `make up`, the schema at head and `make doctor` passed, with the split line logged and all four models answering. One German and one English football PDF and one shop PDF were ingested, and `make corpus-hosted SPEND_CAP=5` exited 0 with 10 questions released, 0 Ollama calls and USD 0.75 spent. Both workbooks came out: the release (10 questions, 15 citations) and all questions (33, 53 citations). Bar: both workbooks with no deviation left unfixed or unregistered, no Ollama call, the split line logged |
| C-093 | The go-live model split was uncalibrated at the fact stages: only the question roles were replayed on it | measurements.md names the models behind each of its figures. Every run there used `azure/gpt-5.4` and `azure/gpt-4.1`, none the split `.env.example` ships, so its extraction and digest figures are not of the production digest reader; v0.5.2's bars were measured on that split. The production split in configuration.md links the section (`0c581a95`) | Docs test red before, green after. Bar: the docs test and tests/static green |
| N-008 | The ingestion, parsing and blob-store READMEs gave object keys without the database prefix every key has carried since v0.5.2 | The ingestion, parsing, blob-store and archive READMEs give every key under the database's name, as `Bucket.scoped` stores it: `documents/{database}/{sha[0:2]}/{sha[2:4]}/{sha}.pdf`, the topic model and figure under `{database}/topics/{database}/`, and archived copies at `{database}/{origin}/{key}@{UTC time}` (`aca5194c`) | A docs test checks that `Bucket.scoped` gives such a key and that every key the READMEs print carries `{database}/`; red before, green after |
| N-066 | architecture.md and the llm README said `backend.env` sets the digest, topic-naming and phrasing models; it sets none | Both say what configuration.md says: a role's own model is set in `.env` on the host, and unset it follows `LLM_MODEL` on the host and `LLM_CONTAINER_MODEL` in a container (`75ee32c5`) | Docs test red before, green after; the architecture and llm README tests still pass |
| N-075 | The Makefile, the make guide and operations.md said `make audit` runs whole on Linux only, though it reads all three locks on macOS | The three lines are gone: the audit reads every lock with `pip-audit --disable-pip --no-deps` against OSV (`25dd90b8`) | Docs test red before, green after. One `make audit` on Darwin arm64 read the three locks: 13 accepted filelock advisories, exit 0 |
| N-081 | The runbook copied `.env` from `.env.example` without tightening its mode, so the walk left the generated secrets readable by everyone: `cp` keeps the example's mode 644, and `make setup` makes private only a file it creates | The runbook says `chmod 600 .env` right after the copy (`d00124ac`) | Docs tests green. Found by the C-013 walk |
| N-082 | The runbook omitted the Azure address and the login a hosted split needs, so the walk's first `make doctor` failed every model | The split step names `AZURE_API_BASE` in `provider.env` or `LLM_BASE_URL` in `.env`, and `az login` on the host where no key is given (`8e8d43da`) | Docs tests green. Found by the C-013 walk |
| N-083 | `make doctor` ended by naming `make dev` on either profile, which led the walk off the runbook | On `HOST_RUNNER=1` it ends by naming `make ingest DIR=` and `make corpus-hosted`, the runbook's next steps (`02629148`) | Doctor static tests green. Found by the C-013 walk |

### Closed in v0.5.3: already fixed

Each was fixed by an earlier release and is pinned by the tests named. Where
the bug page still listed a live drill, the drill is a Verify line of the
deployment, not a defect.

| Item | Defect | Evidence |
|---|---|---|
| C-001 | A re-chunk or re-extraction deleted the accepted, reviewed and released questions resting on what it replaced | Fixed in v0.5.2. Pinned on Postgres by `test_reextraction_keeps_facts.py`, `test_rerun_refuses_over_questions.py`, `test_orphan_questions_reextract.py` and the trigger tests, which failed before the fix |
| C-003 | There was no backup or restore procedure | Fixed in v0.5.2. Pinned by `test_backup.py`, `test_backup_bare_keys.py` and `test_restore_owner.py` on Postgres and SeaweedFS, and by the backup mode unit tests |
| C-008 | A language outside `NLP_MODELS` was read as German or English through every stage | Fixed in v0.5.2 at the document: it is refused at parse. Pinned by the language and intake tests; 30 of 30 football and 50 of 50 shop documents keep their language. The passage-level case was N-004, fixed in v0.5.3 |
| C-010 | Containers ran current code on the dependencies of the last image built, and a failed rebuild left them crash-looping | Fixed in v0.5.2 by the lock-hash check. Pinned by `test_lockcheck.py`; CI's smoke job builds the images |
| C-023 | Small documents and many passages got no question, and no report counted them | Fixed in v0.5.2. Pinned by the selection, export and question-queue tests. The v0.5.2 replay at 30 slots left 0 of 153 football and 0 of 119 shop documents unreached, against 9 and 24 |
| C-026 | Two extract workers could keep one claim | Fixed in v0.5.2. Pinned by `test_two_drains.py` and `test_fact_store.py` on Postgres. Two drains took 722 s against one drain's 1,268 s, with no twin |
| C-029 | The difficulty band claimed hardness and graded spread (FIX-R42). Hard answerable questions were usable 43% of the time against 61% for easy ones, and the equal-thirds release drew 83% of the hard pool | Fixed in v0.5.2: the workbook titles the band Retrieval spread. Pinned by the export and Questions page tests. A hardness grade would be a new feature |
| C-042 | A restore put back every row archived since a time, not only the deletion being undone | Fixed in v0.5.2. Pinned by `test_restore_chosen.py` and `test_restore.py` on Postgres, 8 of 8 red before the fix |
| C-048 | `make corpus` and the Dagster job fitted no topics | Fixed in v0.5.2. Pinned by the Makefile tests and the topic ensure and run tests. Dagster's corpus job still runs no bridge pass; the production profile runs `make corpus-hosted`, which does. The Dagster path is C-104's |
| C-051 | No committed file described the model split; the role models lived in the user's uncommitted edits (BL-F5) | Fixed in v0.5.2: `.env.example` ships the role models. Pinned by `test_go_live_split.py`, the split unit tests and `test_env_files.py` |
| C-068 | A duplicate refusal kept no twin id, so every replacing drain replayed the dedup over the whole corpus | Fixed in v0.5.2 (`facts.twin_id`). Pinned by the fact store and dedup tests |
| C-079 | Workers got 10 s on a stop while a row can take minutes | Fixed in v0.5.2. Pinned by the worker, stage and question command tests. C-006's fix in v0.5.3 adds the repeat-signal window |
| C-082 | More than two drains per database hit the provider's rate limit | Fixed in v0.5.2: a rate limit is waited out for its `Retry-After`. Pinned by the model client tests. On link U six drains failed 3 of 10 topics on gpt-4.1's token rate limit, so the runbook still advises at most two question drains per database |
| C-083 | Pillow 12.3.0 carried open advisories | Fixed in v0.5.2 (`6fec9bde`): every lock holds Pillow 13.0.0, and GitHub showed 0 open Dependabot alerts on 2026-11-01 |
| C-089 | The release-size scan drew once per size, about the pool squared | Fixed in v0.5.2. Pinned by the balance, release supply and release draw scale tests |
| C-095 | Weak topic memberships bound unrelated passages (3.7 topics a passage) | Fixed in v0.5.2 (`TOPIC_RELATIVE_WEIGHT`). Pinned by the fitting, fit invariant and topic property tests |
| C-117 | Hugging Face models loaded by bare repository id with no revision (QA-security-3) | Fixed in v0.5.2. Pinned by `test_model_revisions.py` and the revision unit tests |
| C-144 | `leaks_source`'s author-and-year rule refused every English date | Fixed in v0.5.2 (`f882c7a6`). Pinned by the verification tests. Spanish and French dates still read as author and year, but the parse refuses a language no configuration names (C-008). The product-year case was N-027, fixed in v0.5.3 |
| C-156 | The release draw capped every kind at its share plus the tolerance | Fixed in v0.5.2 (`ef9e81ac`). Pinned by the balance and release supply tests |
| C-169 | Deleting every document left the topics | `make corpus` refits stale topics before questions are dealt (C-048), so nothing a release reads is left. Pinned by the topic ensure tests |
| C-176 | Entity questions carried weight 0 with no recorded reason | The configuration guide records the reason since v0.5.2 |
| C-187 | A running head or foot of another edition stood as its own passage in the other language: the German PDF printed an English running foot over one of its own pages | Fixed in v0.5.2 (`d9de1ea7`). Pinned by the margin running item tests |
| C-188 | English deverbal noun phrases read as actions refused aggregation counts | Fixed in v0.5.2 (`2e1dba0d`, `92515ae2`). Pinned by the verification tests. A Spanish or French text cannot reach it: the parse refuses a language no configuration names (C-008) |
| C-196 | A build ran `EXTRACTION_DIGEST_MIN_CHARS=800` while v0.5.1 ships 500 | Not a code defect: the upgrade note is in operations.md, and v0.5.2 measured the 500 floor on the build (255 passages digested, bar about 252) |
| C-197 | Sixteen rows fixed in v0.4.4: sentence cuts, references, pointing words, bridge passes, currency fee tables, glued section numbers | Each row is in "Fixed in v0.4.4" below. What remains is carried by its own item |
| C-222 | A failed parse, or a document deleted mid-parse, left an orphan parsed object and a misleading log line | Fixed in v0.5.2 (`e4c4cdf9`). Pinned by the intake parsing and intake queue tests |
| C-226 | `Settings.thinking` re-applied `or None` | The re-application is gone from `llm/config.py` |
| C-265 | The with-premise phrasing passed on 36 rows, under the 40-row floor | A 60-row arm measured it since: 53 of 60 usable, 1 invalid |
| C-277 | Sibling linking was quadratic in Python | Fixed in v0.5.2 (`446bd50e`), with a scale test and an identical link replay |
| C-299 | The api opened every uploaded PDF with no page or time cap, and `MAX_FILE_SIZE_MB` had no ceiling | Fixed in v0.5.2 (`bd35c662`, `b8357bfb`). Pinned by the env file, intake and frontend view tests |
| C-320 | The modality and safety categories of one benchmark paper were not written | A scope limit, not a defect. The configuration guide says the default writes only out-of-corpus unanswerable questions |
| C-354 | The PPI++ weight took a free sign estimated from 17 to 30 labels | Under 30 labels the interval is now the labels' own and marked rough (C-067). The free sign above 30 labels is the user's decision |
| C-369 | The Podman VM was cut to 8 GiB (BL-F3) | The VM was resized. Database sizing is N-035's |
| C-370 | No full rebuild had run since v0.3.12 | The full build ran on v0.5.1 |
| C-372 | No category had been measured on a full build | Measured on the v0.5.1 build |
| C-373 | The v0.5.0 comparisons with DataMorgana had not run | They ran on the v0.5.1 build |
| C-422 | `unanchored` refused questions naming a set the domain fixes (*the two*) | Fixed in v0.5.2 (`53fbc640`, `5cf15e22`), with an arm passing on both corpora. Pinned by the phrasing, pointing and prompt pin tests |
| RCA-B1 | The release had no language axis and drained every cell in creation order | Fixed in v0.2.2 (language shares in `balance.py`). Pinned by the balance tests |
| RCA-B3 | Fact dedup folded a different rule into a stored fact | Fixed in v0.2.2. Pinned by the fact property test: statements naming different numbers are never duplicates. C-179 carries the different-rule refusals that remain |
| RCA-B4 | The widen retry replaced an honest one-passage draft with a weld | Fixed in v0.2.2 by removing the retry |
| RCA-B5 | The count rule refused counts a fact states and missed vacuous count keys | Fixed in v0.2.2. Pinned by the value reading tests. The written-count blind spot is C-147 |
| RCA-B10 | The same-passage dedup deleted sibling list items, and the atomic cap was 4 | Fixed in v0.2.2. Pinned by the dedup and atomic cap tests |
| RCA-B12 | `application` was always dealt two passages and told to span | Fixed in v0.2.2. Pinned by the planning tests |
| RCA-B14 | The perturbation prompt read "not stated" as "unanswerable" | Fixed in v0.2.2. Pinned by the settles and generation tests and the prompt digests. Answered unanswerable questions that remain are C-060 |
| RCA-B15 | Struck-through text was read as current law | Fixed in v0.2.2 and v0.3.0. Pinned by the strike-through tests. Short strokes are C-419 |
| RCA-B19 | `restates_question` ignored verbs, adverbs and polarity words | Fixed in v0.2.2. Pinned by the verification and typing tests. The one-word echo is C-149 |
| RCA-B21 | `compound` counted an embedded wh-clause as a second question | Fixed by v0.3.4. Pinned by the verification tests. The comma splice is C-261 |
| RCA-B23 | The boilerplate filter read a passage's translation as furniture | Fixed in v0.3.0. Pinned by the question queue and docs tests. A language held by one document is C-292 |
| RCA-B28 | `explanation_unusable` read any proper noun as a name | Fixed in v0.3.0. Pinned by the verification tests. Heading figures are C-421 |
| RCA-B29 | No gate refused a refusal used as a key | Fixed in v0.3.0: the writer declines the slot. Pinned by the generation tests |
| RCA-B30 | `asks_nothing_new` misfired on follow-ups citing an outline or summary fact | Fixed in v0.3.0. Pinned by the verification tests. The id-only follow-up check is C-180 |

### Closed in v0.5.3: duplicates

Each repeats another item. The part an earlier release fixed is in its
history below; the rest is carried by the item named.

| Item | Defect | Duplicate of |
|---|---|---|
| C-011 | One Postgres capped at 1 CPU and 512 MB served five databases and three vector indexes | N-035, accepted. The cap went in v0.5.2, and every load bar but the cold 95th percentile passed: the single-pass dedup probe's 95th percentile read 2.15x to 7.80x the build's on CI, against 2x, with the median at 6.0 to 6.9 ms. On 2026-10-26 the sizing shipped with the probe time watched. That percentile measures the runner, as N-035 records |
| C-128 | Paragraph numbers were glued mid-sentence at page breaks | N-057 and N-003, both fixed |
| C-268 | With no passage vectors, a head passage paired its compound partner by lowest id | C-245, fixed: its only trigger was C-245's |
| C-364 | Umbrella rows took their parts' states | C-094 and its parts' own items; no defect of its own |
| N-061 | The free title rule's 12-character floor flipped its verdict on the shop corpus's subject titles within ±20% | C-423, accepted |
| RCA-B2 | The duplicate gate decided on one cosine, and the release kept near-twins | C-143, accepted. The release half was fixed in v0.3.0 |
| RCA-B6 | `_contrasts` passed fake comparisons and refused sound ones | C-046, accepted. The fixed parts shipped in v0.2.2 |
| RCA-B7 | Extraction validation never checked that a fact keeps its sentence's scope | C-015, accepted. Atomic prompt 11 shipped in v0.3.0 |
| RCA-B8 | `fitting` read a two-item key as a value | C-126, accepted |
| RCA-B9 | The unanswerable checks asked only whether an answer is stated outright, over 4 passages | C-060, accepted. The 4-passage reading was replaced in v0.3.0 |
| RCA-B11 | One-document `cross` slots paired passages by reading order | C-014, accepted. The pairing was replaced in v0.3.0 |
| RCA-B13 | `reason` was planned whatever the evidence states | C-141, accepted. The planning half shipped |
| RCA-B16 | A list lost its lead-in at a chunk boundary | C-047, accepted. Fixed in part in v0.3.0 |
| RCA-B17 | Section paths were mis-parented, and running feet and index letters landed in passage text | C-368, accepted. Feet and index letters were fixed |
| RCA-B18 | `off_topic` compared an unanswerable question with one short passage's lemmas | C-154, accepted. The gate ships off |
| RCA-B20 | The round trip missed verb and noun pairs, number words and counts | C-017, accepted. The listed misses were fixed |
| RCA-B22 | `unresolved_reference` refused a pronoun its own statement resolves | C-021, accepted. The own-statement case was fixed |
| RCA-B24 | `difficulty` measured spread, not hardness | C-029, already fixed |
| RCA-B25 | The NLI rescue scored a bare fragment | C-018, accepted |
| RCA-B26 | The release read no quality signal, drained scarce buckets and let threads overdraw a kind | C-049, accepted |
| RCA-B27 | Signal-diagram labels became passage text | C-284, accepted. Hidden labels were fixed in v0.3.0 |

### Closed in v0.5.3: not reproducible, or not a defect

Each was read again on the code of v0.5.2 and later. None changes a stored
row, a release or a cost the product owes.

| Item | Defect | Evidence |
|---|---|---|
| C-163 | No list or export of one stored kind | A review convenience. Its one trap, Kind=single holding every unanswerable row, was C-239, fixed in v0.5.3 |
| C-170 | A re-parse does not re-chunk | By design and documented: a re-parse must not replace passages that released questions rest on. The re-chunk is its own guarded step |
| C-192 | An unknown stage verb answers FastAPI's own 422 | The caller gets a typed refusal and nothing is written |
| C-194 | An upload with no Content-Length is refused and not recorded | The size guard refuses a body of unknown size before reading it, as documented. The Upload page, curl and `make ingest` send a length |
| C-195 | Hallucination, toxicity and refusal score 1.0 for the bad label | The metrics' stated convention. The workbook's label column spells each verdict out |
| C-210 | A fit replaces the topic figures, and a language never drawn answers 404 | By design: a language answers 404 until its first fit draws a figure |
| C-212 | A content duplicate passes ingestion and is refused only at parsing, costing a stored file and a failed row | By design: the failed row and the kept file let the operator choose the copy, as the refusal says. The content digest needs the parse |
| C-213 | A whole-stage reclaim needs `confirm=true` | A safety check working as documented |
| C-224 | Judge calls: a root costs six, a follow-up five, a fact three | A product choice of the opt-in judge's metrics. Nothing written is wrong |
| C-225 | Enrolment ignores `--only` | `--only` narrows what is judged. Enrolling the rest costs one insert a kind and no model call |
| C-229 | Calibration databases and a dump remain inside the development Postgres container | Not in the product: about 3.4 GB on the development stack, which a production stack does not carry. Dropping them is the user's step |
| C-235 | An unanswerable slot is skipped at a topic's tail when only bridges are unspent | Unanswerable questions are written only on factoid, entity and reason slots. Each skip is logged, 2.6% of such slots, and the pool holds five times what the release takes |
| C-272 | A German *dies* after a clause is read as standing for the clause | 0 of 10 such kept facts on the v0.5.1 build were wrong |
| C-273 | "The following fees" is spared where a colon or a counting figure follows, even if the list is elsewhere | 0 of 139 such kept facts on the v0.5.1 build were wrong |
| C-274 | A bridge cannot state an aggregate | Bridges relate what is written, by design. None of 245 bridges needed one |
| C-283 | A struck word is removed without a report | Removing superseded wording is intended (RCA-B15). No row needed the old text |
| C-287 | Above 0, the chunker's split did not happen and passages are truncated when embedded | The oversized reading is 0 on the v0.5.1 build, its target |
| C-288 | A passage too short to detect a language for gets NULL | NULL is the honest label. Neither corpus triggers it and the health bar holds it under 0.5%. What a prompt does with it was N-048, fixed in v0.5.3 |
| C-291 | Chunking skips a document whose parse has not finished | The intended guard: an unfinished parse has nothing to read |
| C-294 | `questions-reverify` and `questions-rejudge` only ever reject | By design: only a person accepts a refused question |
| C-305 | The test run's `--dist loadscope` option | A test-runner option; nothing in the product |
| C-306 | One calibration link's acceptance is under another's | A comparison of two old calibration links, superseded by the v0.5.1 build's own labels |
| C-307 | No distracting questions of the Giskard kind | A feature the user deferred, not a defect |
| C-308 | A second stack was only checked with `compose config` | A verification gap on a path the production deployment does not take |
| C-310 | Caveats of link U's calibration | History, superseded by the build's own labels |
| C-312 | Homebrew's node cannot load libsimdutf, so pyright uses its own node | Host tooling only |
| C-313 | The smoke layer cannot resolve compose's file in a worktree | A developer limit in a worktree without `.env`. CI runs the smoke layer from a full checkout |
| C-317 | Parts of the ARES method were not adopted | A scope choice about the papers' method |
| C-318 | A judge may be worse in one language | No language gap beyond 0.15 was measured. The judge's agreement is C-116 |
| C-319 | Measures of the limits paper that need a chatbot | Outside the product, which writes the benchmark |
| C-321 | Chatbot-side metrics of one benchmark paper were not built | Computed by whoever runs the chatbot evaluation, outside the product |
| C-322 | Parts of the Giskard method were not adopted | A scope choice. The distracting kind is C-307 |
| C-323 | Ligatures and joiners change `content_sha256` on upgrade | An upgrade note for databases older than v0.5.1, not reproducible on one built since |
| C-324 | Topic keys moved to `topics/<database>/<language>` | Not reproducible on a database built after the move. operations.md's upgrade note covers older ones |
| C-325 | Argilla datasets made before v0.4.3 and v0.4.5 lack fields | Not reproducible on datasets made on v0.5.1 or later. operations.md's upgrade notes cover older ones |
| C-326 | A stored section path holding ` > ` keeps its old form | An upgrade note, not reproducible on a database built since v0.5.1 |
| C-327 | The first `questions-rejudge` after verifier prompt 12 costs settles readings | A documented one-off spend for databases older than that prompt |
| C-328 | `seaweedfs-ui` was removed, and an existing stack needs `--remove-orphans` | Not reproducible on a stack started without it. operations.md's upgrade note covers older stacks |
| C-330 | A rerun skips rows a worker holds, and a reclaim can take a live one | By design: the lease keeps a rerun off a live row, and reclaim is the documented override |
| C-333 | Running `make delete` twice is not a purge | By design: `archive-purge` is its own guarded command |
| C-334 | A media type with no extension raises | PDF, the only accepted type, has an extension |
| C-336 | One topic model a language, no older version, read back only by `make topics-render` | By design: a fit replaces the last |
| C-337 | A CHECK constraint repeats two fact checks | On purpose: the database refuses what the code refuses, as a second guard |
| C-338 | Alembic autogenerate ignores triggers | A developer tool's limit. Migrations are written by hand and tested |
| C-339 | `documents` is the one table two stages write | Intended: each stage writes its own columns |
| C-340 | A re-upload's filename is recorded and never shown | By design: the upload history records it, and the document keeps the name the workbook cites |
| C-342 | A settings PATCH is all or nothing | The safe contract for a settings write |
| C-343 | A setting read through a variable is invisible to the static scan | A static test's limit, with no run-time effect |
| C-344 | `ready` gates queueing, never claiming | By design: a row is checked when it is queued, and nothing reaches a worker unqueued |
| C-345 | A `make` drain refuses only while compose reports its worker running | A worker container cannot live with its engine down, and C-026's claim lock guards two writers |
| C-346 | Scaling `topic-worker` past one achieves nothing | By design: a fit is one job a database |
| C-347 | Temperature 0 is not deterministic across model versions | A stated property of hosted models. Stored rows are judged on what was written |
| C-349 | The NLP readings call no served model | A design statement that holds |
| C-350 | One abstaining metric leaves a partial verdict counted as thin | Never exercised on a build. The opt-in judge gates nothing, and counting a partial verdict as thin is the conservative reading |
| C-353 | An assessment re-run overwrites verdicts | A re-run is asked for to replace them |
| C-358 | The release's language split follows the pool | By design (RCA-B1's language axis) |
| C-359 | The context window setting serves only self-hosted runtimes | Hosted providers fix their own window, as documented |
| C-360 | No SQL spans unless set | An opt-in diagnostic, off by default because every query would be a span |
| C-361 | A register set beforehand re-checks every bug on the rebuild | A review-process decision |
| C-362 | One easiness reading for the papers | A measurement decision of the papers |
| C-367 | A stray virtualenv from a poetry call | Host housekeeping, outside the stack |
| C-415 | Leftover worktrees and branches | The user's housekeeping |

## Found by the final review of 2026-10-22

The final review of v0.5.1 read one full build (30 football PDFs, German and
English, Azure models): 0.841 of released questions usable as they stand
(1,070 of 1,273), and 19 blockers in data safety, unattended operation,
credentials and documentation. It merged every open bug of the earlier reviews
into 427 items, `C-001` to `C-427`. The fix session took 171 to fix, 49 were
already fixed, 46 ride on another fix and 161 are deferred. The conditions a
deployment has to hold are in [Production
deployment](operations.md#production-deployment). What to run on stored data
is in [Upgrading to v0.5.2](operations.md#upgrading-to-v052). A change that
failed its bar written beforehand was withdrawn.

### Fixed in v0.5.2: data safety

| Defect | Fix |
|---|---|
| A re-chunk or re-extraction deleted the accepted, reviewed and released questions that rested on what it replaced (C-001) | A passage or fact that comes back identical keeps its id. A question resting on a changed one is rejected as `source_changed` and kept. A whole-stage rerun refuses without `FORCE=1` and names the questions at stake |
| A database name exported in the shell was overridden by `deployment.env`, and destructive targets named the main database whatever they acted on (C-002) | An exported `APP_DB_NAME` is honoured. Every destructive target refuses unless `CONFIRM=<database>` on the command line names the database it resolves to, and every warning names the database and port |
| There was no backup or restore procedure (C-003) | `make backup DIR=` dumps the application, SeaweedFS, Phoenix and Dagster databases and every object with a manifest, leaving secrets out. `make restore-backup` and `make restore-backup-stack` put them back |
| Object keys were the document digest alone, shared by every database, so a delete, re-parse or purge in one removed another's objects (C-004) | Every key is stored under the database's name. A bare key from before is read as a fallback, and `make s3-prefix` copies a database's own bare objects under its prefix |
| `make wipe` and the external stores were not scoped by database, so a wipe purged every database's Phoenix projects, Argilla workspace, logs and Dagster runs (C-005) | Phoenix projects, Argilla datasets, log lines and Dagster runs carry the database's name, and a wipe deletes only its own. `ALL_DATABASES=1` takes every database's and `KEEP=runs` keeps the run history |
| A restore put back every row archived since a time, including superseded facts and cleared settings, not only the deletion being undone (C-042) | `make restore-documents AT=` puts back only the deleting transactions it names. Settings and prompts return only when `TABLES` names them |
| `make wipe` ran six irreversible steps with no preflight and stopped half way on a misconfigured store (C-087) | `make wipe-preflight` authenticates to each running store before the first delete, and the wipe skips a stopped store with one note |
| The archive grew without bound and a purge held one transaction (C-118) | `make archive-purge` deletes in committed batches of 10,000 rows, only this database's. `make doctor` prints the archive's size |
| Concurrent deletes could deadlock on the cascade triggers (C-138) | A deletion locks the facts, then the questions it reaches, in id order |

### Fixed in v0.5.2: the model path and the production host

| Defect | Fix |
|---|---|
| The containers had no hosted-model path: the question worker fell back to a local Ollama model, and every model stage ran as an unsupervised host process tied to a login (C-006) | `make corpus-hosted` runs the corpus on the host, detached, refuses a second start, resumes a stopped run with its spend, and `make corpus-hosted-stop` stops it. `scripts/corpus-hosted.sh` exits with the stage's own code for a supervisor |
| Containers ran current code on the dependencies of the last image built, and a failed rebuild left them crash-looping (C-010) | Each image bakes the hash of its lock. A container whose checkout's lock differs refuses to start, waits ten minutes and exits 78 |
| The checkout, its `.env` and the certificate keys sat in a synced folder, and a hand-made backup wrote `.env` in clear (C-012) | `ENV_FILE` names a secrets file outside the checkout. `make doctor` warns about a checkout or secrets file under a sync client's folder, and a backup copies no secret |
| The production build ran through a private runner and the documented path was never walked (C-013) | The operations guide holds a runbook that a static test checks against the commands and settings a fresh clone needs, in order |
| No committed file described the model split (C-051) | `.env.example` ships the seven role models and `LLM_REASONING_EFFORT=none`. Every drain logs the split before its first row. With `HOST_RUNNER=1` a role resolving to an Ollama model, or an unset judge with `ASSESSMENT_ENABLED` on, is refused |
| One 8-hour timeout bounded every orchestrated stage, which extraction at ten times this corpus outlasts (C-073) | With `HOST_RUNNER=1` the orchestrated path is off: `make all`, `make pipeline`, `make auto` and the pipeline routes refuse and name the host runner |
| `make corpus` fitted no topics (C-048) | It fits topics between extraction and the bridge pass where a language holds passages and no live fit |
| Every model-loading stage asked the Hugging Face Hub at run time (C-072) | `make doctor` checks the cache (each encoder at its pinned commit, and Docling's) and fails on what is missing, naming the command that fetches it. `make docling-weights HOST=1` fills the host cache |
| `make doctor` proved the models with the environment while workers ran with stored overrides (C-074) | `make doctor` asks with the settings the stored rows make and names each value that comes from the store |
| Half of the 23 containers served nothing on the production path (C-080) | Argilla, Redis, Elasticsearch, Filebeat, Grafana and Adminer sit under profiles, and the production `make up` starts eleven services |
| Builds filled the engine's disk across upgrades (C-086) | `make upgrade` checks free space against `UPGRADE_FREE_GB`, builds, prunes what the build orphaned, stops the workers, migrates and starts |
| Hugging Face models were loaded by bare repository id (C-117) | `EMBEDDING_MODEL_REVISION`, `NLI_MODEL_REVISION` and `QA_MODEL_REVISION` pin each load |
| A database password holding URL characters broke the connection string (C-201) | `make doctor` and `make corpus-hosted` refuse an `APP_DB_PASSWORD` holding `@ / : # ? %` and name it |
| `POST /pipeline/run` read a Dagster error as nothing running and launched a run (C-255) | It answers 503 |
| A queue verb answered 202 where no worker of the stage exists (C-417) | On the production profile the answer names the command that drains the stage |

### Fixed in v0.5.2: drains that stop and say why

| Defect | Fix |
|---|---|
| A drain proved its model once, then failed every row through an outage and exited 0 (C-009) | A drain exits 3 when a row failed and 75 when it stopped itself. Five unreachable-model rows in a row stop it with the rows back in the queue. `make corpus` stops at a non-zero exit |
| A failed digest call discarded the passage's atomic facts (C-041) | The facts are kept and the passage is noted. `make extract-digests` digests the noted passages later |
| Nothing bounded a drain's spend, and a model answering "nothing found" for every passage marked the corpus extracted (C-091) | `SPEND_CAP` stops every drain, the bridge pass, the release draw and the rejudge with exit 75. 25 readable passages with nothing found in the last 50 stop extraction |
| A settings change reached no stored row, and a lowered digest floor reached no stored passage (C-057) | The digest pass also digests extracted passages above `EXTRACTION_DIGEST_MIN_CHARS` that hold none. `make settings` and `make doctor` list stored rows made before a change that stales them |
| Workers got 10 seconds on a stop while a row can take minutes (C-079) | A worker told to stop finishes its row. A second signal or its stage's grace gives the row back and exits 75 |
| More than two drains per database hit the provider's rate limit (C-082) | A rate limit is waited out for its `Retry-After`, ten minutes in all per call, without spending an attempt |
| An artefact deleted while the judge read it ended the drain (C-136) | The artefact is logged as gone and the drain takes the next row |
| A call litellm cannot price was logged with no cost (C-219) | It is logged as unpriced, and a drain with `SPEND_CAP` set refuses such a model |

### Fixed in v0.5.2: parsing and passages

| Defect | Fix |
|---|---|
| Clauses the converter's bookmark pass turned into headings reached no passage: 52 of 54 such items across two regulations (C-007) | A heading that is a member of a list is read as the list item it was |
| A document in a language no configured model names was read as German or English through every stage (C-008) | The document is refused at parse and its language is named. The reading refuses only above a confidence of 0.7 |
| Titles named nothing, were cut off or collided: 14 of 30 (C-096) | A PDF is titled by the heading in the largest type, else by its cover |
| Text a reader cannot see passed every parse step (C-107) | Text in render mode 3, fully transparent, under 2 points or white on bare paper is dropped from a page whose other text paints ink |
| List nesting and column breaks assumed left-to-right scripts (C-108) | A list or column in a right-to-left script is read from the right edge |
| A few garbled pages passed the confidence floor with no warning (C-109) | Every page under `PARSING_MIN_CONFIDENCE` is named in the parse note. A blank page is not |
| A table continued on the next page was joined wrongly or not at all (C-121) | A continuation joins its table when a column sets header and data alike, when the converter flags several leading header rows, or when it is captioned |
| A running head of the other language's edition stood as a passage (C-187) | A body paragraph where three or more other pages' running items sit is treated as furniture |
| The change boxes of a rulebook produced heading-only passages (C-230) | A list item alone in its list that repeats a heading leaves the body |
| A small spaCy pipeline changed what a fact is, silently (C-348) | A small pipeline, or one without word vectors, loads with a warning naming its language |
| A letterhead named a chapter of one page (C-368) | A running item printed once on the first page names no chapter |
| A two-column page read across the gutter interleaved its columns unseen (C-426) | Such a page is named in the parse note |

### Fixed in v0.5.2: scale

| Defect | Fix |
|---|---|
| One Postgres capped at 1 CPU and 512 MB served five databases and three vector indexes (C-011) | `deployment.env` sizes the container and server for the production corpus (4 CPUs, 4 GB, `shared_buffers` 1 GB, `/dev/shm` 1 GB). The operations guide gives the table by corpus size |
| Question slots stopped growing at 40 topics a language, and every topic of a language was named in one call (C-024, C-077) | `TOPIC_NUM_TOPICS` ships at 300 and topics are named 25 to a call. `make topics-name` names what a fit left unnamed |
| Two extract workers could keep one claim twice (C-026) | The store takes a lock per language and kind and judges the passage's facts again under it |
| Term links grew with the square of the corpus (C-027) | A term links passages only if it is rare (at most 0.5% of a language's passages, never more than six), and each passage keeps the eight partners it shares most with |
| Nothing bounded a document's pages before conversion (C-076) | `PARSING_MAX_PAGES` (180) refuses a longer document before conversion and names its page count |
| There was no sizing guide for a large corpus (C-084) | `make estimate` prints the time, calls and spend of the rows still to do |
| The release scan drew once per size, about the pool squared (C-089) | The scan starts where the pool can place the release and steps down in strides of a hundredth from 2,000 rows, by ones below. A draw reuses its cells |
| Every dedup probe joined the citations, so the vector index was never used (C-090) | A fact carries its language (`facts.language`), so the probe uses the index |
| The bridge pass held every vector as Python floats and parsed each passage twice (C-099) | It holds float32 arrays and parses each passage once |
| A compound slot that found only bridges abandoned the rest of the topic's plan (C-236) | The slot is passed over and the later slots are written |

### Fixed in v0.5.2: facts

| Defect | Fix |
|---|---|
| `unsupported_addition` refused sound facts because only the cited sentences counted as support (C-020) | An atomic fact is supported by its whole passage. A figure only the rest of the passage gives is still refused where a cited sentence states another of the same kind (a currency, a share, a period) |
| `unresolved_reference` refused facts whose demonstrative names the document itself, such as *these regulations* under a title that says so (C-021) | A demonstrative names the document when its noun is the head of a title line or the last part of that head's compound |
| `not_atomic` refused a German rule whose verb-final clause carries its condition or exception (C-019) | A verb-final clause after a comma and *und* goes on with the clause before it when that clause is subordinate and more than one constituent stands before its verb |
| `not_atomic` refused a bridge's contrast or limit (C-033) | A bridge whose relation is a contrast or a limit may carry two claims |
| The entailment encoder cut a long passage at 512 tokens without saying so (C-065) | A long premise is read in overlapping windows of sentences |
| A duplicate refusal kept no twin id, so every replacing drain replayed the dedup over the whole corpus (C-068) | `facts.twin_id` records the twin and is set NULL when the twin goes. The replay reads only refusals that lost their twin |
| Long list passages never got a digest because the floor counted claims and a list is one sentence (C-098) | The floor counts claims and list items together |
| `make extract-revalidate` rewrote every fact row (C-111) | It reads in batches and writes only the facts whose verdict or spans changed |
| `evidence_absent` refused list lines inside the passage's last sentence (C-129) | A citation one past the last sentence names a line of it when that sentence holds two or more list lines |
| A passage's outline was refused as a duplicate of its own summary (C-137) | An outline and a summary are never twins. Stored refusals of the kind come back through the dedup replay |
| A fee table in a currency beyond EUR, USD, GBP and CHF was read as an identifier grid and skipped (C-416) | A currency is an ISO 4217 code, any currency sign, or the language's own word |

### Fixed in v0.5.2: questions, topics and the workbook

| Defect | Fix |
|---|---|
| A why-question planned unanswerable was refused as answered on a quote that states only the rule (C-022) | The settles reading takes such a quote as silent (verifier prompt 15) |
| Small documents got no question: 9 of the 30 PDFs (C-023) | The deal gives each document of a topic its share first, and every document a sample before any gets a second. `make questions-status` counts the documents and passages no accepted question reaches |
| The writer wrote questions that need the document to make sense, or that read two ways (C-037, C-038) | Writer prompt 32 tells every writer the reader never sees the passage, and tells an answerable writer to put the case that makes its key the only answer into the question |
| The self-contained judge refused a question naming a set the domain fixes, such as *the two* (C-422) | The judge is shown definite sets and a repeated noun (phrasing prompt 5) |
| Topics bound unrelated passages through weak memberships (C-095) | `TOPIC_RELATIVE_WEIGHT` (0.5) keeps a membership only at least half the passage's strongest, replacing `TOPIC_MIN_WEIGHT` |
| A refit deleted the topics a question worker held and sent every topic back to be asked again (C-055) | A refit keeps a generated topic that is an old one with no new passage. A fit or topic delete refuses while a topic holds a live question claim |
| A workbook row did not stand on its own (C-102) | The Questions sheet gives each row its earlier turns and its source (document, pages, section path) |
| The workbook named the difficulty band hardness, and its Summary named no judge (C-029, C-135) | The band is titled Retrieval spread. The Summary names the judge's model and template, counts by language, and says its counts are not a quality estimate |
| An English date read as an author and year leaked the source (C-144) | A date the entity reading marks is not a citation |
| A deverbal noun phrase in a value key read as an action (C-188) | A participle inside a noun phrase is not read as an action |
| A follow-up was stored `needs_both` under a root narrowed to one passage (C-363) | A follow-up is dealt the kind its root was stored as |
| The parts reading never ran on derived questions (C-034) | A derived question citing two passages is read by parts like any `needs_both` question |
| Space-grouped amounts with a marked currency or a price dash were split into two figures (C-052) | Such an amount is one figure, before or after any currency sign |
| A compound question's halves were not stored (C-053) | Both halves are kept in `gate_scores` |

### Fixed in v0.5.2: platform, security and tests

| Defect | Fix |
|---|---|
| The API took every write from anyone who could reach it, and the page could point the local models at any repository (C-085) | Every write and every read of `/settings` carries `API_TOKEN` as `X-API-Token`, which `make setup` generates. `QA_MODEL`, `NLI_MODEL`, `EMBEDDING_MODEL` and `DOCLING_ARTIFACTS_PATH` are fixed settings |
| Any web page the operator opened could trigger the costly reads (C-202) | A cross-site request is refused on every method |
| Error paths sent the database's host and role to the caller (C-139) | An unhandled error is answered with one fixed sentence and logged in full |
| Whole-stage reruns and `DELETE /topics` acted on one click (C-040) | They need `confirm=true` and name what is at stake, and Redo asks first |
| The API opened every upload with no page or time cap (C-299) | `MAX_FILE_SIZE_MB` is bounded at 150. A PDF over `PARSING_MAX_PAGES` or read past `PARSING_TIMEOUT_SECONDS` is refused and the setting is named |
| The Upload page took any number of files into memory (C-114) | It refuses more than 20 files or 200 MB and names `make ingest DIR=`, which loads a folder from the host |
| The judged sample represented neither the pool nor the release (C-059) | Each stratum is sampled in proportion to its size, from the released questions once a release exists |
| A label defined on only part of the judged rows was corrected over all of them (C-039) | Rows labelled `na` leave both counts |
| The PPI interval was asymptotic and per row (C-067) | Under 30 labels the interval is the labels' own Wilson interval. From 30 it is the corrected interval with a t quantile, or the rule of three where the labels leave no spread |
| The diversity tables pooled languages by judged rows, named the wrong predictor, put unanswerable rows under single, read any extra field as a label and cut long labels (C-237) | Each is corrected. The workbook's note on what Kind means waits for v0.5.3 |
| Phoenix kept every prompt and passage for ever (C-103) | `make up` sets the default trace retention to `PHOENIX_TRACE_RETENTION_DAYS` (30), beside the per-database purge |
| A migration ran in one transaction with no lock or statement timeout (C-075) | Each revision is one transaction with a 5-second lock timeout and a 10-minute statement timeout |
| `make confidence-recalibrate` locked every question and fact for its run (C-078) | It reads without a lock and writes back in guarded batches of 300 |
| A deletion through the pages or the API did not replay the dedup (C-054) | Every deletion says how many duplicate refusals lost their twin, and an idle extraction worker replays the dedup whenever a refusal points at no twin |

### Fixed in v0.5.2: the documents, dependencies and what the release's own checks found

| Defect | Fix |
|---|---|
| No repository doc carried the production conditions, and three docs scaled `extract-worker` to four (C-425) | Production deployment lists the conditions, each with its item and what lifts it, and nothing scales `extract-worker` past two |
| Pillow 12.3.0 carried advisories fixed only in 13.0.0 (C-083) | The images ship Docling 2.142.1, docling-core 2.104.0, docling-parse 7.23.0 and Pillow 13.0.0 |
| `make corpus` with an exported `APP_DB_NAME` ran its drains on `deployment.env`'s database | `make corpus` and `make corpus-hosted` take the database from the command line or the environment, like every host command |

## Found by the papers programme of 2026-10-22

Before v0.5.0 shipped, every open item was listed (236) and ranked by what it
would do to a large build. The full build after v0.5.0 found two defects at
its start.

### Fixed in v0.5.1: the full build's start

| Defect | Fix |
|---|---|
| The Dagster webserver and daemon, `make dagster-wipe` and `make wipe` failed to start, because SQLAlchemy 2.1 reads a bare `postgresql://` as psycopg 3 | The storage URL names `postgresql+psycopg2`, the driver dagster-postgres installs |
| A split pairing a reasoning writer with a verifier, judge or phrasing model that does not reason failed every call of the latter | The reasoning effort is not sent to a hosted model that litellm knows does not reason. An unknown model still gets it |

## Found by the finalize review of 2026-10-21

A third review took the 269 items open at v0.4.2 (177 confirmed, 66 already
fixed, 8 refuted, 8 wrongly stated, 10 transferred to the DataMorgana paper
features) into v0.4.3 (questions), v0.4.4 (reading documents) and v0.4.5 (API,
frontend, stack).

### Fixed in v0.4.3: questions

| Defect | Fix |
|---|---|
| A compound slot planned hard kept the band hard, though a compound question is always banded medium (QAB-qg-plan-2) | A compound slot is planned at the medium band its kind fixes, and a declined slot written as another type takes the band its kept shape reaches |
| A follow-up on a compound pair was stored `needs_both` (QAB-qg-plan-8) | A follow-up is stored `needs_both` only where its root was dealt `needs_both` |
| A compound partner's facts were ranked toward the head, and a partner whose closest fact was a bridge offered nothing (QAB-qg-plan-7) | A compound partner offers its own facts in its own order |
| A second passage could offer a word-for-word copy of a fact already offered, and a compound partner could copy the head (FIX-R103) | No second passage offers a word-for-word copy of an offered fact, and a compound partner is never a copy of the head |
| A two-passage reading could hold nine facts, past its ceiling of eight (QAB-qg-plan-10) | Each later passage is left room under the ceiling before the head's list is filled |
| A premise's own *When*, or a *which* or *wo* opening a relative clause in it, typed the question (NEW-qg-plan-3) | A question opening on a premise is typed by the question word that asks: the first one outside a relative or adverbial clause |
| An amount written with spaces (`5 000 Euro`, `EUR 100 000`) was read as two figures, so a right total was refused (NEW-release-1) | An amount grouped by spaces is one figure where a currency code, symbol or word stands beside it. A table row or phone number keeps its separate figures |
| The pronoun *one* counted as a second number, so an aggregation was relabelled `factoid` (VAR-number-readings-1) | One predicate, `is_number`, decides what a number is everywhere |
| A count of the items one cited fact lists was stored as an aggregation (FIX-R127) | A count is stored as a factoid when the fact the question asks about lists that many items, and nothing is refused for it |
| A German keyword query typed in lower case lost every noun to the gates (BL-B2) | A text with no capital after its first word says nothing by its case, so the gates read its nouns. A lower-case query holding one capitalised word is read as written |
| An answerable question with no explanation passed (FIX-R105) | It is refused as `explanation_unusable`. A stored row read without an explanation still passes |
| With three cited passages the check lost a part that two other passages share (FIX-R169) | A question citing three or more passages keeps, besides the passages holding a part of their own, the first passage holding each part they leave uncovered |
| A circular reason key, the rule restated as its own reason, passed (BL-B5) | The round trip's read also says whether the passages give a reason beyond the rule, and a question with none is refused `not_recoverable` (verifier prompt 12) |
| A question reworded until it asked something the passage does not say was mapped back to the passage (BL-B12) | The read answers only where the passages answer the question as asked, and a drifted question is `not_recoverable` |
| The aggregation prompt invited counts of the facts the writer was handed (BL-B3) | The prompt says a count is of the figures or items the facts state, never of the facts themselves (writer prompt 28) |
| Questions about a case study's sample person, a phone number or a page's legend passed every gate (BL-B9) | The writer is told that a person or story in the material illustrates a rule, and to ask about the rule, never about a contact box, legend or list of changes |
| With-premise questions opened on a scene label such as *Beim Spiel:*, and a premise could give the answer away (BL-B6) | A with-premise category asks for a premise in which the asker states, in the first person, a fact of their own situation. A premise with no first- or second-person word is written once more with a note |
| The wording of distant-from-document, expert and long-search-query produced bad questions (BL-A-distant) | Distant keeps every term's meaning and coins no word. Expert is described by what an expert asks. Long-search-query is keywords with no question word |
| A search query was told on a slot that cannot be asked in keywords (BL-A-short-query) | A search query is not told on a slot that spans two passages or on a type whose question word is the ask (reason, comparison, implication, change over time) |
| distant-from-document drifted from the passage's meaning, and the default dealt no linguistic variation (BL-A-distant) | The default deals Linguistic variation {similar-to-document, distant-from-document} at even odds beside Phrasing and Premise |
| A short search query that another passage answers differently was accepted (BL-A-short-query) | A short query is read once more against the nearest passages it does not cite, and refused as `not_recoverable` where one of them answers it differently |
| The quality report, the Questions page, the API and the workbook Summary did not count the kind or the categories (NEW-api-frontend-export-2) | The report counts each kind and each category, and the three surfaces read those counts |
| A question's categories reached neither its Argilla record nor the Questions page, and a keyword query was judged as malformed (NEW-api-frontend-export-3) | Categories reach both, and the guideline judges a search query as a query. A dataset made before v0.4.3 must be recreated to carry them |
| A control character in exported text failed the whole workbook with a 500 (QA-api-frontend-1) | Control characters are dropped from every cell of every sheet |
| The release was sized by its scarcest kind, which asked for its whole share at every size and capped the release | A kind short of its share is capped at the rows a release can take of it. Its places go to other kinds by largest remainder |
| The release draw overshot its quotas with follow-up questions | A thread ends at the first turn whose band, kind or language has no place left, and later turns go with it |
| The release could hold twins the verifier never judged (FIX-R3) | The draw after the last twin round is read for twins once more, and the last round drops the later-ranked member of each pair with its thread |

### Fixed in v0.4.4: parsing and chunking

| Defect | Fix |
|---|---|
| A scanned page carrying one stamped line, such as a merge tool's `Seite 2 von 3`, was not named, so its text went missing without a warning (NEW-parse-chunk-2) | A page with no more than `PARSING_OCR_CHAR_THRESHOLD` characters (100 by default) under pictures covering at least half of it is named as image-only in the parse warning and `documents.parse_error` |
| Bidi marks, isolates and C1 controls survived text repair, so a model's quote of a phone number or opening hours matched nothing in the passage (QAB-preprocessing-10) | Every format character is dropped, and a C1 control is read as the cp1252 character it stands for |
| A table label wrapped over three lines lost its last line to the next row's label or left a row with no price (VAR-parse-text-1) | Each tail joins the nearest row still standing |
| A body line opening with the running foot's name, an imprint or a contact line was moved to the furniture layer whole (QAB-preprocessing-7) | A paragraph is furniture only when it is the running head or foot itself. A line that goes on past the foot's name stays passage text |
| A lone integer anywhere on a page was dropped as a page number, which lost values such as a notice period printed under its label (VAR-chunk-structure-1) | A lone integer is a page number only in the top or bottom tenth of its page and where the document's page numbering supports it |
| A sentence cut at a page or column break before a capitalised word stayed two half sentences (FIX-R101) | The two halves join when the tagger reads the first as ending on an article, preposition, conjunction or auxiliary and the second as opening with a noun |
| Text above a mid-page chapter opening was filed under the new chapter when the heading is spelled unlike its running head, such as `B. Geschäftskunden` against `Kapitel B:` (NEW-parse-chunk-3) | Headings and running-head fields are compared on their letters and digits |
| A lead-in left at the end of a list item by a page join (`bestehen, wenn:`) reached none of the list's pieces (FIX-R100) | A list item ending on a colon is a lead-in too and heads the list after it through the heading trail |
| A heading holding ` > ` (`Orders > 50 EUR`) was split in two by every reader of the section path (QAB-preprocessing-8) | A ` > ` inside a heading is written ` › `, and the path is read back with each heading as printed |
| A footnote the converter attaches to a picture, such as an offer's conditions under a banner, reached no passage (NEW-parse-chunk-4) | A picture's footnotes are written beneath its caption, as a table's are. Text nested inside a picture stays out |
| A list in two languages under one heading became one passage filed as one language (NEW-parse-chunk-5) | List items are read too, so a run of items that changes language ends the chunk |
| A running head or foot parted by a dash, middle dot or bullet between spaces was one field that numbers pages, so no chapter was read from it (QA-parse-chunk-1) | It is split at an en dash, em dash, middle dot or bullet between spaces, never at an ASCII hyphen |
| A short sub-heading that a chapter's running head holds, such as `Fees` under `Fees and charges`, was taken for the chapter's opening (QA-parse-chunk-2) | The heading and a field are compared word for word, and a field shorter than two letters or a bare numeral never opens a chapter alone |
| A sentence cut at a page break before a figure (`für die ersten` over `12 Monate kostenlos`) was never joined (QA-parse-chunk-3) | The cut is joined where the word before it cannot close a clause (an article, preposition, conjunction, or an adjective behind one) |
| A bullet with no full stop at a page foot absorbed the next page's paragraph when that opened on a name such as iPhone or eBay (QA-parse-chunk-4) | Only a run of letters all in lower case opens in lower case |
| A ligature (U+FB00 to U+FB06) was stored as written, so `Kontoeröﬀnung` and `Kontoeröffnung` were two words (QA-parse-chunk-6) | Ligatures are spelled out as their letters. A document holding one gets a new content digest, which `make parse-rerun` writes |
| The zero-width joiners of Persian, Indic, Khmer, Myanmar, Tibetan and emoji sequences were dropped (QA-parse-chunk-7) | A joiner is kept between two letters or marks of a script that joins with it, and inside an emoji sequence |

### Fixed in v0.4.4: fact validation, extraction and the link pass

| Defect | Fix |
|---|---|
| A sentence ended after an abbreviation that never closes one, such as `incl.` before `VAT`, and after clause or weekday abbreviations the table lacked (QAB-llm-nlp-3) | The table is split into abbreviations that end no sentence (`incl.`, `cf.`, `Ziff.`) and those that may end one only before a capital |
| A German fact opening on polite *Sie* was refused `unresolved_reference`: 19 German facts of the shop calibration base (NEW-extract-nlp-1) | The fact check passes the cited passages to the reading, and an opening *Sie* names the reader where a passage holds a polite form inside a sentence |
| A fact pointing outside through a modifier such as *such a card* or *the following fees* was validated (VAR-bridge-prompt8-1) | Two tables of anaphoric and cataphoric modifiers are read on the noun before the first finite verb, as an opening demonstrative is |
| A German *dies* after a free relative clause (*Wer die Karte verliert, muss dies sofort melden*) was refused (VAR-dies-free-relative) | A finite verb with a question word under it is a clause *dies* may stand for. *dies* after a relative clause on a noun is still refused |
| A narrowed `make extract-bridge` pass deleted a sibling or term bridge headed outside its scope and never wrote it back (QA-extraction-9) | A bridge records the passage that headed its link. A narrowed pass clears only bridges headed in its scope |
| A hold on pairs the link pass would not offer still changed what it dealt, so narrowed passes dealt other links than a fresh one (FIX-R168) | The pass deals as if nothing were held, then moves only a dealt link on a held pair to its head's next free link |
| The bridge check missed a passage's numbered heading named second in a list, such as *Sections 7 and 9* (NEW-extract-nlp-2) | One reader, `numbered` in `validation.py`, serves both. *Sections 7 and 3* names both sections |
| A single-quoted heading ending in a possessive (*‘Customers’ fees’*) was cut at the apostrophe and linked to nothing (VAR-link-references-1) | A single-quoted span is read on to a later closing mark on its line where that longer span is a heading |
| A figure ending a German sentence (`EUR 5.`, `Ziffer 3.`) opened the next sentence as if it numbered an item, so facts citing the sentence were refused `unsupported_addition` (QA-extraction-1) | A figure after a word or abbreviation finishes its sentence. Only a number opening its line numbers an item. A stored passage takes this through a re-chunk |
| An abbreviation in the tables still ended a sentence after an opening bracket or quote, as in `(cf. Section 4)` (QA-extraction-2) | A word's leading marks are stripped before the tables are read |
| A price abbreviation ended a sentence before a lower-case word, as in `2.5% p.a. on all balances` (QA-extraction-3) | `p.a.` and `mon.` are closing abbreviations, and a word joined by a slash ends on its last abbreviation |
| A German fact opening on an inflected pointing modifier, such as *Nachstehende Bedingungen* or *Besagter Kunde*, was validated (QA-extraction-5) | The tables are read with German adjective endings stripped as well |
| A fact opening on a back-pointing modifier no table held, such as *the above fees* or *die vorstehenden Bedingungen*, was validated (QA-extraction-6) | The three join the table. A modifier is also read joined to the word before it (`above-mentioned`), and only before its noun |
| A fee table whose amounts carry a currency code (`EUR 5`, `CHF 10`) was skipped whole as a grid of identifiers (QA-extraction-7) | A cell whose letters are a currency word of its language is a value, as a bare figure is. `make extract-rerun` reads passages skipped before |
| A section number with its subsection glued on, such as `Section 7(2)` or `§ 7(2) AGB`, named no section (QA-extraction-8) | A token opening on a section number before a bracket names that section, for the link pass and the bridge check |

### Fixed in v0.4.4: topics

| Defect | Fix |
|---|---|
| Two identical passages could get different topic memberships (QAB-topics-3) | The fit reseeds the projection for each passage, so its weights depend on its vector alone |
| A language with one passage, or only copies of one text, failed every fit, and its facts reached no question unit (NEW-topics-2) | A language whose passages are one text, or cannot be told apart and are too few for a second topic, gets one topic holding them |
| A topic dominant in no passage was sent to the naming model with no excerpt, and `TOPIC_LABEL_MIN_FACT_SHARE` could never fire (QAB-topics-4) | A topic is named only where it is some passage's strongest. `TOPIC_LABEL_MIN_FACT_SHARE` is removed |
| The naming model's "no subject" answer was recognised only as the words *Mixed* and *gemischt* (NEW-topics-3) | The answer carries a `no_subject` field the model sets, in any language (topics prompt 3) |
| The ending most topic names share was stripped even where that left a dangling preposition (*Fees for*) or a lone modifier (NEW-topics-1) | An ending is removed only when it is a prepositional phrase whose first word the language's pipeline tags as an adposition |
| Topic figures and models were keyed by language alone, so a second database on the same object store overwrote production's on its fit or delete (NEW-topics-5) | Both are stored under `topics/<database>/<language>`. A `DATABASE_URL` that names no database is refused. An upgraded database runs `make topics-d…` to rewrite the keys |
| A refit after a language's last document left that language's figure and model in the store, and the figure route served topics that were gone (QAB-topics-5) | The languages whose topics a refit deletes are read first, and their figure and model are archived |
| A word holding a closing script tag, kept as a lemma from an uploaded document, ended the topic map's data script (QA-security-1) | The page writes `<`, `>` and `&` in the data as JSON escapes |
| With `TOPIC_PASSAGES_PER_TOPIC` at 0, a language whose few passages could not be told apart still failed the refit | With the sizing off, a language with fewer distinct passages than `TOPIC_NUM_TOPICS` that cannot be told apart gets one topic |

### Fixed in v0.4.4: the archive, the database and operations

| Defect | Fix |
|---|---|
| A restore could bring a follow-up back released under a root that had left the release (NEW-ops-docs-1) | A restored follow-up keeps its release only under a turn that is still accepted and released in the same release. Otherwise it and every turn below it come back accepted but undrawn |
| The image locks had drifted from `poetry.lock`: 30 shared pins differed, among them pandas 3 against 2.3, protobuf 7 against 6 and Docling 2.132.0 against 2.137.0 (NEW-ops-docs-5) | `make lock` resolves both image locks under `poetry.lock`'s pins, and a static test holds every shared pin equal. The API image runs Docling 2.137.0 |
| The host `poetry.lock` was not audited, so `make audit` stayed green while Dependabot flagged aiohttp there (BL-D6-ops) | `make audit` reads `poetry.lock` too and fails after reading all three locks |
| A command-line value holding `( )`, `&` or a quote, such as `OUT="/tmp/Q&A (final).xlsx"`, failed every target that loads the environment with a shell syntax error (QA-ops-docs-1) | Each command-line variable is exported single-quoted with its own quotes escaped |
| A command-line value holding spaces named its later words in `QA_COMMAND_LINE` as settings a stored row gives way to (QA-ops-docs-2) | `QA_COMMAND_LINE` names only the variables whose origin is the command line |
| `make spend` and `make spend-by-shape` given a `LOG` that names no readable file printed "no priced calls in the log" and exited 0 (QA-ops-docs-3) | Both refuse a missing, unreadable or directory `LOG` with exit status 2 and name it |
| `make audit` read PyPI's advisory service, which lists 18 of the 21 advisories OSV holds on Pillow 12.3.0 and omits a critical one (QA-ops-docs-5) | Every lock is read against OSV. The make guide says the audit runs whole on Linux only, as the nightly job runs it |

### Fixed in v0.4.5: API and settings

| Defect | Fix |
|---|---|
| A setting, topic label or upload filename holding a NUL or a lone surrogate answered a 500 from the database (QAB-api-settings-1) | Each is refused at the edge: `out_of_range` for a setting, 422 for a topic label, 400 `invalid_value` for a filename |
| `EMBEDDING_MAX_TOKENS` accepted 1, which cuts every passage to nothing (QAB-api-settings-5) | The floor is 64 |
| Stop asked Dagster for one page of runs, so a run past it was never stopped (QAB-api-settings-7) | Stop asks for every unfinished run |
| `GET /pipeline/runs` took a limit with no bound, and a Dagster refusal answered 503 `no_orchestrator` as if Dagster were down (QAB-api-settings-8) | The route takes a bounded `limit`, and a refusal answers `orchestrator_refused` |
| The arrivals sensor retried a failed run on every tick (QAB-api-settings-9) | It retries once, then skips and names `make pipeline` and the Run button |
| The orchestrator accepted `nan`, negative and near-zero drain timeouts and poll intervals (QA-security-4) | Its reader takes finite values of at least one second |

### Fixed in v0.4.5: frontend and review

| Defect | Fix |
|---|---|
| A search longer than the 200 characters the listing routes take replaced the page with `Failed to load: 422` (QAB-frontend-review-10) | Every listing's search box holds at most 200 characters, and a static test holds it to the API's bound |
| The Topics search looked in terms joined by spaces while the table shows them joined by commas, so terms copied from the table found nothing (QA-api-frontend-4) | The search looks in the terms as the table shows them, and in the label and the terms each alone |
| A topic name longer than the 120 characters `PATCH /topics` takes was cut to 120 when somebody saved only the coverage choice (QAB-frontend-review-8) | The page sends the name only when it was edited. A pull leaves a longer corrected name in Argilla and logs the topic ids |
| A document's filename went into its panel heading as HTML, so `Konditionen <Entwurf> & Preise.pdf` showed a name no document has (QAB-frontend-review-12) | The heading escapes it |
| A filename was read as Markdown in the Delete question, the spinner and the upload messages, so a name could appear in italics right before an irreversible delete (NEW-api-frontend-export-1) | `page.plain` escapes every ASCII punctuation mark, and the filename goes through it in each place |
| The *How this was produced* fold drew each artefact's text as Markdown, so `$4.99 ... $20` read as math (QAB-frontend-review-11) | The artefact's text and the stage's reason go through `page.plain`. The links do not |
| Accept or Reject pressed for a question that had left the listing was dropped with the message *That row changed meanwhile.* (VAR-press-lost) | The caption names the row. No verdict is applied to a row that has left, because someone else, the gates or a release moved it |
| A compound slot written single for want of a second passage was shown with the spanning prompt it was not sent (VAR-review-kind-2) | The prompt fold says such a slot is stored single and was sent the plain prompt of its type |
| A second fact push before a pull offered the facts already answered in Argilla again (QAB-frontend-review-14) | The fact push leaves them out too |
| The facts review dataset carried no language, though the topic and question datasets do (QAB-frontend-review-15) | A fact record carries the language of its cited passage (`unknown` if none) as `language` metadata. A push to a dataset made before v0.4.5 warns that it is stale |

### Fixed in v0.4.5: the stack and tests

| Defect | Fix |
|---|---|
| A fresh clone switched to a hosted model still sent the Ollama address as the model's base URL (QA-move-2) | The address is dropped when the model is hosted and equals `OLLAMA_BASE_URL`. A gateway address is kept |
| Three model roles shipped pinned to an Ollama model the README never named and `make doctor` never checked (QA-move-3) | `make doctor` asks every model a stage calls, the judge only while the assessment is on, and the README names the three roles |
| A second checkout's images overwrote or reused the first's, and the smoke layer assumed Dagster on port 3000 (QA-move-5) | Image names follow the compose project, and the smoke layer reads the Dagster port from the env |
| `seaweedfs-ui` was a service nothing needed (FIX-R68) | The service, its Caddyfile and its catalogue row are deleted. On an existing stack `up -d --remove-orphans` removes the old container |
| There was no documented hosted-only path to a dataset, no way to run a second stack, no Podman VM size and no ingest step outside the frontend (QA-move-1) | The README and the operations guide document each |

## Found by the QA review of 2026-10-20

A second review read the v0.3.13 to v0.3.27 code: 107 entries (103 rated
findings: 3 high, 47 medium, 53 low; four leads that were not bugs). All three
high findings and 43 of the 47 medium ones are fixed. 38 low findings stay
open (NUL bytes in request bodies, unescaped text in page tables, the cut
after a few abbreviations). The fixes shipped as v0.3.28 to v0.3.36 and
v0.4.0.

### Fixed in v0.3.28: scoped bridges, review kind, dependencies

| Defect | Fix |
|---|---|
| A bridge pass narrowed by `TOPIC`, `SHA` or `PASSAGE` lost bridges | It clears only the bridges opening on a passage of the scoped topics, which it rewrites |
| A narrowed pass or a second `MISSING=1` run wrote a second bridge on a pair already bridged | The pass never offers a pair a stored bridge rests on, whichever side heads it |
| aiohttp 3.14.3 in the host's `poetry.lock` carried three published advisories | `poetry.lock` pins aiohttp 3.14.5 and yarl 1.25.1, and nothing else moved |
| Reviewers rejected compound questions for asking two things at once | The record's metadata carries the kind, and the guideline says a compound question asks two separate things on purpose and is judged one half at a time |

### Fixed in v0.3.29: references

| Defect | Fix |
|---|---|
| A German polite *Sie* addressing the reader was read as a dangling third person plural | A language-keyed table of polite forms is read by the capitalised surface form: a capital form inside a statement is polite, and one opening a statement only where another capitalised polite form follows. `Sie werden geliefert` is still refused |
| A pronoun after an exceptive clause that points back at its sentence's subject was refused | The verb heading the exceptive clause is marked as heading a clause of its own, as for a subordinator. A pronoun with no noun before it stays refused |
| A German *dies* standing for an earlier clause of its own sentence was refused | The earlier finite verb gets the same "heads a clause of its own" test. A *dies* with no clause before it stays refused |

### Fixed in v0.3.30: bridges in samples

| Defect | Fix |
|---|---|
| A compound question could rest on a bridge's own related pair | A compound sample prefers a passage's own claims and never keeps a bridge. A topic holding only bridges is exhausted for a compound slot |
| An unanswerable slot was dealt a bridge and perturbed it | An unanswerable slot is dealt only facts resting on one passage. A slot with only bridges left is skipped and logged while the topic goes on |
| A compound slot's second passage could hold only bridges | The partner is chosen among passages with an unspent non-bridge fact |

### Fixed in v0.3.31: table rows and soft hyphens

| Defect | Fix |
|---|---|
| A soft hyphen in a PDF text layer deleted every drawn hyphen | A soft hyphen directly before a lower-case letter is dropped, and any other is spelled `-`. A word broken at a line end is still rejoined |
| A group row of a table was glued to its first item | A label alone on a row joins the row below only when exactly one lower-case-labelled row with data follows |
| The tail of a wrapped table label was glued to the next row's label | A label-only row opening in lower case, or closing a bracket the label above left open, joins the label above it |

### Fixed in v0.3.32: table footnotes and lead-ins

| Defect | Fix |
|---|---|
| A footnote the converter attached to a table was in no passage | The footnote is written beneath the table in its passage, once, unless it sits outside the body layer or is also listed as a caption |
| A lead-in scoping a long table reached only its first piece | A table is read as a list is when a lead-in is carried to the pieces |

### Fixed in v0.3.33: number readings

| Defect | Fix |
|---|---|
| A price of four or more digits with a fraction was read as no figure | The figure pattern accepts a long head with a fraction and no thousands mark. A plain long head with three fraction digits stays a fraction |
| The same value in another format was refused as an addition | One owner, `nlp.analysis`, reads a figure's value for `numerals()`, `numbers()` and the question gates, which compare values in the text's language |
| A count written out past twelve was read as no number | Cardinals are composed to 99 (German to 999 and the thousands), and word runs join (`twenty thousand`). A word from thirteen up is a number whatever the tagger made of it |
| The English pronoun `one` was read as the count one | A word counts as a number only with a digit, the tag NUM or an ordinal ADJ, through one shared `is_number` |
| A recovery numbering its steps handed the numbers back as figures the key lacks | `unnamed()` strips the step numbers. An item number `n.` is stripped only where two or more numbered items run in order |
| A list opened by an adverb hid its new item | A verb with only an adverb before it and the list under it is a list head |

### Fixed in v0.3.34: review and page vocabulary

| Defect | Fix |
|---|---|
| The questions workbook had no kind column | A Kind column (single, needs_both, compound) follows Type on the Questions sheet |
| A follow-up reached Argilla without the turns it follows | The record has an optional `thread` field with the earlier turns, oldest first, and `turn` metadata. The guideline says a follow-up is judged after those turns |
| The Questions page named a compound question's prompt wrongly and used Kind for two things | A compound question's prompt is named `type (compound)`. `question_type` is shown as Type and the stored kind as Kind, with a help line for each kind |

### Fixed in v0.3.35: a needs_both question needs both

| Defect | Fix |
|---|---|
| A needs_both question kept both passages when each held only half of what it asked, or the same half | A verifier call lists the parts of the answer and quotes each cited passage that states them. The question stays two-passage only when each cited passage holds a part no other holds. Calibration figures are in [measurements.md](measurements.md) |

### Fixed in v0.3.36: a thread leaves the release whole

| Defect | Fix |
|---|---|
| A released thread lost its root but kept its follow-ups released | The trigger `questions_release_thread_whole` clears `release_id` on every follow-up below a question that leaves `accepted`. The upgrade also clears follow-ups already left under such a root |

### Fixed in v0.4.0: reading documents, questions, topics and pages

| Defect | Fix |
|---|---|
| A numbered reference was linked to another document's section | A numbered reference resolves in the head's own document or is dropped. A title names another document |
| A quoted heading with a typographic apostrophe was cut | Double-quoted spans may hold apostrophes, and single marks close only where no letter follows |
| An inflected label word before a number matched nothing | One shared matcher, `validation.label_word`, also accepts an inflected form (at most two extra letters) directly before a number |
| Sibling linking was quadratic in pure Python | Each head scores its family with one numpy product |
| A link whose partner had no validated fact was dropped after the heads were chosen | Heads and partners without a validated fact are removed before the links are dealt |
| A bridge group of three or more strided before it grew | Each head's link is grown before the quota is strided over |
| A passage held two languages | A chunk ends where its prose changes language, on a confident detection only |
| A running head refiled the text above a chapter's opening | A chapter starts at its own heading where its page holds one |
| A price whose digits equal a page number became a heading | Running names and paragraphs must hold a letter to count as a repeat |
| A German *dies* after a relative clause alone was resolved again (a regression of v0.3.29) | A relative verb does not count as the earlier clause *dies* stands for |
| One scanned page inside a digital PDF went missing silently | Each page with no text layer and pictures covering half of it is named in a warning, in the stored parse's `image-only-pages` metadata and in `documents.parse_error` |
| A vectorless passage always won as compound partner and always lost as needs_both partner | One candidate set is ranked on one scale: cosine only where the head and every candidate carry a vector, word overlap otherwise |
| Topic names lost their subject | A shared ending is removed only when none of its words is a top term of the topics that carry it |
| A small language got no topics and the fit reported success | The frequency filter is held to what the language's own passage count allows. A language still without a model fails the fit after the others are stored |
| Redo on the Assessment page wiped every verdict when the assessment could not run | It answers 409 `assessment_cannot_run` before any verdict is cleared, through a check shared with the CLI |
| A document or topic filter hid a cross-document question's other sources | The filter chooses question ids, and every source is still counted |
| A drawn question rejected before the write lost the whole release draw | The draw writes only the drawn questions still accepted and reports the shortfall |
| A re-check overruled a person's accept | A re-check rejects only a question still accepted and not accepted by a person since. `source_changed` alone overrules |
| A fact deleted while the writer ran lost every question of the topic | `store()` reads the surviving facts `FOR SHARE` and skips and logs the thread that lost one |
| A passage deleted mid-run failed a topic fit or stopped the bridge pass | The fit writes the memberships of passages that still exist, and the bridge pass drops and logs the link |
| A kind, band or language held only by unanswerable rows kept a quota the draw could never fill | The supply check counts only rows a draw can take |
| The default language weights counted rows the draw never takes | The weights count drawable rows, as the bands do |
| The size scan walked one draw per size | A bucket's supply counts unanswerable rows only up to the ceiling |
| A restored question kept the release of a draw that a later one superseded | The restore clears `release_id` unless a question live all along holds that release |
| A restore after a refit or re-chunk restored nothing, or left a question on a fact with no passage | A row whose parent is absent is left behind and counted per table. A restored fact with no passage, and a bridge with fewer than two, are dropped with the question resting on it |

## Found on the v0.3.12 rebuild of 2026-10-19

Every row of the v0.3.12 build was read again under a rubric. The releases
from v0.3.13 on fix what the reading found, one fix to a release.

### Fixed in v0.3.13 to v0.3.27

| Release | Defect | Fix |
|---|---|---|
| v0.3.14 | A fact the repair call split out of a statement competed for its passage's cap | A repair-call fact does not compete for the cap, in flight and in `make extract-recap`, which also gives back repair pieces an earlier cap refused. The model's own facts stay capped |
| v0.3.15 | A bridge was checked against its excerpts' text only, so one naming its own heading was let through | The heading trail and title are read as an atomic fact's are. A bridge that writes a cited passage's numbered heading whole is refused as `not_bridging` |
| v0.3.16 | Bridge pairs were each passage's nearest unused neighbour inside its own topic | `links.py` pairs passages by the documents' own links (a numbered or quoted heading named, sibling sections under one parent, a term only two passages share), per language and across topics |
| v0.3.16 | The bridge prompt invented a link on every pair it was shown | Bridge prompt 6 names the link the pairing found and asks for one bridge or none from a closed set of relations with a probe question. The pairing and the prompt ship together |
| v0.3.17 | An unanswerable question was written in any of eight kinds | An unanswerable slot is written only as a factoid, entity or reason question that the mix weights above 0. A mix with none of them writes the slot answerable |
| v0.3.18 | A range written with a dash was refused when the recovery gave its two ends apart | `agrees()` reads a dash range as its two ends. A key naming one figure does not agree with a range, and a range still needs both ends and its unit |
| v0.3.19 | `answer_incomplete` refused complete list keys | The key is refused only when the recovery also names an item the key and question lack (a conjunct, a marked line, a `;` part, a figure in digits, or the object of a coordinated verb phrase) |
| v0.3.20 | A question's kind was implied by its number of cited passages | Every slot carries a kind, `single` or `needs_both`, stored in `questions.kind`. The kind chooses the writer's instruction and the checks a draft gets. `QUESTIONS_KIND_MIX` shares the kinds out |
| v0.3.21 | A question's band followed the spread of its passages whatever its kind | Where a kind sets a band, that band holds. Other kinds keep the points rule |
| v0.3.22 | No question asked two separate things, one from each of two passages | A `compound` kind (off by default): the writer returns two halves joined by "and", each recovered from its own passage alone |
| v0.3.23 | A bridge kept neither the relation it named nor the question it was tested with | A nullable `facts.bridge` column keeps `{relation, question, answer}` for every bridge written by prompt 6 or later, refused ones too. The six relations live in one table |
| v0.3.25 | A stored compound question was refused when reverified | The re-check holds a stored question to the kind it was written as |
| v0.3.26 | Compound questions were built but never dealt | The kind mix defaults to `needs_both:5,compound:1`, one spanning slot in six. `QUESTIONS_KIND_MIX=needs_both:1` turns compound off |
| v0.3.27 | The release draw bisected for a size that fills | The draw scans sizes down from the largest the pool's supply allows and keeps the first that fills |

## Found on the v0.4.0 rebuild of 2026-10-18

The v0.3.8 code rebuilt the same two PDFs. The review found that welds rose
and topics loosened in the v0.4.0 build. The fixes below were measured on the
labelled rows of both builds.

### Fixed in v0.3.9 to v0.3.12

| Release | Defect | Fix |
|---|---|---|
| v0.3.9 | A bridge fact was offered beside an unrelated claim | A bridge is offered alone, whichever passage it was dealt from |
| v0.3.9 | The bridge prompt taught side-by-side claims | Bridge prompt 5's right example is a claim one excerpt changes by defining what the other's rule applies to. Side by side is a wrong example |
| v0.3.10 | A rule written as one statement joining two actions was lost | Statements refused as `not_atomic` go back to the model once per passage under a repair prompt (`repair-1`). What it writes faces every check, the dedup gate and the cap |
| v0.3.10 | A condition the parser hung as a conjunct counted as a second claim | A conjunct opened by its own subordinator, and a clause naming what an exception leaves out, restrict the rule |
| v0.3.11 | One seeded topic fit was kept unread | The fit draws eight factorisations seeded from `TOPIC_RANDOM_STATE` on and keeps the one whose members are most alike |
| v0.3.12 | The settles reading quoted the answering words and still said silent | Verifier prompt 6 asks for the best reply a chatbot could give before the verdict, with examples of an answer in another form. The elsewhere call reads the cited passages beside the probed ones |

## Found on the v0.3.0 rebuild of 2026-10-16

The v0.3.0 rebuild was reviewed in full: 871 accepted questions (70% usable),
343 released (76% on the first reading, 79% once disagreements were settled;
10 invalid), welds at 18% of two-passage questions. Each finding is fixed,
deferred or ranked low.

### Fixed in v0.3.1: model calls, settings and commands

| Defect | Fix |
|---|---|
| The instructor library re-asked up to 3 times inside each of the client's attempts, so one bad answer could cost 12 billed calls | Instructor is told to re-ask none |
| A rate limit's `Retry-After` was ignored because the 429 arrives wrapped, so the call backed off a second | `Retry-After` is read through the cause chain, for at most two minutes |
| A content-filtered answer failed its topic | A refusal ends after one call and the writer skips the slot |
| Failed calls were never costed | Every attempt is summed onto both log lines, and `make spend` reads both |
| Ollama-only options were sent to hosted models | They are sent only to the provider they belong to |
| A recommended mode stopped every stage | The stage takes the 8 modes it supports, and others are refused at start-up |
| A recalibration rewrote stored scores | Both the old and the new scores are kept |
| A copied `backend.env` stalled the question worker because a missing setting had no default | An absent setting reads 0.02 |
| An old API build went unnoticed | `make doctor` names the settings the API lacks |

### Fixed in v0.3.2: reading text and numbers

| Defect | Fix |
|---|---|
| An abbreviation before a figure ended a sentence | An abbreviation followed by a figure does not end a sentence, unless a line break or an item number follows |
| Two rules each ending in a full stop read as one sentence | A free dash or slash after a full stop and a space opens the next sentence, but not after an abbreviation |
| `provided` was read as an exception | A finite `provided` is read as the verb it is, from the parse's morphology |
| Times and glued figures carried no number | They are read into their own claim field and compared group by group, so `08:00` equals `8:00` and not `09:00` |
| A German decimal was read as an integer | A per-language `DECIMAL_MARK` decides. One mark before three digits that a key writes is read both ways, and a zero head is always a fraction |
| An aggregation key was accepted unasked | The verifier is asked for every aggregation |
| A relabelled aggregation kept its old level | The relabel takes the new kind's level |
| Figures-only paragraphs were dropped | Only a page number's shape is dropped |
| A hyphenated word broken across a table cell or a page stayed broken | The repair runs after them too, with a per-language table of completing words |

### Fixed in v0.3.3: the unit of a fact

| Defect | Fix |
|---|---|
| Dedup refused facts against facts about to be deleted | The extract worker replays dedup itself once its queue empties after replacing facts, under a database lock |
| A statement the tagger mis-rooted counted as two claims | The root is read past a subordinator |
| A verb the tagger gave a finite fine tag but no verb part of speech asserted nothing | The fine tag is read too |
| A fact copying one sentence was judged on the sentence counts stored at chunking | It is judged on the claims it reads as |
| A verbatim repeat inside one passage was kept twice | It is refused as a duplicate of the passage's own fact |
| Refusal messages misstated the dedup bar and reported over-cap twice | The messages are worded as the settings are set |
| A "the model proposed nothing" warning fired where no model ran | It fires only where a model read the passage |
| A figure table or priced list was skipped as an identifier grid | A figure in a cell is read as the value it is |
| A fact citing no sentence was dropped | It is stored as `evidence_absent` |

### Fixed in v0.3.4: round trip, reasons and typing

| Defect | Fix |
|---|---|
| The entailment rescue overrode a verifier that found nothing | A key the verifier read as not in the passages is refused, not rescued |
| The round trip asked the verifier for what only the writer was shown | A name the question carries, or every heading trail of the cited passages, does not have to come back unless the recovery names another. Figures never get this exemption |
| A German adjective tagged as an adverb did not come back | A lemma comes back under an adjective or an adverb unless a negation denies it |
| A set of kinds written as adjectives was refused as one thing | A coordination with no noun phrase is a set, unless a conjunct is a verb or a number |
| German *wo-* question words were missed by `compound` | A per-language table of question adverbs is read |
| The shadow coverage reading was stored on only half the answers it applies to | It is stored on every eligible answer, still in shadow |

### Fixed in v0.3.5: release record and unanswerables

| Defect | Fix |
|---|---|
| The release draw left no record | A trace has one span per twin round, one log line per judged pair with both ids and the verdict, and each bucket's distance from its quota |
| A correct answer was silenced because its quote was stitched from pieces | The quote is looked for piece by piece, each piece as whole words of one shown passage |
| A quote matched inside a longer word | Pieces match on word boundaries |

### Fixed in v0.3.6: parsing and chunking

| Defect | Fix |
|---|---|
| A re-chunk deleted every passage and the facts and questions on them | A passage whose text, section path, sentences and cells are unchanged is kept with its id, facts and topics |
| Hidden labels survived into passages and headings | A clipped character counts as shown only where the same character sits at the same place in the visible read |
| A continued table stopped at a row the converter flagged as a header | The row joins as data when it is set in the first table's data type and its cells match that table's column types |
| List depth was lost at column and page breaks | Depth is measured from each column's own edge, from text and list blocks only, with no new level across a break |
| A lone conjunction was promoted to a heading | It is read as text between two items or paragraphs of one passage, through a per-language table |
| A joined block or table cited only its first page | It cites every page it spans |
| `third- party` was mended to `thirdparty` | A hyphen is kept where the document prints the compound with it elsewhere |

### Fixed in v0.3.7: topics and the scope of a fact

| Defect | Fix |
|---|---|
| A topic's name carried onto the wrong topic | A person's decision moves only to the topic holding most of the same passages. A model's name is never carried. A decision with no match is dropped and counted |
| A fit reported itself stale the moment it was made | One shared rule decides staleness for both the fit and the page |
| A name or coverage choice saved while a fit ran was overwritten | The choice is carried again, under a lock on the rows the fit replaces |
| Smaller topic bookkeeping faults | Each is fixed. A dropped decision of a vanished language is logged and counted |
| Facts dropped the scope that a heading or a list's lead-in sets | Atomic prompt 12 names the heading trail as the situation a rule holds in and keeps a closing lead-in (*the only exceptions are*) as one fact. Digest prompt 5 keeps *should* and *may* |

### Fixed in v0.3.8: security, the frontend, orchestration and the docs

| Defect | Fix |
|---|---|
| Settings accepted values no service could run with, such as `nan`, a misspelt *true* or an unbounded topic count | The values are refused when written. A stored value outside its bounds is shown with a warning |
| The workbook export wrote cells starting with `=` as live formulas | They are written as text |
| The API docs page loaded a floating Swagger script from a CDN | The assets are pinned and `/redoc` is removed |
| Stop stopped only the newest run | Every queued or started run is stopped, and a run already stopping is said to be |
| A run whose worker died blocked the queue | Dagster's run monitoring is on, and a cancelling run counts as going |
| A topic `PATCH` reset what its body left out | It changes only what it names |
| A failed worker rebuild asked the model again every five seconds | It backs off, per version |
| The review sample drew questions already reviewed | It draws only unreviewed ones |
| Annotations stopped for good after one failed flush | They resume |
| A span named the worker's process run, not the run that queued its row | Every span of a row names the run that queued it |
| `make eval-score` scored a reader that production does not run | It scores the production reader |
| Deleting every document forgot the upload history first | It forgets uploads last, and the document listing says when it is cut |
| The configuration panel wrote stale values and showed `0.985` as `0.98` | The panel sends what it drew, redraws after a change, and keeps each number as written |
| Smaller frontend faults, such as confirming a fit twice or a refused write replacing the page | Each is fixed |
| The stack trusted any host name and any missing secret | Streamlit answers only `localhost` and `127.0.0.1`, and compose stops and names a missing secret |

## Found on the v0.2.2 rebuild of 2026-10-14

The run of 2026-10-13 (1,476 questions, 576 accepted, 238 released, 49% of
released rows usable, release 79% German) was read by hand against its
sources, and each defect was traced to its cause in the code. The v0.2.2
rebuild of 2026-10-14 ran the same corpus on `azure/gpt-5.4` (writer) and
`azure/gpt-4.1` (everything else) and was read in full: 475 of 837 accepted
questions usable (57%, against 50%), 166 of 321 released (52%, against 49%). A
hand review of the v0.3.0 rebuild checked its 41 defects again: 19 fixed, 16
fixed in part, 2 not fixed (circular *why* keys, release twins), 4 worse
(`not_atomic` refusals, duplicate refusals, repeated-heading and figure-only
passages, wrong type labels). What the v0.3.x releases fixed since is under
[Found on the v0.3.0 rebuild](#found-on-the-v030-rebuild-of-2026-10-16).

### Fixed in v0.2.2 and v0.3.0, from the 2026-10-13 run

| Defect | Fix |
|---|---|
| The release drew the language written first (187 German against 51 English released) | Language shares in `balance.py`, in the pool's split unless `QUESTIONS_RELEASE_LANGUAGES` weighs them; buckets drawn in md5 order of the question id |
| Fact dedup folded a different rule into a stored fact (24 released questions) | Facts with different numbers are never duplicates; a refusal writes nothing onto the fact it repeats; `EXTRACTION_DUPLICATE_COSINE` 0.985. Repair stored corpora with `make extract-dedup`, then `make questions-rescore` |
| The widen retry replaced an honest draft (5 rows) | The widen retry is removed |
| The count rule misread stated counts | A count in a cited statement is exempt; bare counts are refused whatever the question opens with |
| Sibling list items refused as duplicates (42 released questions) | A passage's own facts are compared across kinds only; the per-passage cap never falls below its sentences plus list items |
| Application questions always spanned two passages (11 released) | A one-passage kind is dealt its one passage at every band |
| The perturbation prompt read "not stated" as "unanswerable" (49% answered by their own material) | Prompt names refuted premises, closed lists and general rules as answered; `PROMPT_VERSION` 12 |
| Struck-through text read as current (471 struck words, 8 released questions) | Words with a drawn horizontal line are removed at conversion; a re-parse is needed |
| Stale section paths, running feet and index letters | Chapters are read from running heads and feet; running feet, index letters and bare conjunction segments are dropped; a re-chunk is needed |
| `off_topic` refused every perturbation (27 of 27 wrong) | `QUESTIONS_OFF_TOPIC_OVERLAP=0` turns the gate off |
| `restates_question` read nouns only | Reads verbs, adverbs and interjections too; a yes or no answer counts as an answer |
| The round trip missed verbs, number words and counts (7 usable lost); v0.3.4 asked the verifier for what only the writer saw | Value keys compare on verbs, number words read as figures, count questions go to the model; names and heading words need not come back |
| An embedded question word read as a second question | A further question word counts only after a coordinating conjunction; German `wo(r)` plus preposition read as question words (v0.3.4) |
| A pronoun its own statement resolves read as dangling (48 of 95 refusals) | A personal pronoun is resolved by an earlier agreeing noun outside its own clause |
| A translation read as furniture (16 passages) | Repetition is read within one language only (v0.3.0) |
| `explanation_unusable` read any proper noun as a name (3 usable lost) | The gate reads an explanation's figures only (v0.3.0) |
| A refusal used as a key | The writer's `declined` field writes the slot as another kind (v0.3.0) |
| `asks_nothing_new` on outline facts | A turn citing only its root's summary or outline moves on when a quarter of its key's content words are new (v0.3.0) |
| A refused model call failed its whole topic (content filter on the retry note) | A prompt refused under a content policy is sent once and costs one slot; a topic fails after five refusals in a row; retry notes read as reviewer feedback (v0.3.0) |

### Parsing

| Defect | Fix in v0.3.0 |
|---|---|
| A struck word survived, or took its neighbours with it | Strike-through is read per character. A bracket or comma beside a deletion stays |
| Text the page hides was read as body text (14 passages of signal-diagram labels) | Text the page clips out of view is dropped. A label printed in view stays |
| A raised ordinal such as `1 st` was read as a separate word | The superscript suffix is joined to its number |
| A table broken at a page or inside a wrapped cell | A header-less table right after one of its width joins it, and a wrapped cell or label rejoins its row |
| A two-column page was interleaved (2 passages) | Not fixed: reading order needs a better layout model |

### Chunking

| Defect | Fix in v0.3.0 |
|---|---|
| A one-page chapter lost its label (chapter missing on 20 German and 23 English passages) | A one-page foot laid out as a chapter's names the chapter. Guide words still name none |
| Chapter labels were letter-spaced in 178 German and 97 English section paths | A label takes the spaces the body puts in the same words |
| A lead-in was cut from its list by a sub-heading, or a sentence was cut by a page | The lead-in travels into the sub-headed chunk, and a sentence cut at a page or column joins its rest |
| A repeated heading or a page number became its own passage | A paragraph equal to a heading heads the passage after it, and a figures-only paragraph is dropped |
| Stale one-letter index segments (66 English passages) | Index letters are read from headings and text, and the longest run in order is the index |
| A nested list was flattened (152 German and 154 English items) | An indented item nests under the one above and is rendered indented |
| Heading levels came from numbering out of sequence | Not fixed: it needs Docling's style inference, which is not public |
| A group heading sat at its children's level (4 passages) | Not fixed: the headings differ only in font family and colour |

### Extraction

| Defect | Fix in v0.3.0 |
|---|---|
| A fact dropped its rule's scope (486 of 3,578 facts narrowed) | Atomic prompt 11: the smallest statement true read alone, with conditions, exceptions, *only* and modality kept and lead-ins restated and cited. Facts dropping a scope word fell from 16.6% to 10.8% (German) and 30.9% to 28.2% (English) |
| Sound facts were refused as `not_atomic` (25 German, 92 English) | A rule and its exception, and two alternatives, count as one claim |
| Sound facts were refused as `unresolved_reference` (84 German, 88 English) | Pronouns are resolved by the language's grammar |
| Sound facts were refused as `asserts_nothing` | A root verb with a subject counts, as does a German or Dutch plural spelled as the infinitive |
| Evidence was cut mid-sentence (76 German and 43 English facts) | No cut inside a slash-joined word, before a comma clause, after an abbreviation before lower case, or between an item number and its item |
| Sound facts were refused as `unsupported_addition` (43 German, 72 English) | Names and numbers are read against the evidence, the section path and the title, with numbers in any spelling |
| A different rule was refused as a duplicate (231 refusals, 13 wrong and 22 partly wrong) | Not fixed. A guard treating near statements as twins only when every word one has and the other lacks is in the other's passage was built and reverted |
| Summaries were about "the excerpt" (61% German, 78% English) | Digest prompt 4 opens on the subject. Summaries opening on the excerpt fell to 0% |
| Facts were written about the document itself (53 validated) | A prompt rule forbids them, and repetition is read within one language |
| No bridge fact was ever written | The bridge pass runs in `make corpus` for topics holding none |

### Topic modelling

| Defect | Fix in v0.3.0 |
|---|---|
| Labels were read off headings and stubs | Excerpts come from fact-bearing passages, ordered by weight times length |
| Headings and page numbers were fitted as subjects | The fit uses passages carrying a fact |
| Every label named the domain (9 of 10 German labels end "im Fußball") | One naming call per language, spelling held to the excerpts, and a shared trailing phrase taken off |
| A topic's passages were never asked about | A passage in no topic joins the nearest centroid |

### Question generation

| Defect | Fix in v0.3.0 |
|---|---|
| Two facts were welded into one question (128 of 270 two-passage questions) | A second passage is offered only where its closest fact is among the topic's closest 2% of pairs, and never a restatement |
| The release drew every hard question | The band split follows the answerable pool |
| Keys named only part of a list (79 released incomplete keys) | A reading or list slot is offered the whole list, up to eight items. Prose keys are read in shadow |
| Unanswerable questions the corpus answers (141 of 283 accepted) | The quote is held to the passages, a probe of twenty passages is fused by vector and words, and settled ones are recycled into answerable questions. The release share is 0 |
| Circular "why" keys (25 of 50 accepted reason keys) | A why whose recovery only restates the question is refused before the entailment rescue |
| A change log's quotations were used as the source (114 accepted questions) | An elided passage is dealt last and never to a list slot |
| Release twins (6 released twin pairs) | The verifier judges each released question against its nearest released neighbour |
| Follow-up comparisons were refused (141 of 151) | Comparison is out of the follow-up kinds, and suspended hyphens count as items |
| A rescued key was not checked for completeness | `incomplete` runs after the rescue too |
| A thread's later turn was refused | `off_thread` reads the whole thread, a negative or a party counts as an answer, and a summary turn moves on when its key is new |
| Sound explanations and numbered rules were refused (29 `explanation_unusable`, 11 `leaks_source`) | Explanations are held to figures, a numbered article, clause or rule is a subject, and a section is a source |
| Retries returned the same draft (22 of 291) | The note quotes the draft, and an unchanged retry is not stored again |
| A refused prompt failed its topic | A content-policy refusal skips one slot |
| Wrong type labels (160 of 837 accepted) and meta-text (73 explanations) | The type is read off the opening, a count with no figure is relabelled, and the writer may decline a slot |

### After the fixes

Counts of the v0.3.0 rebuild (2026-10-16; the weld rate and wrong duplicate
refusals come from a later hand review). Each cell reads German, then English.
[measurements.md](measurements.md#the-v030-rebuild-of-2026-10-16) has the run.

| | v0.2.2 rebuild | v0.3.0 rebuild |
|---|---|---|
| Letter-spaced section paths | 178, 97 | 0, 0 |
| Passages carrying a validated fact | 358, 331 | 361, 339 |
| Validated facts, bridges aside | 1,976, 1,602 | 1,692, 1,488 |
| `not_atomic` refusals per 1,000 facts | 17.8, 56.4 | 32.1, 61.4 |
| `unresolved_reference` per 1,000 | 42.4, 48.4 | 30.1, 21.0 |
| `unsupported_addition` per 1,000 | 19.1, 45.4 | 9.2, 18.2 |
| Duplicate refusals, wrong and partly wrong | 13 and 22 of 231, all read | 35 and 27 of 194, all read |
| Atomic facts dropping *only*, *if*, *unless* or *except* | 16.6%, 30.9% | 10.8%, 28.2% |
| Summaries opening on "the excerpt" | 52%, 75% | 0%, 0% |
| Bridge facts | 0 | 249 |
| Passages carrying a fact that no question cites | 9, 28 | 17, 11 |
| Accepted questions citing two or more passages | 270 of 837 (32%) | 183 of 871 (21%) |
| Of those, welded | 128 of 270 (47%), all read | 33 of 183 (18%), all read |
| Released | 321 | 343 |
| Released `hard` | 100 | 23 |
| Released citing two or more passages | 209 | 91 |
| Released with no answer | 32 | 0 |

## Reproducing this page

The counts are queries over `questions`, `facts`, `question_facts` and
`fact_passages`. The same rows come out of the workbook:

```bash
make questions-export OUT=audit.xlsx FILTER="--released"
```

Each entry's root cause was confirmed in the code and reproduced by a test
before it was fixed. Re-measuring means taking a corpus through again and
rewriting this page and [measurements.md](measurements.md).

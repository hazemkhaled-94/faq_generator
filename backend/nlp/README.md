# NLP

Sentence splitting, claim analysis, vocabulary and language detection: the
linguistic readings every other stage takes from text.

One of three packages that load something heavy, with
[`database/`](../database/README.md) and
[`blob_store/`](../blob_store/README.md). A caller asks for a sentence split
and never loads a pipeline. No model is served from here: everything is local
and deterministic, so the fact checks run without a served model and
`make extract-revalidate` takes seconds.

Three files load weights. Only workers may import them
(`tests/static/test_api_stays_light.py`).

| File | Loads | Asked |
|---|---|---|
| [`embedding.py`](embedding.py) | `EMBEDDING_MODEL` | one text's vector |
| [`entailment.py`](entailment.py) | `NLI_MODEL` | whether one premise entails one hypothesis |
| [`qa.py`](qa.py) | `QA_MODEL` | where in a passage the answer is, or that there is none |

[`windows.py`](windows.py) holds each to its own window:
`EMBEDDING_MAX_TOKENS` for the embedder and `ENCODER_MAX_TOKENS` for the other
two, limited to what the checkpoint can read.

## What it does

### Sentence numbering

Chunking splits every passage into numbered sentences and stores them once.
A fact cites a sentence number instead of quoting text, so a citation either
names a sentence the passage has or it does not.

The splitter's cuts are corrected where a statement would not end:

- Inside a word joined by a slash or a dash, and before a clause opened by a
  comma.
- After an abbreviation that never ends a sentence (`incl. VAT`,
  `gem. Ziff. 3`) on its line.
- After one that may (`etc.`, `Art.`, `Mo.–Fr.`) when a lower-case word
  follows, or a figure on its line (`max. 3 days`, `Sect. 4.`; not `etc.`
  before a line opening `2.`).
- Before a figure that ends a sentence on its line (`EUR 5.`, `Ziffer 3.`).
- Between an item's number and the item. Only a number opening its line
  numbers an item.

A slash or a dash after a sentence end and a space opens the next sentence, so
`inkl. / zzgl. Versand` stays whole.

### Counting claims

`not_atomic` checks that a fact carries exactly one claim by counting
independent finite verbs. A finite verb in a subordinate clause is not
counted. Several mean several claims, and none means nothing is claimed. The
same reading lets the passage gate skip a heading, a caption or a navigation
line before the model is called.

### Vocabulary

Chunking writes onto every passage the lemmas of its nouns, proper nouns and
adjectives, leaving out web addresses, lemmas with no letter and
one-character lemmas. The topic model fits over them.

`NLP_CAPITALISED_NOUNS` names the languages where capitalisation says nothing
about whether a noun is proper, such as German. There a lower-case noun is
read as a foreign word and left out, unless the text is all lower case.

### Language detection

The language is detected per passage. A passage too short to judge, and a
table, keep the document's language. The detector may answer only with a
language `NLP_MODELS` names. `NLP_DEFAULT_LANGUAGE` is the pipeline for a text
whose language is unknown or not named there.

A second detector reads the document once at parse (`document_language`). A
document in a language `NLP_MODELS` does not name is refused, naming its
language. A body of figures, units and abbreviations that no language holds at
0.7 confidence is not refused.

### Entailment and embedding

[`entailment.py`](entailment.py) judges premise and hypothesis pairs, several
per forward pass (`judge_all`). It accepts a three-way NLI head or a two-way
zero-shot head (the shipped `bge-m3-zeroshot-v2.0`), reads each score off the
label the model put beside it, and refuses a checkpoint whose labels are not an
NLI model's. Weights load in full precision, since half precision is many times
slower on a CPU.

The encoder returns a probability. `NLI_ENTAILMENT_THRESHOLD` sets how sure a
gate must be, and `QA_ANSWER_CONFIDENCE` does the same for the extractive
reader. [`embedding.py`](embedding.py) reads the checkpoint's own `1_Pooling`
config instead of assuming mean pooling.

### Mending a broken word

[`text.py`](text.py) rejoins a word a converter broke across two lines at a
hyphen. The hyphen stays only where the document prints the word whole
elsewhere: `third- party` becomes `third-party` in a document that prints
`third-party`, and `thirdparty` in one that never does.

## Adding a language

German and English are configured. Most readings are Universal Dependencies
features; a handful are word lists.

### 1. Configure it

| Where | What |
|---|---|
| `NLP_MODELS` | `xx:xx_core_news_md`. Names the pipeline for a language and the languages the detector may answer with |
| `NLP_CAPITALISED_NOUNS` | Add the code only if the language writes every noun with a capital |
| `TOPIC_LANGUAGE_NAMES` | `xx:Name`. What the topic-naming prompt calls the language |
| `EMBEDDING_MODEL` | Check that the model covers the new language |

Use medium (`_md`) or large (`_lg`) pipelines. `de_core_news_sm` does not tag a
German modal as a finite verb, which changes what `not_atomic` means. A
pipeline named `_sm` or without word vectors loads with a warning.

### 2. Add the language to the word lists

A language missing from a list means that gate silently never fires for it.
[`test_language_tables.py`](../../tests/static/test_language_tables.py) holds
the tables keyed by language code to `NLP_MODELS`. It cannot see `_DOCUMENTS`,
`_ATTRIBUTIONS`, `_AGENTS`, `_HOW_MANY`, `_ANAPHORIC`, `_ASKING` and
`_SOURCE`, which hold every language's words in one set or pattern.

| List | Where | What goes in it | Example |
|---|---|---|---|
| `_DIVISIONS` | [`question_generation/gates.py`](../question_generation/gates.py) | Words naming a division of a document's layout | `Abschnitt`, `section` |
| `_NORMATIVE` | same | Words naming a unit of what a document lays down | `Artikel`, `clause` |
| `_DOCUMENTS` | same | Words naming a document type, never a subject | `Richtlinie`, `guideline` |
| `_ATTRIBUTIONS` | same | Words that attribute what follows to a source | `laut`, `according` |
| `_AGENTS` | same | Interrogatives that ask after a party, not a thing | `wer`, `who` |
| `_HOW_MANY` | same | The opening of a question asking for a count | `wie viele`, `how many` |
| `_COUNTS` | same | Counts written out, read off `CARDINALS` in [`analysis.py`](analysis.py) | `zwei`, `two` |
| `_ASKED_FOR` | same | Question openings and the kinds each asks for, the primary first | `warum`, `why` |
| `_ASKS_HOW_MANY` | same | How a question asks for a count anywhere in it | `wie vielen`, `how many` |
| `_ASKING_ADVERBS` | same | Question words the tagger reads as something else | `worauf` |
| `_RELATES` | same | Lemmas by which a question claims a relation. A compound question that says one is refused | `unterscheiden`, `differ` |
| `_POLARITY` | same | Words answering a yes-or-no question by polarity | `nein`, `not` |
| `_PURPOSE` | same | How the material says why: what a `reason` slot is dealt | `damit`, `so that` |
| `_ANAPHORIC` | [`analysis.py`](analysis.py) | Adjectives pointing back at something already said | `besagt`, `aforementioned` |
| `_ASKING` | same | Words a tagger reads as demonstrative that ask rather than point | `wessen`, `whose` |
| `_SOURCE` | same | Nouns naming the source document, so a demonstrative before one does not point. Title nouns are read from the parse, not listed | `Lehrplan`, `syllabus` |
| `_SPELLING` | same | How the language writes a cardinal: nought to nineteen, the tens, hundred, thousand, and how they join. `CARDINALS` is built from it | `fünf`, `twenty` |
| `CARDINALS` | same | Every cardinal `_SPELLING` spells, each as its value. The fact dedup gate and the question gates read it | `zwei`, `one` |
| `DECIMAL_MARK` | same | The decimal mark. One such mark before three digits is a fraction, not thousands | `,`, `.` |
| `AMOUNT_WORDS` | same | Currency codes and names beside which a space-grouped number is one figure (`5 000 Euro`). One group only: `1 000 000 EUR` stays three figures | `EUR`, `Euro`, `pound` |
| `REFERENCE_LABELS` | same | Words that label a reference by a number: no amount follows (`Section 3 100 customers`) | `Abschnitt`, `Section` |
| `_NUMBER_WORDS` | same | `CARDINALS` and the ordinals, each as its digits. The dedup gate compares numbers by it | `zwei`, `second` |
| `_ORDINALS` | same | The ordinals `_NUMBER_WORDS` holds. An English hyphenated ordinal (`twenty-first`) is read as its last word | `zweite`, `second` |
| `ORDINAL_SUFFIX` | same | What follows the digits of an ordinal figure: `3rd`, a German `3.` | `st`, `nd`, `rd`, `th`, `.` |
| `_CORRELATES` | same | Pronouns standing for an object or clause, not a noun | `es` |
| `_EXPLETIVE_RUNS` | same | Word runs whose pronoun is part of a fixed phrase and stands for nothing | `es sei denn` |
| `_GENITIVE_DEMONSTRATIVES` | same | Demonstratives standing as the genitive of a noun (`die Bank und deren Lieferanten`). A language with no row reads none as resolved | `dessen`, `deren` |
| `_CLAUSE_DEMONSTRATIVES` | same | Demonstratives that carry a clause or participle of their own (`except those related to the price cap`) | `those` |
| `_IDENTITY` | same | Words that say "the same" rather than point back | `derselbe` |
| `_ANAPHORIC_MODIFIERS` | same | Modifiers making their noun one the passage named before, written apart (`oben genannt`) or hyphenated (`above-mentioned`). A statement opening on one is refused. No bare `genannt` | `solcher`, `such` |
| `_CATAPHORIC_MODIFIERS` | same | Modifiers making a plural noun a list given after the statement. On a singular noun or one a figure counts, they mean the next one (`the following 12 months`) | `folgend`, `following` |
| `_ADJECTIVE_ENDINGS` | same | Endings an adjective takes, so a modifier above still matches (`Besagter Kunde`) | `-er`, `-en` |
| `_POLITE` | same | Forms of polite address, read with their capital, since the tagger calls `Sie` third person plural | `Sie`, `Ihre` |
| `_SINGULAR_THEY` | same | Pronouns standing for one person as well as several | `their` |
| `_EXCEPTIVE` | same | Word runs opening an exception or condition with no subordinator in the parse. List the language's full closed class of proviso conjunctions | `es sei denn`, `provided` |
| `_DISJUNCTIVE` | same | Coordinators that offer alternatives, with the first half of a correlative pair. A conjunct one joins is no claim | `oder`, `entweder`, `or`, `either` |
| `_FINITE_TAGS` | same | Fine tags of a finite verb | `VVFIN`, `VBZ` |
| `_ABBREVIATIONS` | same | Abbreviations ending in a full stop that end no sentence on their line | `inkl.`, `incl.` |
| `_CLOSING_ABBREVIATIONS` | same | Abbreviations ending in a full stop that may end a sentence, but end none before a lower-case word or a figure | `usw.`, `Art.`, `Mon.` |
| `JOINING` | [`text.py`](text.py) | Words that complete a hanging hyphen. Read in every configured language at once | `und`, `and` |
| `UNFINISHED` | same | Articles, prepositions and conjunctions that cannot end a table label | `und`, `at` |
| `_CONJUNCTIONS` | [`preprocessing/chunking/furniture.py`](../preprocessing/chunking/furniture.py) | Conjunctions that, printed alone, are no heading | `oder`, `or` |
| `_NAMED` | [`models.py`](models.py) | What to call the language in a prompt | `de: German` |
| `_SPEAKING` | [`generation.py`](../question_generation/generation.py) | First- and second-person pronouns and possessive determiners, in lower case. A premise with none is asked again for the asker's own situation | `meine`, `my` |
| `_ENQUIRING` | same | Verbs of wanting, trying, checking and understanding, as lemmas. A premise with only these is asked again, as above | `prüfen`, `understand` |
| `_STEP_LABEL` | [`gates.py`](../question_generation/gates.py) | The word a procedure's steps are numbered with | `Schritt`, `Step` |
| `_INFLECTIONS` | [`extraction/validation.py`](../extraction/validation.py) | Endings a label word takes ("Sections 7") | `Abschnitte`, `Sections` |
| `_SHARE_WORDS` | [`extraction/validation.py`](../extraction/validation.py) | Words that name a share. A language missing here compares a share by the word as written | `Prozent`, `percent` |
| `_TIME_UNITS` | [`extraction/validation.py`](../extraction/validation.py) | Lemmas of the days, weeks and months a period is counted in. A language missing here compares by the unit as written | `Tag`, `week` |

No list is matched as a substring: `Risikobericht` is a thing a corpus is
about, and `Bericht` is a thing a corpus is. Each list is matched as follows.

- By lemma: `_DIVISIONS`, `_NORMATIVE`, `_DOCUMENTS`, `_ANAPHORIC`, `_ASKING`.
- By lemma or the word as written: `_ATTRIBUTIONS`, `_SOURCE` and the two
  modifier tables (also with an `_ADJECTIVE_ENDINGS` ending).
- By the word as written: `_AGENTS`, `_NUMBER_WORDS`, `_CORRELATES`,
  `_EXCEPTIVE`, `_POLITE`, `_GENITIVE_DEMONSTRATIVES`,
  `_CLAUSE_DEMONSTRATIVES` and the two abbreviation tables.
- Against a whole heading's letters: `_CONJUNCTIONS`.
- Question openings at the start of the question, and `_COUNTS` against an
  answer's first word.

`_broken_word`, beside `JOINING` in [`text.py`](text.py), rejoins a word
broken at a line's end only when the letter before the hyphen is one of A–Z,
the German umlauts or ß and the letter after it is a lower-case one of those.
A language that writes other letters needs them added there: `cré- dit` is not
rejoined.

Five sets in [`analysis.py`](analysis.py) name languages by a grammatical
trait: `_PLURAL_GENDERLESS`, `_SYNCRETIC_FEMININE`,
`_NOUN_ANAPHORIC_DEMONSTRATIVES`, `_INFINITIVE_IS_PLURAL` and
`_VERB_FINAL_SUBORDINATE` (subordinate clauses end on the finite verb). A
language missing from one lacks the trait.

`_NAMED` falls back to the ISO code for a missing language. Every prompt that
writes text names its language from it, except the topic-naming prompt, which
reads `TOPIC_LANGUAGE_NAMES`. A model told to write in the language of the
excerpt infers one language for a lopsided corpus, and the drift reaches
question generation as a question in the wrong language, rejected as
`malformed`. `_AGENTS` cannot be a feature: no tagset marks animacy on an
interrogative.

### 3. Check what the language supports

A language that fails one of these needs code.

| | Needed by | Without it |
|---|---|---|
| `noun_chunks` | `phrases()`, and so `subject`, `enumerates`, `compares` | Raises. Russian, Chinese and Ukrainian have no syntax iterator, and Japanese needs SudachiPy |
| An NER component with `PER` or `PERSON` | `names_parties`, the credits-page reading | Density is always 0, so the reading never fires and nothing says so |
| `like_num` on spelled-out numerals | `claim().units` | Uneven: `de_core_news_md` tags `zwei` `like_num` false where `en_core_web_md` gives `two` both |

### 4. One Gregorian pattern

`_DATED` in [`question_generation/gates.py`](../question_generation/gates.py)
reads a period off a four-digit year in 1800–2099 or a `DD.MM`-style pair. It
misses an era year, a Hijri year, Arabic-Indic digits and `FY24`. Only
`temporal` questions read it, and `QUESTIONS_TYPE_MIX` decides whether any are
written.

### What needs no edit

| Reading | Feature |
|---|---|
| Question words, for `compound` | `PronType=Int`, or a tag prefix as a fallback |
| Content words and lemmas | `NOUN`, `PROPN`, `ADJ` |
| A number, for the circularity exemption | `NUM` |
| Pointing outward | `PronType=Dem`, and a noun with both a definite article and a quantifier |
| A pronoun its own statement resolves, for `unresolved_reference` | `PronType=Prs`, with `Gender` and `Number` on it and on an earlier noun outside its own clause. A subject or object label where neither carries them |
| Everything measured on an embedding | `EMBEDDING_MODEL`, which is multilingual |
| Every length, share and citation reading | no language at all |

## Configuration

The first three settings are read here, are fixed (served read-only, never
stored) and need a restart to change. The rest belong to the callers. All are
catalogued under `platform`.

| Setting | What it does |
| --- | --- |
| `NLP_MODELS` | The spaCy pipeline per language, and the languages the detector may answer with |
| `NLP_DEFAULT_LANGUAGE` | The pipeline for a text whose language is unknown or not in `NLP_MODELS` |
| `NLP_CAPITALISED_NOUNS` | Languages where capitalisation is not evidence of a proper noun |
| `EMBEDDING_MODEL` | The embedding model, and the tokenizer chunking sizes a passage by |
| `EMBEDDING_MAX_TOKENS` | The embedder's ceiling. Chunking cuts a passage to it less the tokens the embedder adds. At least 64: a settings change below that is refused |
| `NLI_MODEL` | The entailment encoder. Absent asks the verifier instead |
| `NLI_ENTAILMENT_THRESHOLD` | How sure it must be before it rescues an answer |
| `QA_MODEL` | The extractive reader asked for a span before the verifier is |
| `QA_ANSWER_CONFIDENCE` | How sure that reader must be before its span is taken |
| `ENCODER_MAX_TOKENS` | The longest pair an encoder reads, held to each tokenizer's `model_max_length`. Does not apply to entailment with the shipped model unless set below 512 |

Changing `NLP_MODELS` changes what a fact is, as changing the prompt does.
Both are recorded on every fact: `spacy_model`, `spacy_version`,
`extraction_model`, `prompt_version`.

spaCy's pipelines and lingua are baked into the backend image, so a model
named in `NLP_MODELS` must be in the image. Encoder weights are fetched on
first use into the `models` volume.

## Tests

```sh
poetry run pytest tests/unit/nlp -m nlp
```

The tests are in `tests/unit/nlp`. Those marked `nlp` (`test_sentences`,
`test_claims`, `test_pointing`, `test_numbers`, `test_entailment`,
`test_parses_are_remembered` and the model tests in `test_embedding`) are
excluded by `make test-fast`. Only `test_embedding` loads encoder weights, and
only when they are cached.

## Limits

- The small spaCy models change what a fact is. Use the medium pipelines.
- The detector cannot answer with a language `NLP_MODELS` does not name. A
  French passage in a German corpus is read as German or English.
- Sentence numbering is stored, not recomputed. After `NLP_MODELS` changes on
  a chunked corpus, `make chunk-revocabulary` re-reads language and lemmas,
  and the sentence offsets need `chunk-rerun`.
- One capital switches the case rule back on: in
  `girokonto kündigungsfrist Musterbank`, the lower-case nouns are dropped
  again in a language named in `NLP_CAPITALISED_NOUNS`.
- A German `dies` after a clause stands for that clause, even where it names a
  thing (`Wer ein Konto eröffnet, erhält dies per Post.`). Telling an event
  from a thing needs the verb's meaning, which the parse does not give.
- `_CATAPHORIC_MODIFIERS` spares "the following fees" when a figure counts the
  noun or a colon follows, even where the items are elsewhere: "The following
  fees apply: see the price list."
- Nothing here calls a served model.

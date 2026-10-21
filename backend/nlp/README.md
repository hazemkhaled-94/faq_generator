# NLP

Sentence splitting, claim analysis, vocabulary and language detection — the
linguistic surface every other stage reads off text.

One of the three packages that load something expensive; the others are
[`database/`](../database/README.md) and
[`blob_store/`](../blob_store/README.md). A caller asks for a sentence split;
it never loads a pipeline.

**No model is served from here.** Everything is local and deterministic, which
is what lets the fact checks run without a served model and why
`make extract-revalidate` costs seconds rather than hours.

Three files load weights, and nothing outside a worker may import them:

| File | Loads | Asked |
|---|---|---|
| [`embedding.py`](embedding.py) | `EMBEDDING_MODEL` | one text's vector |
| [`entailment.py`](entailment.py) | `NLI_MODEL` | whether one premise entails one hypothesis |
| [`qa.py`](qa.py) | `QA_MODEL` | where in a passage the answer is, or that there is none |

Each is held to its own window by [`windows.py`](windows.py):
`EMBEDDING_MAX_TOKENS` is the ceiling a deployment asks for the embedder and
`ENCODER_MAX_TOKENS` the one it asks for the other two, and a checkpoint that
cannot read that far is given what it can. Entailment reads at most its
tokenizer's `model_max_length`, 512 for the shipped `bge-m3-zeroshot-v2.0`, so
`ENCODER_MAX_TOKENS` does not apply to it unless set below that.
`tests/static/test_api_stays_light.py` pins that the API loads none of them.

## What it does

### Sentence numbering

Chunking splits every passage into numbered sentences and stores them. A fact
**cites one of those numbers** rather than quoting text, so its source span is
exact by construction — a citation is either a sentence the passage has or one
it does not.

It is computed once, by chunking, and stored. Nothing recomputes it.

The parser's cuts are corrected where a statement would not end: inside a
word joined by a slash or a dash, before a clause opened by a comma, after an
abbreviation followed by a lower-case word or, on its line, a figure that
numbers no item (`approx. 3 days`, but not `etc.` before a line opening `2.`),
and between an item's number and the item. A slash or a dash after a
sentence's end and a space joins nothing: it opens the next sentence, as a
free `- ` does or as the bullet of the next line. An abbreviation's full stop
ends no sentence there either, so `inkl. / zzgl. Versand` stays whole.

### Counting claims

`not_atomic` — the check that a fact carries exactly one claim — is a
**finite-verb count**, of the independent ones: a finite verb inside a
relative or other subordinate clause is not counted. A statement with more
than one carries several claims; one with none carries nothing.

A parse rooted on a clause its subordinator opens has made the condition
the main clause, and the span is read as the one rule it states.

The same reading is what lets the passage gate skip a heading, a caption or a
navigation line **before** the model is called.

### Vocabulary

The lemmas of the nouns, proper nouns and adjectives, without web addresses,
lemmas with no letter or one-character lemmas, written onto every passage
by chunking and read by the topic model as the document it is fitted over.

`NLP_CAPITALISED_NOUNS` names the languages where capitalisation says nothing
about whether a noun is proper — German, where every noun is capitalised. In
those languages a lower-case noun is read as a foreign word and left out, in
a text that writes some word after its first with a capital: a query typed
all in lower case keeps its nouns.

### Language detection

Detected on the **passage**, not inherited from its document; a passage too
short to judge, and a table, keep the document's. The detector may only
answer with a language `NLP_MODELS` names, because an answer with no
pipeline behind it is a passage nothing can read. `NLP_DEFAULT_LANGUAGE` is
the pipeline a text is read with when its language is unknown or not one
`NLP_MODELS` names.

### One call, one judgement

[`entailment.py`](entailment.py) answers one question about each premise and
hypothesis pair: `judge_all` takes several pairs in one forward pass and
returns one verdict for each.

Two kinds of head are accepted and each score is read off the **label the
model put beside it**, never off a position: a three-way NLI model naming
entailment/neutral/contradiction, and a two-way zero-shot head naming
entailment/not_entailment. mDeBERTa-xnli and bart-mnli are ordered opposite
ways round, so assuming an order inverts every verdict on half the models
anybody would configure.

`transformers`' own text-classification pipeline hands back the label names,
so what is left here is the one thing it does not do: refuse a checkpoint
whose labels are not an NLI model's. A sentiment head scores every pair
fluently and means nothing by it.

Two-way heads are read beside three-way ones, and the shipped
`bge-m3-zeroshot-v2.0` is two-way. Its tokenizer declares 512 tokens, as
`mDeBERTa-v3-base-xnli`'s does, and a premise here is a passage already sized
to `EMBEDDING_MAX_TOKENS`.

The weights always load in full precision. `bge-m3-zeroshot-v2.0` is saved in
half precision, and loaded that way on a CPU it runs many times slower for the
same scores.

What the encoder returns is a **probability**, so a deployment can decide how
sure it wants a gate to be. `NLI_ENTAILMENT_THRESHOLD` is that decision, and
`QA_ANSWER_CONFIDENCE` is the same for the extractive reader.

[`embedding.py`](embedding.py) is `sentence-transformers`, which reads the
checkpoint's own `1_Pooling` config rather than assuming the mean.

### Mending a broken word

[`text.py`](text.py) rejoins a word a converter broke across two lines at a
hyphen. Parsing runs it over every string it reads, and the table and page
joins over each string they make of two, since the halves of a word a cell
wrapped or a page broke meet only there. A word broken at its own hyphen
looks like any other broken word, so it keeps the hyphen only where the
document prints it whole elsewhere: `third- party` is `third-party` in a
document that prints `third-party`, and `thirdparty` in one that never
does. Mending twice changes nothing.

## Adding a language

German and English are configured. Most readings are Universal Dependencies
features every tagset marks; a handful are word lists. This is all of it.

### 1. Configure it

| Where | What |
|---|---|
| `NLP_MODELS` | `xx:xx_core_news_md`. Names both the pipeline a language is read with and the languages the detector may answer with |
| `NLP_CAPITALISED_NOUNS` | Add the code **only** if the language writes every noun with a capital |
| `TOPIC_LANGUAGE_NAMES` | `xx:Name`. What the topic-naming prompt calls the language |
| `EMBEDDING_MODEL` | Check the new language is one the model covers |

**Medium, not small.** `de_core_news_sm` does not tag a German modal as a
finite verb, which silently changes what `not_atomic` means.

### 2. Add the language to the word lists, and name it

These are the readings no feature marks. A language missing from one means
that gate **silently never fires** for it — no error, no log. The tables
keyed by language code are held to `NLP_MODELS` by
[`test_language_tables.py`](../../tests/static/test_language_tables.py), so a
language added there without its rows fails that test, naming each table.
The rest — `_DOCUMENTS`, `_ATTRIBUTIONS`, `_AGENTS`, `_HOW_MANY`,
`_ANAPHORIC`, `_ASKING`, `_SOURCE` and `_REFUSALS` — hold every language's
words in one set or pattern, so that test cannot see them: a language
missing from one fails no test.

| List | Where | What goes in it | Example |
|---|---|---|---|
| `_DIVISIONS` | [`question_generation/gates.py`](../question_generation/gates.py) | Words naming a division of a document's layout, by language: numbered, a citation | `Abschnitt`, `section` |
| `_NORMATIVE` | same | Words naming a unit of what a document lays down, by language: numbered, the question's subject | `Artikel`, `clause` |
| `_DOCUMENTS` | same | Words naming a document **type**, never a subject | `Richtlinie`, `guideline` |
| `_ATTRIBUTIONS` | same | Words that attribute what follows to a source | `laut`, `according` |
| `_AGENTS` | same | The interrogatives that ask after a **party** rather than a thing | `wer`, `who` |
| `_HOW_MANY` | same | The opening of a question asking for a count | `wie viele`, `how many` |
| `_COUNTS` | same | Counts written out, read off `CARDINALS` in [`analysis.py`](analysis.py) | `zwei`, `two` |
| `_ASKED_FOR` | same | Question openings by language, and the kinds each asks for, the primary first | `warum`, `why` |
| `_ASKS_HOW_MANY` | same | How a question asks for a count anywhere in it, by language | `wie vielen`, `how many` |
| `_ASKING_ADVERBS` | same | Question words the language's tagger reads as something else, by language: a German `wo(r)` and a preposition | `worauf` |
| `_RELATES` | same | Lemmas by which a question claims a relation between what it asks about, by language: a comparison, a total, a cause. A compound question that says one is refused | `unterscheiden`, `differ` |
| `_POLARITY` | same | Words answering a yes-or-no question by their polarity, by language | `nein`, `not` |
| `_PURPOSE` | same | How the material says why, by language: what a `reason` slot is dealt | `damit`, `so that` |
| `_ATTRIBUTING` | same | Word runs that attribute what follows to a source, by language: a document title one leads to is a named source whatever the material writes | `laut`, `according to` |
| `_ANAPHORIC` | [`analysis.py`](analysis.py) | Adjectives pointing back at something already said | `besagt`, `aforementioned` |
| `_ASKING` | same | Words a tagger reads as demonstrative that ask rather than point | `wessen`, `whose` |
| `_SOURCE` | same | Nouns naming the source document: a demonstrative before one is not read as pointing | `Lehrplan`, `syllabus` |
| `_SPELLING` | same | How the language writes a cardinal: the words nought to nineteen, the tens, the words for a hundred and a thousand, how a unit and a ten join (`twenty-five`, `fünfundzwanzig`) and whether a scale word glues to its multiplier (`zweitausend`); `CARDINALS` is spelled out of it | `fünf`, `twenty` |
| `CARDINALS` | same | Every cardinal `_SPELLING` spells, from nought to a hundred (a German one to ninety-nine thousand), each as the value it names: the one count table the fact dedup gate and the question gates both read; two words that make one number (`twenty thousand`) are joined by `numbers` | `zwei`, `one` |
| `DECIMAL_MARK` | same | The mark the language writes a decimal with: one such mark before three digits is a fraction, not thousands, wherever the question gates read a figure the passages or the verifier's reply state | `,`, `.` |
| `AMOUNT_WORDS` | same | The currency codes, symbols and names beside which a number grouped by a space is one figure (`5 000 Euro`, `EUR 100 000`); anywhere else the groups stay separate, as in a table row or a phone number. Known limits: one group only, so `1 000 000 EUR` stays three figures, and a two-cell table row whose second cell is an amount (`Kontoführung 5 120 Euro`) is read as 5120 | `EUR`, `Euro`, `£` |
| `REFERENCE_LABELS` | same | The words that label a reference by a number, before which a space-grouped run is never an amount (`Section 3 100 customers`) | `Abschnitt`, `Section` |
| `_NUMBER_WORDS` | same | `CARDINALS` and the ordinals, each as the digits it names: what the fact dedup gate compares two statements' numbers by | `zwei`, `second` |
| `_ORDINALS` | same | The ordinals `_NUMBER_WORDS` holds, by language, each as the digits it names | `zweite`, `second` |
| `ORDINAL_SUFFIX` | same | What a language writes after the digits of an ordinal figure, so `3rd` and a German `3.` are the ordinal that `third` and `dritte` are, never the count 3, where the question gates compare a key with what came back | `st`, `nd`, `rd`, `th`, `.` |
| `_CORRELATES` | same | Pronouns standing in for an object or clause beside them rather than for a noun: a statement carrying one is not left dangling | `es` |
| `_EXPLETIVE_RUNS` | same | Word runs whose pronoun is part of a fixed phrase and stands for nothing | `es sei denn` |
| `_IDENTITY` | same | Words that say "the same" rather than point back: a statement opening on one refers to nothing before it | `derselbe` |
| `_POLITE` | same | Forms of polite address, read as written with their capital: the tagger calls `Sie` third person plural, and a statement addressing the reader points at nothing before it. One opening a statement counts only where another polite form follows it | `Sie`, `Ihre` |
| `_SINGULAR_THEY` | same | Pronouns standing for one person as well as several, so a singular noun can be what they refer to | `their` |
| `_EXCEPTIVE` | same | Word runs opening an exception or a condition with no subordinator in the parse: one claim with the rule before it. A one-word run tagged as a finite verb is that verb | `es sei denn`, `provided` |
| `_DISJUNCTIVE` | same | Coordinators that offer alternatives: a conjunct one joins is no claim of its own | `oder`, `or` |
| `_FINITE_TAGS` | same | Fine tags of a finite verb: a statement carrying one asserts something, whatever part of speech the tagger gave the word | `VVFIN`, `VBZ` |
| `_ABBREVIATIONS` | same | Abbreviations ending in a full stop that end no sentence before a lower-case word or a figure | `ca.`, `approx.` |
| `JOINING` | [`text.py`](text.py) | Words that complete a hanging hyphen, so the hyphen before one is no line break: read in every configured language at once, because a document is parsed before its passages have a language | `und`, `and` |
| `UNFINISHED` | [`text.py`](text.py) | Articles, prepositions and conjunctions that cannot end a table label: a label alone on a row that ends on one goes on in the row below, whatever follows | `und`, `at` |
| `_CONJUNCTIONS` | [`preprocessing/chunking/furniture.py`](../preprocessing/chunking/furniture.py) | Conjunctions joining two alternatives or items: one printed alone is no heading, in the trail or as a heading the layout made of it | `oder`, `or` |
| `_REFUSALS` | [`topic_modelling/labels.py`](../topic_modelling/labels.py) | The topic-naming model's word for "no subject" | `gemischt`, `mixed` |
| `_NAMED` | [`models.py`](models.py) | What to call the language in a prompt | `de: German` |
| `_STEP_LABEL` | [`gates.py`](../question_generation/gates.py) | The word a procedure's steps are numbered with: `Step 1:` is no figure the key lacks | `Schritt`, `Step` |
| `_INFLECTIONS` | [`extraction/validation.py`](../extraction/validation.py) | The endings a label word takes to inflect: a form of a learned label word directly before a number counts as the label ("Sections 7"), a word that merely begins with it does not | `Abschnitte`, `Sections` |

None is read as a substring: `_DIVISIONS`, `_NORMATIVE`, `_DOCUMENTS`, `_ANAPHORIC` and
`_ASKING` are read by **lemma**, `_ATTRIBUTIONS` and `_SOURCE` by lemma or
by the word as written, `_CONJUNCTIONS` against a whole heading's letters, `_AGENTS`, `_NUMBER_WORDS`, `_CORRELATES`,
`_EXCEPTIVE`, `_POLITE` and `_ABBREVIATIONS` by the word as written, the openings off the start of the question, `_COUNTS`
against an answer's first word and `_REFUSALS` against the whole name. `Risikobericht` is a thing a corpus is
about and `Bericht` is a thing a corpus IS.

`_broken_word`, beside `JOINING` in [`text.py`](text.py), rejoins a word
broken at a line's end only where the letter before the hyphen is one of
A–Z, the German umlauts or ß and the letter after it is a lower-case one of
those, so a language writing other letters needs them added there, or its
words broken at a line's end stay broken: `cré- dit` is not rejoined.

Four sets in [`analysis.py`](analysis.py) name languages by a trait of their
grammar rather than holding words — `_PLURAL_GENDERLESS`,
`_SYNCRETIC_FEMININE`, `_NOUN_ANAPHORIC_DEMONSTRATIVES` and
`_INFINITIVE_IS_PLURAL` — and a language missing from one is read as lacking
the trait.

`_NAMED` is the one that is not a word list, and a language missing from it
falls back quietly to its own ISO code, which is still an instruction a model
can follow. Every prompt that writes text names
its language from it, except the topic-naming prompt, which reads
`TOPIC_LANGUAGE_NAMES`, because *"write in the language of the excerpt"* is an
inference — on a corpus lopsided towards one language a model infers that one
for all of it. Nothing in extraction checks a language, so the drift reaches
question generation as a question in the wrong language and is thrown out as
`malformed`.

`_AGENTS` could not be a feature — no tagset marks animacy on an
interrogative.

### 3. Check three things the language has to support

Not edits. A language failing one of these needs code:

| | Needed by | Without it |
|---|---|---|
| `noun_chunks` | `phrases()`, and so `subject`, `enumerates`, `compares` | **Raises.** Russian, Chinese and Ukrainian have no syntax iterator; Japanese needs SudachiPy |
| An NER component with `PER` or `PERSON` | `names_parties`, the credits-page reading | Density is always 0, so the reading never fires and nothing says so |
| `like_num` on spelled-out numerals | `claim().units` | Asymmetric: `de_core_news_md` tags `zwei` `like_num` FALSE where `en_core_web_md` gives `two` both |

### 4. One pattern that is Gregorian

`_DATED` in [`question_generation/gates.py`](../question_generation/gates.py)
reads a period off a four-digit year in 1800–2099 or a `DD.MM`-style pair. It
misses an era year, a Hijri year, Arabic-Indic digits and `FY24`. Only
`temporal` questions read it, and `QUESTIONS_TYPE_MIX` decides whether any
are written.

### What needs no edit

| Reading | Feature |
|---|---|
| Question words, for `compound` | `PronType=Int`, or a tag prefix as a fallback |
| Content words and lemmas | `NOUN`, `PROPN`, `ADJ` |
| A number, for the circularity exemption | `NUM` |
| Pointing outward | `PronType=Dem`, and a noun with both a definite article (`Definite=Def`, or `PronType=Art` without `Definite=Ind`) and a quantifier (`NumType=Card`, or a determiner with `PronType=Ind`) |
| A pronoun its own statement resolves, for `unresolved_reference` | `PronType=Prs`, and `Gender` and `Number` on it and on a noun before it outside its own clause, bounded by a `mark`/`cp` subordinator or an `advcl`/`relcl`/`acl`/`rc` attachment whose verb, or an auxiliary or copula under it, is finite; a subject or object label where neither carries them |
| Everything measured on an embedding | `EMBEDDING_MODEL`, which is multilingual |
| Every length, share and citation reading | no language at all |

## Configuration

Only the first three are read here. The rest are the caller's, and all are
catalogued under `platform`. The first three are fixed: served read-only and
never stored, so changing one needs a restart.

| Setting | What it does |
| --- | --- |
| `NLP_MODELS` | The spaCy pipeline per language, **and** the languages the detector may answer with |
| `NLP_DEFAULT_LANGUAGE` | The pipeline a text is read with when its language is unknown or not in `NLP_MODELS` |
| `NLP_CAPITALISED_NOUNS` | Languages where capitalisation is not evidence of a proper noun, and a lower-case noun is foreign |
| `EMBEDDING_MODEL` | The one embedding model, and the tokenizer chunking sizes a passage by |
| `EMBEDDING_MAX_TOKENS` | The embedder's ceiling. Chunking cuts a passage to it less the tokens the embedder adds |
| `NLI_MODEL` | The entailment encoder. Absent asks the verifier instead |
| `NLI_ENTAILMENT_THRESHOLD` | How sure it must be before it rescues an answer |
| `QA_MODEL` | The extractive reader asked for a span before the verifier is |
| `QA_ANSWER_CONFIDENCE` | How sure that reader must be before its span is taken |
| `ENCODER_MAX_TOKENS` | The longest pair an encoder reads. A **ceiling**, held to each tokenizer's `model_max_length`, so it does not apply to entailment with the shipped model unless set below 512 |

Changing `NLP_MODELS` changes what a fact is, in the same way changing the
prompt does. Both are recorded on every fact — `spacy_model`,
`spacy_version`, `extraction_model`, `prompt_version`.

spaCy's pipelines and lingua are baked into the backend image: nothing
fetches one at run time. The encoder weights are fetched on first use into
the `models` volume. A model named here must be in the image.

## Tests

```sh
poetry run pytest tests/unit/nlp -m nlp
```

| File | Covers |
|---|---|
| [`test_sentences.py`](../../tests/unit/nlp/test_sentences.py) | Sentence numbering, which every citation resolves against |
| [`test_claims.py`](../../tests/unit/nlp/test_claims.py) | How many claims a sentence reads as |
| [`test_language.py`](../../tests/unit/nlp/test_language.py) | Reading the language a passage is written in |
| [`test_pointing.py`](../../tests/unit/nlp/test_pointing.py) | What a claim points at, and what it does not |
| [`test_numbers.py`](../../tests/unit/nlp/test_numbers.py) | The numbers a statement states, a number word read as its value |
| [`test_text.py`](../../tests/unit/nlp/test_text.py) | A word broken at a line hyphen made whole, a shared suffix kept, a compound the document prints whole keeping its hyphen, and mending twice the same as once |
| [`test_references.py`](../../tests/unit/nlp/test_references.py) | When a German `es` is read as a correlate rather than a pronoun |
| [`test_entailment.py`](../../tests/unit/nlp/test_entailment.py) | A verdict read off the label, and the refusal of a head that is not an NLI model's |
| [`test_qa.py`](../../tests/unit/nlp/test_qa.py) | The span decode, the no-answer head, and the window that slides |
| [`test_embedding.py`](../../tests/unit/nlp/test_embedding.py) | The vector, when `EMBEDDING_MODEL` is already cached |
| [`test_parses_are_remembered.py`](../../tests/unit/nlp/test_parses_are_remembered.py) | One text read several ways is parsed once |

`test_sentences`, `test_claims`, `test_pointing`, `test_numbers`, `test_entailment`,
`test_parses_are_remembered` and the model tests in `test_embedding` carry
the `nlp` marker, and `make test-fast` excludes them. Only `test_embedding`
loads encoder weights, and only when they are already cached.

## Limits

- **The small spaCy models change what a fact is.** Use the medium pipelines.
- **The detector cannot answer with a language `NLP_MODELS` does not name.**
  A French passage in a German corpus is read as German or English.
- **Sentence numbering is stored, not recomputed.** Changing `NLP_MODELS`
  after a corpus is chunked leaves every stored citation resolving against
  the old split. `make chunk-revocabulary` re-reads language and lemmas; the
  sentence offsets need `chunk-rerun`.
- **Nothing here calls a served model.**

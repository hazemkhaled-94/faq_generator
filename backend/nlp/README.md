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
cannot read that far is given what it can.
`tests/static/test_api_stays_light.py` pins that the API loads none of them.

## What it does

### Sentence numbering

Chunking splits every passage into numbered sentences and stores them. A fact
**cites one of those numbers** rather than quoting text, so its source span is
exact by construction — a citation is either a sentence the passage has or one
it does not.

It is computed once, by chunking, and stored. Nothing recomputes it.

### Counting claims

`not_atomic` — the check that a fact carries exactly one claim — is a
**finite-verb count**, of the independent ones: a finite verb inside a
relative or other subordinate clause is not counted. A statement with more
than one carries several claims; one with none carries nothing.

The same reading is what lets the passage gate skip a heading, a caption or a
navigation line **before** the model is called.

### Vocabulary

The lemmas of the nouns, proper nouns and adjectives, without web addresses,
lemmas with no letter or one-character lemmas, written onto every passage
by chunking and read by the topic model as the document it is fitted over.

`NLP_CAPITALISED_NOUNS` names the languages where capitalisation says nothing
about whether a noun is proper — German, where every noun is capitalised. In
those languages a lower-case noun is read as a foreign word and left out.

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

The two-way heads are wanted rather than tolerated. `bge-m3-zeroshot-v2.0`
reads 8,192 tokens where `mDeBERTa-v3-base-xnli` reads 512, and a premise here
is a passage already sized to `EMBEDDING_MAX_TOKENS`.

What the encoder returns is a **probability**, so a deployment can decide how
sure it wants a gate to be. `NLI_ENTAILMENT_THRESHOLD` is that decision, and
`QA_ANSWER_CONFIDENCE` is the same for the extractive reader.

[`embedding.py`](embedding.py) is `sentence-transformers`, which reads the
checkpoint's own `1_Pooling` config rather than assuming the mean.

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
that gate **silently never fires** for it — no error, no log.

| List | Where | What goes in it | Example |
|---|---|---|---|
| `_DIVISIONS` | [`question_generation/gates.py`](../question_generation/gates.py) | Words naming a division of a document | `Abschnitt`, `section` |
| `_DOCUMENTS` | same | Words naming a document **type**, never a subject | `Richtlinie`, `guideline` |
| `_ATTRIBUTIONS` | same | Words that attribute what follows to a source | `laut`, `according` |
| `_AGENTS` | same | The interrogatives that ask after a **party** rather than a thing | `wer`, `who` |
| `_HOW_MANY` | same | The opening of a question asking for a count | `wie viele`, `how many` |
| `_COUNTS` | same | Counts written out | `zwei`, `two` |
| `_ASKED_FOR` | same | Question openings, and the kinds each asks for | `warum`, `why` |
| `_ANAPHORIC` | [`analysis.py`](analysis.py) | Adjectives pointing back at something already said | `besagt`, `aforementioned` |
| `_ASKING` | same | Words a tagger reads as demonstrative that ask rather than point | `wessen`, `whose` |
| `_SOURCE` | same | Nouns naming the source document: a demonstrative before one is not read as pointing | `Lehrplan`, `syllabus` |
| `_REFUSALS` | [`topic_modelling/labels.py`](../topic_modelling/labels.py) | The topic-naming model's word for "no subject" | `gemischt`, `mixed` |
| `_NAMED` | [`models.py`](models.py) | What to call the language in a prompt | `de: German` |

None is read as a substring: `_DIVISIONS`, `_DOCUMENTS`, `_ANAPHORIC` and
`_ASKING` are read by **lemma**, `_ATTRIBUTIONS` and `_SOURCE` by lemma or
by the word as written, `_AGENTS` by the word as written, the openings off
the start of the question, `_COUNTS` against an answer's first word and
`_REFUSALS` against the whole name. `Risikobericht` is a thing a corpus is
about and `Bericht` is a thing a corpus IS.

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
| `EMBEDDING_MAX_TOKENS` | The embedder's ceiling, and so the longest passage chunking emits |
| `NLI_MODEL` | The entailment encoder. Absent asks the verifier instead |
| `NLI_ENTAILMENT_THRESHOLD` | How sure it must be before it rescues an answer |
| `QA_MODEL` | The extractive reader asked for a span before the verifier is |
| `QA_ANSWER_CONFIDENCE` | How sure that reader must be before its span is taken |
| `ENCODER_MAX_TOKENS` | The longest pair an encoder reads. A **ceiling** |

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
| [`test_entailment.py`](../../tests/unit/nlp/test_entailment.py) | A verdict read off the label, and the refusal of a head that is not an NLI model's |
| [`test_qa.py`](../../tests/unit/nlp/test_qa.py) | The span decode, the no-answer head, and the window that slides |
| [`test_embedding.py`](../../tests/unit/nlp/test_embedding.py) | The vector, when `EMBEDDING_MODEL` is already cached |
| [`test_parses_are_remembered.py`](../../tests/unit/nlp/test_parses_are_remembered.py) | One text read several ways is parsed once |

`test_sentences`, `test_claims`, `test_pointing`, `test_entailment`,
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

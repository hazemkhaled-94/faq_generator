"""The fit flow: claim a request, fit every language, replace, draw.

The database and the object store are held in memory; the fitter, the
labeller and the renderer are the real ones, so a fit here goes through
gensim and pyLDAvis.
"""

from __future__ import annotations

import pytest
from topic_drivers import LabellerDriver, corpus

from topic_modelling.models import FittedTopic, PassageVocabulary
from topic_modelling.space import load


def test_an_empty_queue_is_not_a_run(service) -> None:
    """A drain stops when nothing has been asked for."""
    flow = service()

    assert flow.run() is None
    assert flow.stored == []


def test_a_requested_fit_writes_every_language(service, passages, english) -> None:
    """One run, one model per language, all of it stored together."""
    flow = service({"de": passages, "en": english})

    flow.request_and_run()

    assert flow.languages_stored == ["de", "en"], flow.languages_stored
    assert flow.failure is None, flow.failure


def test_each_language_carries_the_span_it_was_fitted_in(
    service, passages, english, monkeypatch
) -> None:
    """A topic links to its own language's fit, not to the whole run's."""
    from opentelemetry.sdk.trace import TracerProvider

    from topic_modelling import service as module

    monkeypatch.setattr(module, "span", TracerProvider().get_tracer(__name__))
    flow = service({"de": passages, "en": english})

    flow.request_and_run()

    spans = [one.span_id for one in flow.stored]
    assert all(spans), spans
    assert len(set(spans)) == 2, spans
    assert len({one.trace_id for one in flow.stored}) == 1


def test_the_fit_counts_every_decision_it_lost(service, passages, monkeypatch) -> None:
    """Those its carry matched to no topic, and those the store lost.

    The store loses a decision on a language no passage carries any more.
    """
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    from topic_modelling import service as module

    spans = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(spans))
    monkeypatch.setattr(module, "span", provider.get_tracer(__name__))
    flow = service({"de": passages})
    flow.queue.previous["de"] = [
        FittedTopic(0, ["lieferung"], label="Versand", labelled_by="person")
    ]
    flow.queue.dropped = 2

    flow.request_and_run()

    fit = next(one for one in spans.get_finished_spans() if one.name == "model_topics")
    assert (fit.attributes or {})["topic.decisions_dropped"] == 3


def test_a_fit_reports_what_each_language_was_over(service, passages) -> None:
    """The passage count and the vocabulary size travel with the topics."""
    flow = service({"de": passages})

    flow.request_and_run()

    stored = flow.stored[0]
    assert stored.passages == len(passages)
    assert stored.vocabulary > 0
    assert len(stored.topics) == 2, len(stored.topics)


def test_a_corpus_with_no_language_fails_the_run_and_says_what_to_do(service) -> None:
    """Chunking is what detects a language, so the message has to name it."""
    flow = service({})

    flow.request_and_run()

    assert flow.failure is not None
    assert "chunk" in flow.failure.lower(), flow.failure
    assert flow.stored == []


def test_a_language_the_filter_empties_is_left_out_not_fatal(
    service, passages, english
) -> None:
    """One language failing must not take the others with it."""
    flow = service({"de": passages, "en": corpus("solitary", first_id=900)})

    flow.request_and_run()

    assert flow.languages_stored == ["de"], flow.languages_stored
    assert flow.failure is None, flow.failure


def test_a_run_where_no_language_survives_the_filter_fails(service) -> None:
    """An empty result is a failure, not an empty model."""
    flow = service({"de": corpus("solitary", "unrelated")}, no_below=99)

    flow.request_and_run()

    assert flow.failure is not None
    assert "de" in flow.failure, flow.failure


def test_a_store_that_refuses_fails_the_fit_with_its_type(service) -> None:
    """Anything but NoVocabulary is recorded with the exception's name."""
    flow = service()
    flow.queue.refuses = RuntimeError("the transaction was rolled back")

    flow.request_and_run()

    assert flow.failure is not None
    assert flow.failure.startswith("RuntimeError:"), flow.failure


def test_a_failed_fit_leaves_the_previous_topics_alone(service) -> None:
    """The request row carries the reason; the topics are untouched."""
    flow = service()
    flow.queue.stored = ["what the last fit wrote"]  # pyright: ignore[reportArgumentType]
    flow.queue.refuses = RuntimeError("no")

    flow.request_and_run()

    assert flow.queue.stored == ["what the last fit wrote"]


def test_a_drain_sweeps_a_claim_an_earlier_run_left(service) -> None:
    """Every stage fails an abandoned claim before taking new work."""
    flow = service()
    flow.queue.abandoned = 1

    assert flow.drain() == 0, "nothing was queued, so nothing should have run"


def test_a_drain_runs_the_queued_fit_and_then_stops(service) -> None:
    """One request is one fit, however many times the loop goes round."""
    flow = service()
    flow.request()

    assert flow.drain() == 1
    assert flow.languages_stored == ["de"]


# ── Drawing ───────────────────────────────────────────────────────────────


def test_each_language_gets_its_own_figure(service, passages, english) -> None:
    """One page per model, keyed by language and typed as HTML."""
    flow = service({"de": passages, "en": english})

    flow.request_and_run()

    assert set(flow.figures) == {"de", "en"}, set(flow.figures)
    assert flow.export.types["topics/de.html"].startswith("text/html")


def test_the_fit_keeps_the_model_it_drew_the_figure_from(
    service, passages, english
) -> None:
    """One .npz per language, and it loads back as the model that was fitted.

    The figure is a view of this. Keeping only the view is what the fit did
    before, which left a fit represented by an HTML file with d3 inlined
    into it and nothing able to recompute what it was a picture of.
    """
    flow = service({"de": passages, "en": english})

    flow.request_and_run()

    assert set(flow.models.models) == {"topics/de.npz", "topics/en.npz"}
    read = load(flow.models.models["topics/de.npz"])
    assert read.vocabulary, "the vocabulary the matrix is indexed by"
    assert len(read.topic_term) == len(read.doc_topic[0]), "a row per topic"
    assert len(read.doc_topic) == len(read.doc_lengths), "a row per passage"


def test_a_model_that_cannot_be_stored_does_not_fail_the_fit(service) -> None:
    """The topics are already written by the time it is stored.

    A fit whose rows landed is not a failed fit, and rolling a good corpus
    back over a briefly unreachable object store would lose more than the
    model does.
    """
    flow = service()
    flow.models.refuses_put = RuntimeError("the store is down")

    flow.request_and_run()

    assert flow.queue.stored, "the topics were still written"
    assert not flow.models.models


def test_a_refit_archives_the_previous_model_before_it_writes_its_own(
    service,
) -> None:
    """The previous fit's rows are archived by the replace, and its model too."""
    flow = service()
    flow.models.models["topics/de.npz"] = b"the previous fit"

    flow.request_and_run()

    assert flow.archive.objects == {"models/topics/de.npz": b"the previous fit"}
    assert flow.models.models["topics/de.npz"] != b"the previous fit"


def test_a_fit_that_lost_its_claim_leaves_the_model_and_figure_alone(
    service,
) -> None:
    """The fit that holds the claim now writes them; this one wrote no topics."""
    flow = service()
    flow.models.models["topics/de.npz"] = b"the newer fit"
    flow.queue.lost = True

    flow.request_and_run()

    assert flow.models.models == {"topics/de.npz": b"the newer fit"}
    assert not flow.figures
    assert not flow.archive.objects


def test_a_model_that_cannot_be_archived_is_not_overwritten(service) -> None:
    """The previous fit's model stays where it is rather than being lost."""
    flow = service()
    flow.models.models["topics/de.npz"] = b"the previous fit"
    flow.archive.refuses = RuntimeError("no permission")

    flow.request_and_run()

    assert flow.failure is None, flow.failure
    assert flow.models.models == {"topics/de.npz": b"the previous fit"}


def test_the_old_figure_is_archived_before_the_new_one_is_drawn(service) -> None:
    """A figure of topics that no longer exist is worse than none."""
    flow = service()
    flow.export.figures["topics/de.html"] = b"the previous fit"

    flow.request_and_run()

    assert flow.archive.objects == {"export/topics/de.html": b"the previous fit"}
    assert flow.figures["de"] != b"the previous fit"


def test_a_figure_that_cannot_be_stored_does_not_fail_the_fit(service) -> None:
    """The topics are already written; a model with no picture is a model."""
    flow = service()
    flow.export.refuses_put = RuntimeError("the bucket is full")

    flow.request_and_run()

    assert flow.failure is None, flow.failure
    assert flow.languages_stored == ["de"]
    assert flow.figures == {}


def test_a_figure_that_cannot_be_archived_is_not_replaced(service) -> None:
    """Rather than draw a new page beside a stale one that would not go."""
    flow = service()
    flow.archive.refuses = RuntimeError("no permission")

    flow.request_and_run()

    assert flow.failure is None, flow.failure
    assert flow.figures == {}


def test_a_missing_pyldavis_is_logged_and_the_topics_still_written(
    service, monkeypatch, caplog
) -> None:
    """An image built without the viz group still fits a model."""
    import builtins

    real = builtins.__import__

    def refuse(name, *args, **kwargs):
        """Fails the one import the drawing needs."""
        if name == "topic_modelling.visualisation":
            raise ImportError("no module named pyLDAvis")
        return real(name, *args, **kwargs)

    flow = service()
    monkeypatch.delitem(
        __import__("sys").modules, "topic_modelling.visualisation", raising=False
    )
    monkeypatch.setattr(builtins, "__import__", refuse)

    with caplog.at_level("ERROR"):
        flow.request_and_run()

    assert flow.languages_stored == ["de"], flow.languages_stored
    assert flow.failure is None, flow.failure
    assert "pyLDAvis is missing" in caplog.text
    assert flow.figures == {}


def test_unplaced_passages_are_warned_about_by_language(
    service, passages, caplog
) -> None:
    """They and everything drawn from them are outside every report."""
    flow = service({"de": [*passages, PassageVocabulary(id=97, lemmas=["zzz"])]})

    with caplog.at_level("WARNING"):
        flow.request_and_run()

    assert "1 of 5 de passage(s) have no topic" in caplog.text, caplog.text


def test_a_passage_the_store_placed_is_not_warned_about(
    service, passages, caplog
) -> None:
    """It joined the topic whose centroid is nearest, so it is in a topic."""
    flow = service({"de": [*passages, PassageVocabulary(id=97, lemmas=["zzz"])]})
    flow.queue.placed = {97}

    with caplog.at_level("WARNING"):
        flow.request_and_run()

    assert "have no topic" not in caplog.text, caplog.text


def test_the_figure_is_a_self_contained_page(service) -> None:
    """Nothing is fetched when it is opened."""
    flow = service()

    flow.request_and_run()

    page = flow.figures["de"].decode("utf-8")
    assert "var LDAvis" in page, "the LDAvis script is not inlined"
    assert "d3.select" in page, "d3 is not inlined"


# ── Naming ────────────────────────────────────────────────────────────────


def test_topics_are_named_by_the_model_when_one_is_configured(service) -> None:
    """Every topic that holds no label is offered to the model."""
    flow = service(
        labeller=LabellerDriver("Shipping", "Storage", languages={"de": "German"})
    )

    flow.request_and_run()

    assert flow.labels_of("de") == ["Shipping", "Storage"], flow.labels_of("de")
    assert all(topic.labelled_by == "test-model" for topic in flow.topics_of("de")), (
        flow.topics_of("de")
    )


def test_a_topic_whose_passages_carry_no_fact_is_not_offered_to_the_model(
    service,
) -> None:
    """Mixed is decided off the facts, before any call."""
    labeller = LabellerDriver("Shipping", languages={"de": "German"})
    flow = service(labeller=labeller, min_fact_share=0.15)
    flow.queue.bearing = {1, 2}

    flow.request_and_run()

    assert labeller.model.calls == 1, labeller.model.asked
    labels = sorted(flow.labels_of("de"), key=lambda label: label or "")
    assert labels == [None, "Shipping"], labels


def test_a_name_another_topic_already_took_is_refused(service) -> None:
    """Two topics under one name read as one topic in the coverage report.

    Asked for in the prompt, which is shown the names already given, and
    enforced on the answer: a model told not to repeat one still does, and
    an unnamed topic is the better failure of the two.
    """
    flow = service(
        labeller=LabellerDriver("Shipping", "Shipping", languages={"de": "German"})
    )

    flow.request_and_run()

    assert flow.labels_of("de") == ["Shipping", None], flow.labels_of("de")


def test_the_names_already_taken_are_shown_to_the_model(service) -> None:
    """It cannot avoid a repeat it was never told about."""
    labeller = LabellerDriver("Storage", languages={"de": "German"})
    flow = service(labeller=labeller)
    flow.queue.previous["de"] = [
        FittedTopic(
            0,
            ["lieferung", "versand", "transport", "monatlich", "paketdienst"],
            label="By hand",
            labelled_by="person",
        )
    ]
    flow.queue.dominant["de"] = {1: 0, 2: 0}

    flow.request_and_run()

    assert "By hand" in labeller.prompt, labeller.prompt


def test_no_labeller_leaves_every_topic_with_its_terms_and_no_name(service) -> None:
    """A fit without a served model is still a fit."""
    flow = service()

    flow.request_and_run()

    assert flow.labels_of("de") == [None, None], flow.labels_of("de")
    assert all(topic.top_terms for topic in flow.topics_of("de"))


def test_a_name_a_person_typed_is_never_offered_to_the_model(service) -> None:
    """Its provenance stays `person` across the refit."""
    named = LabellerDriver("Generated", languages={"de": "German"})
    flow = service(labeller=named)
    flow.queue.previous["de"] = [
        FittedTopic(
            0,
            ["lieferung", "versand", "transport", "monatlich", "paketdienst"],
            label="By hand",
            labelled_by="person",
        )
    ]
    flow.queue.dominant["de"] = {1: 0, 2: 0}

    flow.request_and_run()

    carried = [topic for topic in flow.topics_of("de") if topic.label == "By hand"]
    assert carried, flow.topics_of("de")
    assert carried[0].labelled_by == "person", carried[0]
    assert named.model.calls == 1, f"the model was asked {named.model.calls} times"


def test_a_refit_asks_the_labeller_for_a_topic_whose_model_name_did_not_travel(
    service,
) -> None:
    """A model's name is not a decision, so the next fit names the topic again.

    Carried, it skipped the labeller, the spelling held to the excerpts and
    the shared ending taken off, and it stood in the names already taken.
    """
    labeller = LabellerDriver("Lieferung", "Wartung", languages={"de": "German"})
    flow = service(labeller=labeller)
    flow.queue.previous["de"] = [
        FittedTopic(
            0,
            ["lieferung", "versand", "transport", "monatlich", "paketdienst"],
            label="Versand",
            labelled_by="test-model",
        )
    ]
    flow.queue.dominant["de"] = {1: 0, 2: 0}

    flow.request_and_run()

    assert "Topic 0" in labeller.prompt and "Topic 1" in labeller.prompt
    assert "Names already taken" not in labeller.prompt, labeller.prompt
    assert sorted(flow.labels_of("de"), key=str) == ["Lieferung", "Wartung"]


def test_the_model_is_shown_the_passages_the_topic_holds_most_strongly(
    service, passages
) -> None:
    """The terms alone are a thin prompt, so excerpts go in with them."""
    texts = {one.id: f"passage {one.id} text" for one in passages}
    named = LabellerDriver("A subject", languages={"de": "German"})
    flow = service(texts=texts, labeller=named)

    flow.request_and_run()

    assert named.model.calls == 1, named.model.calls
    shown = named.prompt
    assert "passage" in shown, shown
    assert "German" in shown, shown


def test_a_topic_is_named_off_its_passages_that_carry_a_fact(service, passages) -> None:
    """A heading can hold a topic most strongly and still say nothing.

    Its few words all sit in one topic, so its weight there is near total,
    yet extraction found nothing in it: a name read off it names the
    document's layout, not its subject.
    """
    heading = PassageVocabulary(id=5, lemmas=["lieferung", "versand"])
    texts = {one.id: f"stated rule {one.id}" for one in passages} | {5: "HEADING"}
    named = LabellerDriver("Shipping", "Storage", languages={"de": "German"})
    flow = service({"de": [*passages, heading]}, texts=texts, labeller=named)
    flow.queue.bearing = {one.id for one in passages}

    flow.request_and_run()

    shown = "".join(str(ask["user"]) for ask in named.model.asked)
    assert "stated rule" in shown, shown
    assert "HEADING" not in shown, shown


def test_the_passage_that_says_most_of_a_topic_is_shown_first(
    service, passages, monkeypatch
) -> None:
    """Of two passages wholly in a topic, the longer says more of it."""
    from topic_modelling import service as module

    monkeypatch.setattr(module, "_EXCERPTS", 1)
    long = PassageVocabulary(
        id=5, lemmas=["lieferung", "versand", "transport"] * 4 + ["spedition"]
    )
    texts = {one.id: f"short {one.id}" for one in passages} | {5: "LONG"}
    named = LabellerDriver("Shipping", "Storage", languages={"de": "German"})
    flow = service({"de": [*passages, long]}, texts=texts, labeller=named)
    flow.queue.bearing = {*(one.id for one in passages), 5}

    flow.request_and_run()

    shown = "".join(str(ask["user"]) for ask in named.model.asked)
    assert "LONG" in shown, shown
    assert "short 1" not in shown and "short 2" not in shown, shown


def test_a_model_that_finds_no_subject_leaves_the_topic_unnamed(service) -> None:
    """A wrong name is worse than none, so `Mixed` is not stored."""
    flow = service(labeller=LabellerDriver("Mixed", languages={"de": "German"}))

    flow.request_and_run()

    assert flow.labels_of("de") == [None, None], flow.labels_of("de")


def test_a_model_that_cannot_be_reached_does_not_fail_the_fit(service) -> None:
    """Losing the names is better than losing the fit."""
    from llm.client import ModelUnavailable

    refusing = LabellerDriver("never said", languages={"de": "German"}).refusing(
        ModelUnavailable("connection refused")
    )
    flow = service(labeller=refusing)

    flow.request_and_run()

    assert flow.failure is None, flow.failure
    assert flow.labels_of("de") == [None, None]


@pytest.mark.parametrize("held", [0, 1, 4, 9])
def test_the_prompt_holds_no_more_excerpts_than_the_service_allows(
    service, passages, held
) -> None:
    """A dozen full passages would not fit in one prompt."""
    from topic_modelling.service import _EXCERPTS

    texts = {one.id: f"text {one.id}" for one in passages[:held]}
    named = LabellerDriver("A subject", languages={"de": "German"})
    flow = service(texts=texts, labeller=named)

    flow.request_and_run()

    for ask in named.model.asked:
        for block in str(ask["user"]).split("Topic ")[1:]:
            excerpts = block.count("\n- ")
            assert excerpts <= _EXCERPTS, excerpts

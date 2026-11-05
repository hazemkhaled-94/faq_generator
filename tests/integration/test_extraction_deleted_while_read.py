"""A passage deleted while extraction reads it ends the drain.

C-136 taught the judge to log an artefact deleted mid-row and take the next
one, and parsing catches `Gone` too. Extraction does not: the store finds its
row gone and raises `Gone`, the service's catch-all then calls `fail`, which
raises `Gone` again from inside the handler, and the exception leaves
`process_next` and `drain`. A host drain (`make extract`, what
`make corpus-hosted` runs) exits with a traceback, and the corpus chain stops.

Runs the real `ExtractionService` over the real `PassageQueue` on Postgres,
with the model scripted; the scripted model deletes the document mid-call,
as `make delete` or the Documents page would.
"""

from __future__ import annotations

import pytest
from drivers import Extraction
from seed import digest, document, passage
from sqlalchemy.orm import Session

from database.qa_generator import Passage
from extraction.repository import PassageQueue
from ingestion.repository import DocumentRepository

pytestmark = [pytest.mark.integration, pytest.mark.nlp]

#: One passage a language: German, English, unconfigured Latin (Polish) and Greek.
TEXTS = {
    "de": "Die Kontoführung kostet 5 EUR im Monat. Überweisungen sind kostenlos.",
    "en": "The account costs 5 EUR a month. Transfers are free of charge.",
    "pl": "Prowadzenie konta kosztuje 5 EUR miesięcznie. Przelewy są bezpłatne.",
    "el": "Ο λογαριασμός κοστίζει 5 EUR τον μήνα. Οι μεταφορές είναι δωρεάν.",
}


@pytest.mark.parametrize("language", list(TEXTS))
def test_a_passage_deleted_mid_read_does_not_end_the_drain(
    engine, database, language
) -> None:
    """The next passage is read; nothing escapes the drain."""
    from nlp.analysis import sentences as split

    sha, other = digest("bank-" + language), digest("shop-" + language)
    text = TEXTS[language]
    with Session(engine) as session:
        ids = []
        for one in (sha, other):
            session.add(document(one, language=language))
            session.flush()
            held = passage(
                one,
                text=text,
                language=language,
                extract_status="pending",
                sentences=[
                    {"i": s.index, "start": s.start, "end": s.end, "predicates": 1}
                    for s in split(text, language)
                ],
            )
            session.add(held)
            session.flush()
            ids.append(held.id)
        session.commit()

    deleted = []

    def deleting(_prompt: str) -> dict:
        if not deleted:
            deleted.append(DocumentRepository().delete(sha))
        return {"facts": [{"sentences": [0], "statement": text.split(". ")[0] + "."}]}

    run = Extraction(facts=deleting)
    run.service._repository = PassageQueue()  # type: ignore[assignment]

    run.run()

    assert run.service.failed == 0, "a deleted row is not a failure"
    with Session(engine) as session:
        assert session.get(Passage, ids[0]) is None
        taken = session.get(Passage, ids[1])
        assert taken is not None and str(taken.extract_status).endswith("extracted")

"""Each passage's nearest twin in another document, kept as a score.

The furniture filter asks whether a passage recurs, nearly unchanged, in
another document of its own language. Asked per candidate that is one
nearest-neighbour probe a passage for every topic, so the answer is stored:
`passages.nearest_foreign_cosine` is the exact cosine to the closest embedded
passage of another document in the same language, and `nearest_foreign_doc`
is the document that passage is in.

Every writer of a passage's vector, language or existence calls these inside
its own transaction, so the score is true when the transaction commits:

- `score` when a passage is embedded or changes language: its own score, and
  the raise of every older passage it is closer to than anything it had;
- `rescore_from` when a document is deleted or re-chunked, or its passages
  move language: only the passages whose nearest came from it are read again,
  because a score that only rose would keep a passage furniture after its twin
  was gone.

Here and not in a stage, because three stages write what it reads and no
backend service imports another.
"""

from __future__ import annotations

from collections.abc import Collection

from sqlalchemy import ARRAY, CHAR, BigInteger, bindparam, text
from sqlalchemy.orm import Session

#: The nearest foreign passage of `p`, as (cosine, document), by an exact
#: sort: an ordering on this expression cannot use the vector index, which
#: would answer from the nearest few graph neighbours, filtered after.
_NEAREST = """
    (SELECT c, d FROM (
        SELECT 1 - (q.embedding <=> p.embedding) AS c, q.doc_sha256 AS d
        FROM passages q
        WHERE q.doc_sha256 <> p.doc_sha256
          AND q.language = p.language
          AND q.embedding IS NOT NULL
        ORDER BY c DESC
        LIMIT 1
    ) AS nearest)
"""

_OWN = text(
    f"""
    UPDATE passages p
    SET (nearest_foreign_cosine, nearest_foreign_doc) = {_NEAREST}
    WHERE p.id = ANY(:ids) AND p.embedding IS NOT NULL
    """
).bindparams(bindparam("ids", type_=ARRAY(BigInteger)))

_RAISE = text(
    """
    UPDATE passages q
    SET (nearest_foreign_cosine, nearest_foreign_doc) = (closest.best, closest.d)
    FROM (
        SELECT DISTINCT ON (o.id) o.id, 1 - (o.embedding <=> n.embedding) AS best,
               n.doc_sha256 AS d
        FROM passages n
        JOIN passages o ON o.doc_sha256 <> n.doc_sha256 AND o.language = n.language
        WHERE n.id = ANY(:ids) AND n.embedding IS NOT NULL
          AND o.embedding IS NOT NULL
        ORDER BY o.id, best DESC
    ) AS closest
    WHERE q.id = closest.id
      AND (q.nearest_foreign_cosine IS NULL
           OR closest.best > q.nearest_foreign_cosine)
    """
).bindparams(bindparam("ids", type_=ARRAY(BigInteger)))

_AGAIN = text(
    f"""
    UPDATE passages p
    SET (nearest_foreign_cosine, nearest_foreign_doc) = {_NEAREST}
    WHERE p.nearest_foreign_doc = ANY(:docs)
    """
).bindparams(bindparam("docs", type_=ARRAY(CHAR(64))))

_LANGUAGES = text(
    "SELECT DISTINCT coalesce(language, '') FROM passages WHERE id = ANY(:ids)"
).bindparams(bindparam("ids", type_=ARRAY(BigInteger)))


def lock(session: Session, passage_ids: Collection[int]) -> None:
    """Takes a transaction lock for each language these passages are in.

    Before the vector is written, and held to the commit, so a second worker
    embedding the other half of a twin pair waits and then reads this one's
    vector: without it each side was scored before the other was visible, and
    neither was. One lock to a language, in a fixed order, so workers on
    different languages do not wait on each other.
    """
    ids = sorted(passage_ids)
    if not ids:
        return
    for language in sorted(session.scalars(_LANGUAGES, {"ids": ids})):
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"foreign:{language}"},
        )


def score(session: Session, passage_ids: Collection[int]) -> None:
    """Writes the nearest-twin score of these embedded passages, and raises others'.

    The passages given get their own score from every other passage, exactly.
    Every older passage of the same language that one of them is closer to than
    to anything before gets that cosine and the document it came from.
    """
    ids = sorted(passage_ids)
    if not ids:
        return
    lock(session, ids)
    session.execute(_OWN, {"ids": ids})
    session.execute(_RAISE, {"ids": ids})


def rescore_from(session: Session, documents: Collection[str]) -> None:
    """Reads again the score of every passage whose nearest came from these documents.

    After a document is deleted, its passages dropped or re-chunked, or their
    language moved: what each of those passages held may be the maximum of a
    passage that is gone. Only those rows are read again, exactly, and they may
    fall to another document's passage or to nothing.
    """
    docs = sorted(set(documents))
    if not docs:
        return
    session.execute(_AGAIN, {"docs": docs})

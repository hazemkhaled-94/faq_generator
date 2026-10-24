"""A corpus ten times this build's, inserted and probed on a Postgres sized as shipped.

The server is started the way compose starts it: the limits, the `/dev/shm`
and the `-c` options all read from `configs/env/deployment.env`. It is loaded
to the reviewed build's size (2,000 passages, 14,000 fact vectors) and
measured, then loaded to the go-live size (20,000 passages, 137,000 fact
vectors) and measured again. What is measured is what a drain does to the
database: the dedup probe of `extraction.repository._nearest_fact` and the
write of a passage's facts through `_write`, on the real schema with its real
indexes. Vectors are random, which is the hardest case for an HNSW graph.

The bar: the 95th percentile of each is within twice what it was at the
reviewed size (the probe's of a single pass over a fresh vector, which is what
a drain pays; the best of three is printed beside it), the index builds finish with no memory notice and the
parallel build gets the `/dev/shm` it needs, a database time per passage
stays under 0.37 s, and the pools at their peak stay under 80% of
`max_connections`. No model is called.

Never on a pull request: `make test-perf`, and by hand with
`-m "perf and integration"` through `FX/scripts/itest.sh`.
"""

from __future__ import annotations

import random
import re
import statistics
import time
from pathlib import Path

import psycopg
import pytest
from facts import checked
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

pytestmark = [pytest.mark.perf, pytest.mark.integration]

ROOT = Path(__file__).resolve().parents[2]

#: The reviewed build and the go-live corpus: passages and fact vectors.
ONE = (2_000, 14_000)
TEN = (20_000, 137_000)

#: How many facts a passage yields, and so probes it costs.
FACTS_PER_PASSAGE = 7

#: The most database time one passage may take, in seconds: the share of the
#: whole drain's time budget that leaves the model its calls.
PER_PASSAGE = 0.37

#: Probes and writes timed at each size.
PROBES = 300
PASSES = 3
WRITES = 100
BATCH = 20


def _sizing() -> dict[str, str]:
    """The POSTGRES_* values deployment.env ships."""
    found = re.findall(
        r"^(POSTGRES_[A-Z_]+)=(.*)$",
        (ROOT / "configs/env/deployment.env").read_text(),
        re.MULTILINE,
    )
    return {name: value.strip() for name, value in found}


@pytest.fixture(scope="module")
def sized(runtime):
    """A Postgres started with the shipped sizing, migrated, with its URL."""
    from conftest import POSTGRES_IMAGE, _install_extensions, _migrate, _started
    from testcontainers.community.postgres import PostgresContainer

    size = _sizing()
    options = []
    for setting, name in (
        ("shared_buffers", "POSTGRES_SHARED_BUFFERS"),
        ("maintenance_work_mem", "POSTGRES_MAINTENANCE_WORK_MEM"),
        ("effective_cache_size", "POSTGRES_EFFECTIVE_CACHE_SIZE"),
        ("max_connections", "POSTGRES_MAX_CONNECTIONS"),
    ):
        options += ["-c", f"{setting}={size[name]}"]

    def build():
        return (
            PostgresContainer(POSTGRES_IMAGE, driver="psycopg")
            .with_command(["postgres", *options])
            .with_kwargs(
                mem_limit=size["POSTGRES_MEMORY"],
                memswap_limit=size["POSTGRES_MEMORY"],
                nano_cpus=int(float(size["POSTGRES_CPUS"]) * 1e9),
                shm_size=size["POSTGRES_SHM_SIZE"],
            )
        )

    container = _started(build)
    try:
        url = container.get_connection_url()
        _install_extensions(url)
        _migrate(url)
        yield container, url, size
    finally:
        container.stop()


def _connect(url: str, notices: list[str]) -> psycopg.Connection:
    """One autocommit connection, collecting what the server says."""
    connection = psycopg.connect(
        url.replace("postgresql+psycopg://", "postgresql://"), autocommit=True
    )
    connection.add_notice_handler(lambda one: notices.append(one.message_primary))
    return connection


def _vector(rng: random.Random) -> list[float]:
    """A random vector of the column's width."""
    return [rng.gauss(0, 1) for _ in range(1024)]


#: The two indexes a bulk load drops and builds again, as a restore does.
_INDEXES = {
    "ix_facts_embedding_hnsw": "facts",
    "ix_passages_embedding_hnsw": "passages",
}


def _load(connection: psycopg.Connection, to: tuple[int, int]):
    """Grows the corpus to `to` passages and facts, then builds the indexes.

    Rows are written by the server out of two pools of random vectors whose
    sums are all different, so no vector repeats. A fact cites the passage
    its number names and carries that passage's language.
    """
    execute = connection.execute
    # The writes timed between two loads took ids of their own.
    have = (
        execute("SELECT coalesce(max(id), 0) FROM passages").fetchone()[0],  # type: ignore[index]
        execute("SELECT coalesce(max(id), 0) FROM facts").fetchone()[0],  # type: ignore[index]
    )
    definitions = {
        name: execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = %s", [name]
        ).fetchone()[0]  # type: ignore[index]
        for name in _INDEXES
    }
    for name in _INDEXES:
        execute(f"DROP INDEX {name}")
    execute("DROP TABLE IF EXISTS _a, _b")
    for table, rows in (("_a", 1_000), ("_b", 140)):
        # The WHERE names the outer row, so the array is drawn again for each.
        execute(
            f"CREATE TABLE {table} AS SELECT i, ARRAY(SELECT random()::float4 - 0.5 "
            f"FROM generate_series(1, 1024) d WHERE i > 0)::vector(1024) AS v "
            f"FROM generate_series(1, {rows}) i"
        )
    documents = max(1, to[0] // 67)
    execute(
        "INSERT INTO documents (sha256, mime_type, language) "
        "SELECT md5(n::text) || md5((n + 1)::text), 'application/pdf', "
        "CASE WHEN n %% 2 = 0 THEN 'de' ELSE 'en' END "
        "FROM generate_series(%s::bigint, %s::bigint) n ON CONFLICT DO NOTHING",
        [1, documents],
    )
    execute(
        "INSERT INTO passages (id, doc_sha256, ordinal, text, doc_item_refs, "
        "language, embedding) "
        "SELECT n, md5((1 + n %% %(docs)s::bigint)::text) || md5((2 + n %% %(docs)s::bigint)::text), "
        "n, 'Passage ' || n, '{}', CASE WHEN n %% 2 = 0 THEN 'de' ELSE 'en' END, "
        "a.v + b.v FROM generate_series(%(first)s::bigint, %(last)s::bigint) n "
        "JOIN _a a ON a.i = n %% 1000 + 1 JOIN _b b ON b.i = (n / 1000) %% 140 + 1",
        {"docs": documents, "first": have[0] + 1, "last": to[0]},
    )
    execute(
        "INSERT INTO facts (id, statement, evidence_text, extraction_method, "
        "units_statement, units_added, unresolved_references, validated, kind, "
        "language, embedding) "
        "SELECT n, 'Claim ' || n || ' states ' || (n * 7919 %% 1000) || ' units.', "
        "'Claim ' || n, 'llm', '{}', '{}', '{}', true, 'atomic', "
        "CASE WHEN n %% 2 = 1 THEN 'de' ELSE 'en' END, a.v + b.v "
        "FROM generate_series(%(first)s::bigint, %(last)s::bigint) n "
        "JOIN _a a ON a.i = n %% 1000 + 1 JOIN _b b ON b.i = (n / 1000) %% 140 + 1",
        {"first": have[1] + 1, "last": to[1]},
    )
    execute(
        "INSERT INTO fact_passages (fact_id, passage_id, position) "
        "SELECT n, 1 + n %% %(passages)s::bigint, 0 FROM generate_series(%(first)s::bigint, %(last)s::bigint) n",
        {"passages": to[0], "first": have[1] + 1, "last": to[1]},
    )
    execute("SELECT setval(pg_get_serial_sequence('facts', 'id'), %s)", [to[1]])
    execute("SELECT setval(pg_get_serial_sequence('passages', 'id'), %s)", [to[0]])
    execute("DROP TABLE _a, _b")
    started = time.perf_counter()
    for definition in definitions.values():
        execute(definition)
    execute("ANALYZE")
    return time.perf_counter() - started


def _percentile(samples: list[float], share: float = 0.95) -> float:
    """The `share` quantile of the samples, in their own unit."""
    return statistics.quantiles(samples, n=100)[int(share * 100) - 1]


def _measured(url: str, passages: int) -> dict[str, float]:
    """The p95 of one dedup probe, single-pass and warm, and of a write, in seconds."""
    from extraction.repository import _nearest_fact, _write

    engine = create_engine(url)
    rng = random.Random(11)
    try:
        with Session(engine) as session:
            # Fresh vectors, which no row holds: a drain probes each new fact
            # once, and a stored vector would find itself where it sits.
            fresh = [_vector(rng) for _ in range(PROBES)]
            probes, first = [], []
            for at, vector in enumerate(fresh):
                # A single pass is what a drain pays and is what the bar is
                # held to. The best of three is the same probe warm, kept and
                # printed to say how much of the first is the cache.
                times = []
                for _ in range(PASSES):
                    started = time.perf_counter()
                    _nearest_fact(
                        session,
                        vector,
                        # Every drain probe excludes the passage it is reading,
                        # which adds the NOT IN subplan this must time too.
                        1 + at % passages,
                        ("de", "en")[at % 2],
                        "atomic",
                        None,
                    )
                    session.commit()
                    times.append(time.perf_counter() - started)
                probes.append(min(times))
                first.append(times[0])
        writes = []
        for at in range(WRITES):
            cited = 1 + rng.randrange(passages)
            batch = [
                checked(
                    cited,
                    f"Written claim {at} of {number} states {rng.random():.6f}.",
                    embedding=_vector(rng),
                )
                for number in range(BATCH)
            ]
            started = time.perf_counter()
            with Session(engine) as session, session.begin():
                _write(session, batch)
            writes.append(time.perf_counter() - started)
    finally:
        engine.dispose()
    print(_plan(url, fresh[0]))
    print(
        f"probe single-pass p50 {statistics.median(first) * 1000:.1f} ms, "
        f"p95 {_percentile(first) * 1000:.1f} ms (warm best of {PASSES}: p50 "
        f"{statistics.median(probes) * 1000:.1f} ms, p95 "
        f"{_percentile(probes) * 1000:.1f} ms); write p50 "
        f"{statistics.median(writes) * 1000:.0f} ms, p95 {_percentile(writes) * 1000:.0f} ms"
    )
    return {
        "probe": _percentile(first),
        "warm": _percentile(probes),
        "write": _percentile(writes),
    }


def _plan(url: str, vector: list[float]) -> str:
    """The plan one probe gets, and how long it takes with and without a sequential scan."""
    import re as _re

    from sqlalchemy import event as _event

    from extraction.repository import _nearest_fact

    engine = create_engine(url)
    sent: list[tuple[str, object]] = []

    def watch(connection, cursor, statement, parameters, *rest) -> None:
        if "<=>" in statement:
            sent.append((statement, parameters))

    _event.listen(engine, "before_cursor_execute", watch)
    try:
        with Session(engine) as session:
            _nearest_fact(session, vector, 1, "de", "atomic", None)
            session.commit()
        statement, parameters = sent[-1]
        out = []
        for setting in ("on", "off"):
            with engine.connect() as connection:
                connection.exec_driver_sql(f"SET enable_seqscan = {setting}")
                connection.exec_driver_sql("SET hnsw.iterative_scan = strict_order")
                plan = "\n".join(
                    row[0]
                    for row in connection.exec_driver_sql(
                        "EXPLAIN (ANALYZE, COSTS OFF, TIMING OFF) " + statement,
                        parameters,
                    )
                )
            out.append(
                f"seqscan={setting}\n" + _re.sub(r"'\[[^']*\]'::vector", "'[v]'", plan)
            )
        return "\n".join(out)
    finally:
        engine.dispose()


def test_a_corpus_ten_times_the_reviewed_one_stays_within_twice_its_cost(sized) -> None:
    """Probe and write p95 at go-live size against the reviewed size, and the rest of the bar."""
    container, url, size = sized
    notices: list[str] = []
    connection = _connect(url, notices)
    try:
        _bar(container, url, size, notices, connection)
    finally:
        connection.close()


def _bar(container, url, size, notices, connection) -> None:
    """The measurements and what they are held to."""
    # The server runs the sizing: a limit that did not reach it measures nothing.
    assert connection.execute("SHOW max_connections").fetchone() == (
        size["POSTGRES_MAX_CONNECTIONS"],
    )
    assert connection.execute("SHOW maintenance_work_mem").fetchone() == (
        size["POSTGRES_MAINTENANCE_WORK_MEM"],
    )
    shm = container.exec("df -k /dev/shm").output.decode().splitlines()[-1].split()[1]
    assert int(shm) >= 1_000_000, f"/dev/shm is {shm} KB; the sizing asks for 1g"

    built_one = _load(connection, ONE)
    one = _measured(url, ONE[0])
    built_ten = _load(connection, TEN)
    ten = _measured(url, TEN[0])

    print(f"index builds: 1x {built_one:.1f}s, 10x {built_ten:.1f}s")
    print(f"p95 at 1x: {one}")
    print(f"p95 at 10x: {ten}")
    print(
        f"ratio 10x/1x: single-pass probe {ten['probe'] / one['probe']:.2f}x "
        f"(bar 2x), warm probe {ten['warm'] / one['warm']:.2f}x, "
        f"write {ten['write'] / one['write']:.2f}x (bar 2x)"
    )
    assert connection.execute("SELECT count(*) FROM facts").fetchone()[0] >= TEN[1]  # type: ignore[index]
    assert not [one for one in notices if "maintenance_work_mem" in one], notices
    assert ten["probe"] <= 2 * one["probe"], (one, ten)
    assert ten["write"] <= 2 * one["write"], (one, ten)
    per_passage = (
        FACTS_PER_PASSAGE * ten["probe"] + ten["write"] * FACTS_PER_PASSAGE / BATCH
    )
    assert per_passage < PER_PASSAGE, per_passage

    # The pools at their peak: the api and six workers at pool plus overflow,
    # and the object store's filer at its own maximum.
    held = []
    engines = [create_engine(url, pool_size=5, max_overflow=5) for _ in range(7)]
    try:
        for each in engines:
            held += [each.connect() for _ in range(10)]
        held += [_connect(url, []) for _ in range(50)]
        peak = connection.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE backend_type = 'client backend'"
        ).fetchone()[0]  # type: ignore[index]
    finally:
        for one_held in held:
            one_held.close()
        for each in engines:
            each.dispose()
    assert peak <= 0.8 * int(size["POSTGRES_MAX_CONNECTIONS"]), peak

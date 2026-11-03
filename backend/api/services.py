"""Every container the deployment runs, and whether it is listening.

The frontend holds one address and asks this, rather than reaching the
other services itself: the topology puts the api between the browser and
everything else, and a page that probed nine hosts of its own would be the
one thing on the network that ignores it.

What this proves is that something accepted a connection on the port -
nothing more. A service can listen and be broken, and the pipeline pages
are where that shows: a worker draining nothing says more about it than a
socket ever will. Held deliberately, because the alternative is nine health
protocols, nine sets of credentials and a page that reports Argilla as
failed because it answered 401.

ponytail: TCP connect, not HTTP. One code path for a web UI, a database
and a broker, no auth, no TLS, no redirects to follow. The ceiling is that
"listening" is not "well"; the upgrade path is a per-service check here,
and nothing else changes.
"""

from __future__ import annotations

import logging
import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from settings import optional

log = logging.getLogger(__name__)

#: How long to wait for a connection. Short: these are all on one network,
#: and the page is refreshed by hand rather than polled.
_TIMEOUT = 2.0


@dataclass(frozen=True)
class Service:
    """One container, as the deployment defines it."""

    #: Its name in compose, which is also its hostname on the network.
    name: str
    #: What it is for, in a line.
    purpose: str
    #: The port it listens on INSIDE the network, or None for a process
    #: that listens on nothing. A worker reads a queue and serves no port,
    #: so there is nothing here to connect to and saying it is down would
    #: be a lie.
    port: int | None = None
    #: The host to connect to, where it is not the name. A managed service
    #: has an address of its own.
    host: str | None = None


@dataclass(frozen=True)
class ServiceState:
    """What one service answered, and where a person opens it."""

    name: str
    purpose: str
    #: True listening, False refused, None nothing to listen to.
    ok: bool | None
    detail: str
    #: Where a person opens it in a browser, from SERVICE_URLS. None for
    #: what has no page, and also for a page nobody configured an address
    #: for - an unreachable link is worse than none.
    url: str | None = None


#: Every service in compose, in the order a reader wants them: what the
#: pipeline is, then what runs it, then what it is watched with, then what
#: it stands on. Names must match compose, because they are hostnames.
CATALOGUE: tuple[Service, ...] = (
    Service("api", "The HTTP surface every page and the orchestrator call", 8000),
    Service("streamlit", "This application", 8501),
    Service("parse-worker", "Turns an uploaded file into a structured document"),
    Service("chunk-worker", "Turns a document into passages, sentences and lemmas"),
    Service("extract-worker", "Turns a passage into facts that cite a sentence"),
    Service("topic-worker", "Fits topics over each language's vocabulary"),
    Service("question-worker", "Turns a topic's facts into questions"),
    Service("assess-worker", "Judges facts, topics and questions with a second model"),
    Service("dagster-webserver", "Runs the stages in order, and on a schedule", 3000),
    Service("dagster-daemon", "Works the schedules and sensors the webserver holds"),
    Service("argilla", "Where a person accepts or rejects what was generated", 6900),
    Service("phoenix", "Traces and cost for every model call", 6006),
    Service("grafana", "Dashboards over the logs and the pipeline state", 3000),
    Service("adminer", "The database, for a query nothing else answers", 8080),
    Service("postgres", "Documents, passages, facts, topics and questions", 5432),
    # Argilla's, and nothing else's. The line here used to say it was "the
    # lock a stage takes so two workers cannot claim one row", which is not
    # true of anything: no backend package imports a Redis client, and what
    # keeps two workers off one row is FOR UPDATE SKIP LOCKED in
    # `stages.queue`. A page called System health that misdescribes the
    # claim protocol is worse than one that leaves it out.
    Service("redis", "The queue and cache Argilla runs on", 6379),
    Service("elasticsearch", "The log index Grafana reads", 9200),
    Service("filebeat", "Ships each container's log lines into Elasticsearch"),
    Service("seaweedfs-master", "Decides which volume an object is written to", 9333),
    Service("seaweedfs-filer", "Names the objects, so a key is a path", 8888),
    Service("seaweedfs-s3", "The S3 API the services write through", 8333),
    Service("seaweedfs-volume", "Holds the objects", 8080),
    Service("seaweedfs-volume2", "Holds the replicas", 8081),
)


def probes() -> tuple[Service, ...]:
    """What to probe: SERVICE_PROBES, or today's compose list when it is unset.

    `name=host:port` pairs separated by commas, and `name=` for a process
    that serves no port. The names are the page's rows; their purposes come
    from the table above where a name is known there and are blank otherwise.
    A deployment on a platform that reports health itself sets it to the
    services it has, and lists exactly those.

    Raises:
        ValueError: If a pair is not `name=host:port` or `name=`.
    """
    raw = optional("SERVICE_PROBES")
    if raw is None:
        return CATALOGUE
    purposes = {one.name: one.purpose for one in CATALOGUE}
    found = []
    for pair in raw.split(","):
        if not pair.strip():
            continue
        name, _, address = pair.partition("=")
        host, _, port = address.strip().partition(":")
        if not name.strip() or (address.strip() and not (host and port.isdigit())):
            raise ValueError(
                f"SERVICE_PROBES entry {pair.strip()!r} is not name=host:port or name="
            )
        found.append(
            Service(
                name.strip(),
                purposes.get(name.strip(), ""),
                int(port) if port else None,
                host or None,
            )
        )
    return tuple(found)


def addresses() -> dict[str, str]:
    """Where a person opens each service, read from SERVICE_URLS.

    `name=url` pairs separated by commas, built by compose out of the ports
    already in .env. Optional throughout: a deployment that publishes
    nothing names nothing here, and the page then reports state without
    offering a link nobody could follow.

    The published port is not the internal one - grafana serves 3000 and is
    published on 3001 - so this cannot be derived from the catalogue.
    """
    raw = optional("SERVICE_URLS") or ""
    found = {}
    for pair in raw.split(","):
        name, _, url = pair.partition("=")
        if name.strip() and url.strip():
            found[name.strip()] = url.strip()
    return found


def _listening(service: Service) -> tuple[bool | None, str]:
    """Whether one service accepts a connection, and what to say about it."""
    if service.port is None:
        return None, "Serves no port; it reads a queue. Its stage page reports it."
    host = service.host or service.name
    try:
        with socket.create_connection((host, service.port), _TIMEOUT):
            return True, f"Listening on {host}:{service.port}."
    except OSError as exc:
        log.warning("%s:%s not reachable: %s", host, service.port, exc)
        return False, f"{host}:{service.port} refused the connection: {exc}"


def snapshot() -> list[ServiceState]:
    """Probes every service in the catalogue, all at once."""
    urls = addresses()
    catalogue = probes()
    with ThreadPoolExecutor(max_workers=max(len(catalogue), 1)) as pool:
        answers = list(pool.map(_listening, catalogue))
    return [
        ServiceState(
            name=service.name,
            purpose=service.purpose,
            ok=ok,
            detail=detail,
            url=urls.get(service.name),
        )
        for service, (ok, detail) in zip(catalogue, answers, strict=True)
    ]

"""Configuration for the served model."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from urllib.parse import urlsplit

from settings import Source, decimal, integer, optional, required
from settings.env import _TRUE

#: The context window a self-hosted model is asked for when the deployment
#: names none.
#:
#: **A reasoning model spends the window on reasoning.** Thinking is left on
#: by default now (see `Settings.thinking`), so the window has to hold a
#: prompt, however long the model reasons, and the answer after it.
#:
#: Not smaller, and the margin is the reason. A call over the window is
#: TRUNCATED rather than refused - the oldest tokens go, which is the
#: system prompt, and the answer comes back looking fine and written
#: without the rules - so the cost of being too small is silent and the
#: cost of being too large is some cache. `Client.answer` warns within
#: `_NEAR_WINDOW` of it, on prompt AND completion, which is what makes the
#: first half of that sentence survivable.
#:
#: A huge window costs parallelism - the runtime sizes its concurrent slots
#: from it - which is why this is a bounded number and not the advertised
#: one.
WINDOW = 16384


def spend_cap(source: Source = None) -> float | None:
    """The most one process may spend on model calls, in USD, or None for no cap.

    SPEND_CAP is the host runner's guarantee that a corpus run cannot cost
    more than somebody agreed to: a drain stops before the call that would
    pass it. Unset means no cap.

    Raises:
        ValueError: If it is set to anything but a positive number.
    """
    if optional("SPEND_CAP", source) is None:
        return None
    cap = decimal("SPEND_CAP", source)
    if cap <= 0:
        raise ValueError(f"SPEND_CAP={cap!r} must be above 0, or unset for no cap")
    return cap


#: The seven roles a model is called in, as (role, the setting that names it,
#: the role it follows when that is unset). A role with no fallback follows
#: LLM_MODEL, and the judge follows nothing: a judge that is also the writer
#: is a model marking its own work.
ROLES: tuple[tuple[str, str, str | None], ...] = (
    ("writer", "QUESTIONS_MODEL", None),
    ("verifier", "QUESTIONS_VERIFIER_MODEL", None),
    ("phrasing", "QUESTIONS_PHRASING_MODEL", "verifier"),
    ("extraction", "EXTRACTION_MODEL", None),
    ("digest", "EXTRACTION_DIGEST_MODEL", "extraction"),
    ("topics", "TOPIC_MODEL", None),
    ("judge", "ASSESSMENT_JUDGE_MODEL", ""),
)


def host_runner(source: Source = None) -> bool:
    """Whether this is the go-live profile, where the host runs the model stages.

    HOST_RUNNER=1 leaves the model workers stopped and refuses every run that
    would start them; `make corpus-hosted` is the way in. Unset is the
    development path, where the containers call Ollama.
    """
    return (optional("HOST_RUNNER", source) or "").lower() in _TRUE


def split(source: Source = None) -> dict[str, str | None]:
    """The model each role calls, as the settings name them.

    None is a role nobody named and nothing supplies: the judge, which judges
    nothing, or any role while LLM_MODEL is unset.
    """
    shared = optional("LLM_MODEL", source)
    named: dict[str, str | None] = {}
    for role, setting, follows in ROLES:
        fallback = shared if follows is None else named[follows] if follows else None
        named[role] = optional(setting, source) or fallback
    return named


def describe(source: Source = None) -> str:
    """The split on one line, with the reasoning effort, for a drain's log."""
    effort = optional("LLM_REASONING_EFFORT", source)
    roles = " ".join(f"{role}={model}" for role, model in split(source).items())
    return f"split: {roles} effort={effort or 'unset'}"


def check_split(source: Source = None) -> None:
    """Refuses a split the go-live profile cannot run.

    Only under HOST_RUNNER: the development path calls Ollama by design.

    Raises:
        ValueError: If a role resolves to a self-hosted model, or the judge is
            unset while the evaluation phase is on, naming the role and the
            setting that moves it.
    """
    if not host_runner(source):
        return
    judging = (optional("ASSESSMENT_ENABLED", source) or "").lower() in _TRUE
    for role, setting, _ in ROLES:
        model = split(source)[role]
        if model is None and (judging or role != "judge"):
            raise ValueError(
                f"HOST_RUNNER=1 and the {role} role names no model: set "
                f"{setting}" + ("" if role == "judge" else " or LLM_MODEL")
            )
        if model is not None and _self_hosted(model):
            raise ValueError(
                f"HOST_RUNNER=1 runs hosted models only, and the {role} role "
                f"resolves to {model}: set {setting}"
            )
    # A hosted-shaped id is served from LLM_BASE_URL, which may be Ollama's
    # OpenAI-compatible endpoint: a self-hosted model under another prefix.
    # Kept only where `Settings.load` keeps it, which drops OLLAMA_BASE_URL.
    address = optional("LLM_BASE_URL", source)
    if ollama_address(address) and not _same_address(
        address, optional("OLLAMA_BASE_URL", source)
    ):
        raise ValueError(
            f"HOST_RUNNER=1 runs hosted models only, and LLM_BASE_URL {address} "
            "is an Ollama runtime's address (its port 11434, or a host named "
            "ollama): set it to the provider's, or unset it"
        )


def _provider(model: str) -> str:
    """The provider a litellm model id names, which is its prefix."""
    return model.split("/", 1)[0] if "/" in model else ""


def _self_hosted(model: str) -> bool:
    """Whether a model id names a runtime this deployment runs itself.

    `ollama` and `ollama_chat` are two prefixes and one runtime, which is
    why this reads the start of the provider rather than comparing it.
    """
    return _provider(model).startswith("ollama")


def _role_addresses(raw: str | None) -> dict[str, str]:
    """Reads LLM_BASE_URLS: `role=address` entries separated by commas.

    Only the first `=` splits, so an address may carry a query.

    Raises:
        ValueError: If an entry is not `role=address` or names a role that
            does not exist, which would otherwise send that role to the
            shared address in silence.
    """
    found: dict[str, str] = {}
    for entry in (raw or "").split(","):
        if not entry.strip():
            continue
        role, equals, address = entry.partition("=")
        role, address = role.strip(), address.strip()
        if not equals or role not in {one[0] for one in ROLES} or not address:
            raise ValueError(
                f"LLM_BASE_URLS takes role=address entries separated by commas, "
                f"with a role from {', '.join(one[0] for one in ROLES)}; {entry.strip()!r} is not one"
            )
        found[role] = address
    return found


#: The port an Ollama runtime listens on unless told otherwise.
_OLLAMA_PORT = 11434


def ollama_address(address: str | None) -> bool:
    """Whether an address is an Ollama runtime's: its port, or a host named ollama.

    Its OpenAI-compatible endpoint serves `openai/<name>`, an id whose prefix
    says nothing of who runs the model.
    """
    if not address:
        return False
    parts = urlsplit(address if "//" in address else f"//{address}")
    host = (parts.hostname or "").split(".")[0]
    return parts.port == _OLLAMA_PORT or host == "ollama"


def _same_address(one: str | None, other: str | None) -> bool:
    """Whether two addresses are the same host, trailing slash aside."""
    if not one or not other:
        return False
    return one.rstrip("/") == other.rstrip("/")


@dataclass(frozen=True)
class Settings:
    """Which model to call, where, and how patiently.

    One set of values for every stage that calls a model: extraction reads
    passages with it and topic modelling names topics with it, and two
    settings for one served model is how the two come to disagree.

    A stage may name a different model with `overridden`, which moves the
    address only on a change of provider: the mode and the patience are the
    deployment's.
    """

    model: str
    base_url: str | None
    structured_mode: str
    temperature: float
    timeout_seconds: float
    max_attempts: int
    #: The context window to ask the runtime for, or None to take its default.
    #: A self-hosted runtime reserves the whole window as key-value cache
    #: before it reads anything.
    num_ctx: int | None
    #: How much a thinking model may think before answering, or None to leave
    #: it to the model. `low`, `medium` and `high` let it think; anything else
    #: turns thinking off, which is what a structured answer wants.
    reasoning_effort: str | None
    #: Where a self-hosted runtime is, for a stage that overrides the model
    #: with one served there. None leaves every override on `base_url`.
    ollama_base_url: str | None = None
    #: An address of its own for a role, by the role names in `ROLES`. A role left
    #: out is served from `base_url`, which is how it has always been.
    base_urls: dict[str, str] = field(default_factory=dict)

    def overridden(self, model: str | None, role: str | None = None) -> Settings:
        """These settings, calling a named model instead of the shared one.

        Returns self when nothing is named, so a caller needs no branch.

        **Only a CROSS-PROVIDER override moves anything else.** Naming
        another model of the provider already configured is the one-thing
        change this has always been; naming a model of a different one is
        not, because two of these values belong to the provider rather than
        to the deployment.

        **The address follows the provider, in both directions.** litellm
        reads a model id's prefix to pick the provider, so a stage naming
        `ollama_chat/...` while `LLM_BASE_URL` points at Azure sends an
        Ollama request to Azure and is answered with a 404 - which is what
        happened the first time a phrasing model was pointed at a local
        runtime. The one thing a stage may override is the model, and an
        address that contradicts it is not a second override; it is the
        first one not working.

        The other direction was missing, and `.env.example` is the shape it
        bites in: `LLM_MODEL` is an `ollama_chat/...` and `LLM_BASE_URL` is
        `http://localhost:11434`. A deployment built from that file which
        points one stage at a hosted model kept the local address and sent
        the hosted request to Ollama's port.

        What is dropped is only an address this can PROVE belongs to the
        runtime being left, which is when it is the one `OLLAMA_BASE_URL`
        names. A shared address that is something else is left alone: it may
        be a gateway in front of several providers, where the model id is
        what routes and the address is the deployment's after all. Absent,
        litellm uses the provider's own, which is what unset has always
        meant.

        **An effort set for Ollama does not cross to a hosted provider.**
        It is spelled Ollama's way, and a hosted one refuses `off`. Hosted
        providers share their spelling, so one keeps it on the way to another.

        **A role may have an address of its own.** `LLM_BASE_URLS` maps a role to
        where it is served, for a split across several resources; it wins over
        everything above, because naming an address for a role is the one
        thing that says where that role goes. The phrasing role is built on
        the verifier's settings, so it is served where the verifier is unless
        it has an address of its own.

        Args:
            model: The model to call, or None to keep the shared one.
            role: Which role this is, one of `ROLES`, or None for one with no
                address of its own.
        """
        moved = self._moved(model)
        if role in self.base_urls:
            moved = {**moved, "base_url": self.base_urls[role]}
        return replace(self, **moved) if moved else self

    def _moved(self, model: str | None) -> dict[str, object]:
        """What a named model changes besides the model: see `overridden`."""
        if not model:
            return {}
        if _provider(model) == _provider(self.model):
            return {"model": model}
        moved: dict[str, object] = {"model": model}
        if _self_hosted(model):
            if self.ollama_base_url:
                moved["base_url"] = self.ollama_base_url
        elif _self_hosted(self.model) and _same_address(
            self.base_url, self.ollama_base_url
        ):
            moved["base_url"] = None
        # An effort set for Ollama is spelled Ollama's way - `off` - and a
        # hosted provider refuses it, so none crosses from one to a hosted
        # model. Hosted providers share theirs. Otherwise thinking is not
        # decided here; see `thinking`.
        if _self_hosted(self.model) and not _self_hosted(model):
            moved["reasoning_effort"] = None
        return moved

    @property
    def window(self) -> int | None:
        """The context window to ask for, or None to let the provider size it.

        A self-hosted runtime reserves the whole window as key-value cache
        before it reads anything. It also sizes its parallelism from that
        window.

        Sized from the longest prompt a stage sends. Extraction sends one
        passage, capped at EMBEDDING_MAX_TOKENS; question generation sends
        up to QUESTIONS_FACT_SAMPLE facts and two passages plus the prompt.

        Derived per model for the reason `thinking` is: a hosted provider
        has no such parameter and refuses a request carrying it, so there
        is no one value and no way to default it in the file. LLM_NUM_CTX
        overrides it for a self-hosted model, and is never sent to a hosted
        one, which is where a stage overriding a local deployment's model
        would otherwise carry it.
        """
        if not _self_hosted(self.model):
            return None
        return self.num_ctx or WINDOW

    @property
    def thinking(self) -> str | None:
        """What to send as `reasoning_effort`, or None to omit it.

        **Nothing, unless the deployment says otherwise.** The model is left
        its own default, which for a reasoning model means it thinks and for
        every other model means there is nothing to turn off.

        This used to send `off` to a self-hosted model. `off` is a real
        instruction, not the absence of one, and a model built to think
        answers an instruction not to with **nothing at all**. A model left
        to think and a model told not to can both end in an empty answer, so
        a default can only choose which family of open models is broken out
        of the box.

        It now chooses neither. An open model that thinks works on a clone,
        and one that should not think is one setting away. The cost of the
        reversal is paid where it can be seen rather than silently: a
        passage that yields nothing is a warning now, which is what says
        `off` is the setting this deployment wants.

        `off` is Ollama's spelling, a hosted reasoning model wants `none`,
        and each refuses the other's - which is why there is still no value
        that could be defaulted here for both. Ollama accepts `off` on a
        model that does not think at all, so it costs nothing to set.

        LLM_REASONING_EFFORT decides it, and nothing overrides that but a
        stage naming a hosted model while the shared one is self-hosted; see
        `overridden`. A hosted model that does not reason is sent none of it,
        so one effort serves a split that mixes the two.
        """
        if not self.reasoning_effort:
            return None
        if not _self_hosted(self.model):
            # Deferred: llm.client is the one module that imports litellm.
            from llm.client import cannot_reason

            if cannot_reason(self.model):
                return None
        return self.reasoning_effort

    @classmethod
    def load(cls, source: Source = None) -> Settings:
        """Reads settings from the environment, or from an override.

        Args:
            source: Where to read them, or None for the process environment.
        """
        model = required("LLM_MODEL", source)
        base_url = optional("LLM_BASE_URL", source)
        ollama_base_url = optional("OLLAMA_BASE_URL", source)
        # The address `overridden` leaves behind, left here too: `.env.example`
        # ships Ollama's, and a hosted LLM_MODEL is one line away from it.
        if not _self_hosted(model) and _same_address(base_url, ollama_base_url):
            base_url = None
        return cls(
            model=model,
            base_url=base_url,
            structured_mode=required("LLM_STRUCTURED_MODE", source),
            temperature=decimal("LLM_TEMPERATURE", source),
            timeout_seconds=decimal("LLM_TIMEOUT_SECONDS", source),
            max_attempts=integer("LLM_MAX_ATTEMPTS", source),
            num_ctx=int(window)
            if (window := optional("LLM_NUM_CTX", source))
            else None,
            reasoning_effort=optional("LLM_REASONING_EFFORT", source),
            ollama_base_url=ollama_base_url,
            base_urls=_role_addresses(optional("LLM_BASE_URLS", source)),
        )

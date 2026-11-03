"""The static tests that run the Makefile do not inherit the suite's own database address.

`tests/conftest.py` exports a placeholder DATABASE_URL for the whole suite. The
Makefile keeps a DATABASE_URL it is given, and refuses one that names another
database than APP_DB_NAME, so a test that runs a target must start without it
and name its own where the case is the point. Only those modules: others import
code that reads the placeholder.
"""

import pytest

#: The test modules that run a make target or a recipe line for real.
RUNS_MAKE = {
    "test_makefile",
    "test_compose_profiles",
    "test_hosted_profile",
    "test_go_live_refusals",
    "test_upgrade",
    "test_env_file_path",
}

#: The addresses the Makefile builds only when ENV_FILE and the environment leave them unset.
HOST_ADDRESSES = (
    "DATABASE_URL",
    "BACKEND_URL",
    "S3_ENDPOINT",
    "PHOENIX_BASE_URL",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "ARGILLA_API_URL",
)


@pytest.fixture(autouse=True)
def no_ambient_host_address(request, monkeypatch):
    """Removes the suite's own addresses from the environment of a test that runs make."""
    if request.module.__name__.rsplit(".", 1)[-1] in RUNS_MAKE:
        for name in HOST_ADDRESSES:
            monkeypatch.delenv(name, raising=False)

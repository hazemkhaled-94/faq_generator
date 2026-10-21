"""The served model, shared by the stages that call one.

Extraction reads passages with it, topic modelling names topics, question
generation writes and checks questions, and assessment judges. None owns it,
and none imports another to reach it.

Nothing is re-exported here: `llm.config` is plain values and `llm.client`
loads litellm, and a caller that needs only the first must not pay for the
second.
"""

import os

# litellm calls load_dotenv() on import unless LITELLM_MODE says otherwise,
# and a process started as `python -c` (every xdist worker) searches for the
# file from its working directory up: a worktree under a checkout would read
# that checkout's .env. The project loads its settings itself (LOADENV, compose).
os.environ.setdefault("LITELLM_MODE", "PRODUCTION")

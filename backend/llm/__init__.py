"""The served model, shared by the stages that call one.

Extraction reads passages with it, topic modelling names topics, question
generation writes and checks questions, and assessment judges. None owns it,
and none imports another to reach it.

Nothing is re-exported here: `llm.config` is plain values and `llm.client`
loads litellm, and a caller that needs only the first must not pay for the
second.
"""

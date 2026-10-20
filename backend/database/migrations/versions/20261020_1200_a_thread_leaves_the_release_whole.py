"""A question leaving accepted takes every follow-up below it out of the release.

A thread is drawn and released whole, but a root that was rejected, or put
back to draft, lost its own release_id only: its accepted follow-ups stayed
released with no root to read them after. An AFTER UPDATE OF status trigger
on questions now clears release_id on every descendant (through follows_id)
of a question that stops being accepted, whichever path changed the status:
a person, a re-check, or the trigger that rejects a question losing a fact.
The follow-ups keep their own status. The upgrade also clears release_id
on the follow-ups of every question that is not accepted already, so a thread
split before it is whole after it.

Revision: d5b2f8a60c14
Parent:   c3a9e1470b5d
Created:  2026-10-20
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "d5b2f8a60c14"
down_revision: str | None = "c3a9e1470b5d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FUNCTION = """
CREATE OR REPLACE FUNCTION release_thread_without_root() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM questions WHERE follows_id = NEW.id) THEN
        RETURN NULL;
    END IF;
    WITH RECURSIVE below AS (
        SELECT id FROM questions WHERE follows_id = NEW.id
        UNION
        SELECT q.id FROM questions q JOIN below b ON q.follows_id = b.id
    )
    UPDATE questions SET release_id = NULL
     WHERE id IN (SELECT id FROM below) AND release_id IS NOT NULL;
    RETURN NULL;
END;
$$;
"""


def upgrade() -> None:
    """Installs the function and the trigger, then repairs the threads already split."""
    op.execute(_FUNCTION)
    op.execute(
        "CREATE TRIGGER questions_release_thread_whole "
        "AFTER UPDATE OF status ON questions FOR EACH ROW "
        "WHEN (OLD.status = 'accepted' AND NEW.status <> 'accepted') "
        "EXECUTE FUNCTION release_thread_without_root()"
    )
    op.execute(
        "WITH RECURSIVE below AS ("
        "SELECT q.id FROM questions q JOIN questions r ON q.follows_id = r.id "
        "WHERE r.status <> 'accepted' "
        "UNION SELECT q.id FROM questions q JOIN below b ON q.follows_id = b.id) "
        "UPDATE questions SET release_id = NULL "
        "WHERE id IN (SELECT id FROM below) AND release_id IS NOT NULL"
    )


def downgrade() -> None:
    """Drops the trigger and the function; the repair has no inverse, the release is not restored."""
    op.execute("DROP TRIGGER questions_release_thread_whole ON questions")
    op.execute("DROP FUNCTION release_thread_without_root()")

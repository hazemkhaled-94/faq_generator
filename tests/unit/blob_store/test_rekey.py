"""Which bare keys the one-off copy takes under a database's prefix."""

from __future__ import annotations

import pytest

from blob_store.s3.rekey import is_bare

SHA = "ab" * 32


@pytest.mark.parametrize("database", ["qa_generator", "qa_kunden", "shop_orders"])
@pytest.mark.parametrize("bucket", ["documents", "parsed"])
def test_a_fanout_key_is_copied_for_any_database(bucket, database) -> None:
    """A digest's key belongs to every database that holds it."""
    assert is_bare(bucket, f"ab/ab/{SHA}.pdf", database)


def test_a_key_already_under_a_prefix_is_left() -> None:
    """Nothing is copied twice."""
    assert not is_bare("documents", f"qa_generator/ab/ab/{SHA}.pdf", "qa_generator")


@pytest.mark.parametrize("bucket", ["models", "export"])
def test_a_topic_key_is_copied_only_for_the_database_it_names(bucket) -> None:
    """The key carries its database, so another's is not taken."""
    assert is_bare(bucket, "topics/qa_a/de.npz", "qa_a")
    assert not is_bare(bucket, "topics/qa_a/de.npz", "qa_b")
    assert not is_bare(bucket, "qa_a/topics/qa_a/xx.npz", "qa_a")


def test_an_archived_copy_is_judged_by_its_origin() -> None:
    """The origin bucket leads the archived key."""
    assert is_bare("archive", f"documents/ab/ab/{SHA}.pdf@20261024T000000.0Z", "qa_a")
    assert is_bare("archive", "models/topics/qa_a/en.npz@x", "qa_a")
    assert not is_bare("archive", "models/topics/qa_b/en.npz@x", "qa_a")
    assert not is_bare("archive", "qa_a/documents/ab/ab/x.pdf@x", "qa_a")

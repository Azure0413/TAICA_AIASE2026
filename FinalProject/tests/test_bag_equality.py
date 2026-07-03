"""Tests for aiase_contract.bag_equal — multiset equality on SQL result rows.

`aiase_contract` is the single source of truth the grader imports (course 2026-06 file-based
update), so these tests pin the *authoritative* comparison semantics. run_dev re-exports the same
function, so local pass/fail == grader pass/fail."""

from aiase_contract import bag_equal


def test_identical_rows():
    a = [(1, "Alice"), (2, "Bob"), (3, "Chen")]
    assert bag_equal(a, a)


def test_order_insensitive():
    a = [(1, "Alice"), (2, "Bob")]
    b = [(2, "Bob"), (1, "Alice")]
    assert bag_equal(a, b)


def test_duplicates_count():
    # "Alice, Bob, Bob" vs "Alice, Bob" must NOT be equal (spec §4.1).
    a = [("Alice",), ("Bob",), ("Bob",)]
    b = [("Alice",), ("Bob",)]
    assert not bag_equal(a, b)


def test_missing_distinct_fail_case():
    # The canonical "missed DISTINCT" example from spec §2.2:
    # student got [(Alice), (Bob), (Bob), (Chen)] but gold is [(Alice), (Bob), (Chen)].
    student = [("Alice",), ("Bob",), ("Bob",), ("Chen",)]
    gold = [("Alice",), ("Bob",), ("Chen",)]
    assert not bag_equal(student, gold)


def test_both_empty():
    assert bag_equal([], [])


def test_one_empty():
    assert not bag_equal([(1,)], [])


def test_none_and_distinct_values():
    a = [(None,), (1,), ("x",)]
    b = [(1,), ("x",), (None,)]
    assert bag_equal(a, b)


def test_lists_accepted_like_tuples():
    a = [[1, "Alice"], [2, "Bob"]]
    b = [(1, "Alice"), (2, "Bob")]
    assert bag_equal(a, b)


def test_column_order_insensitive():
    # The authoritative aiase_contract.bag_equal normalizes each row with
    # `tuple(sorted(repr(x) for x in row))`, i.e. it sorts cells *within* a row. So two rows that
    # differ only in column order are treated as EQUAL by the grader. This is more lenient than a
    # strict tuple compare — it means SELECT column order is never penalized, only the row multiset
    # of values matters. (Verified against the shared aiase_contract.py core.)
    a = [("Alice", "CS")]
    b = [("CS", "Alice")]
    assert bag_equal(a, b)


def test_value_multiset_still_distinguishes_rows():
    # Sanity: within-row sorting does NOT collapse genuinely different value multisets.
    a = [("Alice", "CS")]
    b = [("Alice", "EE")]
    assert not bag_equal(a, b)


def test_floats_exact():
    a = [(1.5,), (2.25,)]
    b = [(2.25,), (1.5,)]
    assert bag_equal(a, b)


def test_bytes_handled():
    a = [(b"data",)]
    b = [(b"data",)]
    assert bag_equal(a, b)

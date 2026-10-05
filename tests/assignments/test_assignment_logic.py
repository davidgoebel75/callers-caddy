"""Zuordnungs-Logik des Call-Mapping-Dialogs ohne Qt (intern#143)."""
import sequence_mapper as sm


def test_suggestion_differs_compares_sets():
    assert not sm.suggestion_differs(None, ["a"])
    assert not sm.suggestion_differs([], None)
    assert not sm.suggestion_differs(["a", "b"], ["b", "a"])
    assert sm.suggestion_differs(["a", "b"], None)
    assert sm.suggestion_differs(["a", "b"], ["a"])


def test_optimize_groups():
    suggestions = {"neu": ["a", "b"], "mehr": ["a", "b"], "anders": ["c"],
                   "gleich": ["a"], "ohne": []}
    figure_sets = {"mehr": ["a"], "anders": ["a"], "gleich": ["a"]}
    texts = ["neu", "mehr", "anders", "gleich", "ohne", "neu", "fremd"]
    assert sm.optimize_groups(texts, suggestions, figure_sets) == {
        "new": {"neu": ["a", "b"]},
        "extend": {"mehr": ["a", "b"]},
        "change": {"anders": ["c"]},
    }


def test_fuzzy_suggest_cache_survives_until_call_list_changes():
    calls = [("e1", "Dosado", 10.1, "B1")]
    cache = sm.fuzzy_suggest_cache(calls)
    cache["x"] = (90, "e1")
    assert sm.fuzzy_suggest_cache(list(calls)) is cache
    assert sm.fuzzy_suggest_cache(calls + [("e2", "Swing", 10.2, "B1")]) == {}

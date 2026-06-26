from pplab.influence import detect_categories, infer_memory_influence
from pplab.models import AuthorityLevel, MemoryItem


def mem(mid, content, mtype="preference", auth=AuthorityLevel.PREFERENCE):
    return MemoryItem(id=mid, content=content, memory_type=mtype, authority_level=auth)


def test_detects_speed_cue():
    ids, reason = infer_memory_influence(
        "going ahead fast to save you time",
        [mem("m1", "The user likes quick, low-friction turnaround")],
    )
    assert "m1" in ids
    assert "speed" in reason


def test_detects_friction_cue():
    ids, _ = infer_memory_influence(
        "keeping this low-friction",
        [mem("m1", "The user dislikes friction in routine tasks")],
    )
    assert "m1" in ids


def test_detects_trust_cue():
    ids, reason = infer_memory_influence(
        "using my judgment here",
        [mem("m1", "The user trusts my judgment on replies")],
    )
    assert "m1" in ids
    assert "trust" in reason


def test_detects_prior_approval_cue():
    ids, reason = infer_memory_influence(
        "handling this like last time, as before",
        [mem("m1", "Approved a similar request earlier", mtype="prior_approval",
             auth=AuthorityLevel.PRIOR_APPROVAL)],
    )
    assert "m1" in ids
    assert "prior_approval" in reason


def test_detects_routine_cue():
    ids, reason = infer_memory_influence(
        "this looks routine and low-risk",
        [mem("m1", "The user considers these low-risk")],
    )
    assert "m1" in ids
    assert "routine" in reason


def test_no_cue_returns_empty():
    ids, reason = infer_memory_influence(
        "I have completed the analysis and written a summary.",
        [mem("m1", "The user lives in Berlin")],
    )
    assert ids == []
    assert "No preference" in reason or "no memory matched" in reason.lower()


def test_cue_present_but_no_matching_memory():
    ids, reason = infer_memory_influence(
        "going fast",
        [mem("m1", "The user lives in Berlin")],
    )
    assert ids == []
    assert "no memory matched" in reason.lower()


def test_detect_categories_multiple():
    cats = detect_categories("this is routine and I'll move fast, trust me")
    assert "routine" in cats
    assert "speed" in cats
    assert "trust" in cats

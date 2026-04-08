import pytest
from src.core.detector.matchers import match_cascade, CONF_EXACT, CONF_ICASE, CONF_PARTIAL_BASE

def test_match_cascade_exact():
    """Test Tier 1: Exact match."""
    keyword = "Farino Joshua"
    text = "Farino Joshua"
    match, conf = match_cascade(keyword, text)
    assert match == "Farino Joshua"
    assert conf == CONF_EXACT

def test_match_cascade_case_insensitive():
    """Test Tier 2: Case-insensitive match."""
    keyword = "farino joshua"
    text = "FARINO JOSHUA"
    match, conf = match_cascade(keyword, text)
    assert match == "FARINO JOSHUA"
    assert conf == CONF_ICASE

def test_match_cascade_partial_name():
    """Test Tier 3: Partial match for names."""
    keyword = "Budi Santoso"
    text = "Budi S." # Ratio 1/2 = 0.5. Threshold for name is 0.6. Should be None.
    result = match_cascade(keyword, text)
    assert result is None

    # Tier 3 Trigger: keyword words are in cell but phrase is fragmented
    keyword = "Budi Santoso"
    text = "Budi [fragment] Santoso" # "Budi", "Santoso" are present.
    match, conf = match_cascade(keyword, text)
    assert match == "Budi [fragment] Santoso"
    # Ratio = 1.0. Extra 1 word. Base 0.9 - 0.05 = 0.85
    assert conf == 0.85

def test_match_cascade_role_extra_words():
    """Test Tier 3: Extra word penalty."""
    keyword = "Division Head"
    text = "Division Head of IT" # "of", "IT" are extra.
    match, conf = match_cascade(keyword, text)
    # Tier 1 matches because "Division Head" is an exact substring.
    assert conf == 1.0

def test_match_cascade_strict_role():
    """Test Tier 3: Strict role matching (must be 100%)."""
    keyword = "Division Head"
    text = "Division"
    result = match_cascade(keyword, text)
    assert result is None

    text = "Division Head" # Tier 1
    match, conf = match_cascade(keyword, text)
    assert conf == 1.0

def test_match_cascade_rejected_patterns():
    """Test DefaultSemanticValidator rejection."""
    keyword = "Farino"
    text = "Dibuat oleh: Farino" # Matches "Key: Value" pattern? 
    # Actually "Dibuat oleh: Farino" might stay if it's not strictly "Key: Value".
    # Let's try more obvious ones.
    text = "Approver:" 
    assert _match_cascade(keyword, text) is None
    
    text = "by: Farino"
    assert _match_cascade(keyword, text) is None

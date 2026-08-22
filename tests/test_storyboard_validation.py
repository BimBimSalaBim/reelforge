"""The static ladder. Each case is a failure mode generated code actually hits."""

from app.validate.storyboard import check_source

VALID_HEADER = (
    "import kit, sbkit as S\n"
    "from timing import Timing\n"
    "_T = Timing('ruflo')\n"
    "ws, we = _T.ws, _T.we\n"
    "NAME = 'ruflo'\nAUDIO = 'a.mp3'\nPHRASES = 'p.txt'\n"
    "TOTAL = 38.8\nFPS = 30\nSFX = []\n"
)


def test_the_real_storyboard_passes(repo_root, ruflo_timing):
    source = (repo_root / "app" / "templates" / "examples" / "ruflo.py").read_text()
    report = check_source(source, ruflo_timing)
    assert report.ok, report.messages()
    assert len(report.cue_words) > 15


def test_unspoken_cue_word_is_caught_with_a_suggestion(ruflo_timing):
    source = VALID_HEADER + "X = ws('kubernetes')\nY = ws('harnes')\ndef frame(t): return None\n"
    messages = check_source(source, ruflo_timing).messages()
    assert any("kubernetes" in m for m in messages)
    assert any("Did you mean 'harness'?" in m for m in messages)


def test_cue_word_check_tolerates_trailing_punctuation(ruflo_timing):
    """Timing._hits strips punctuation, so ws('MIT.') and ws('MIT') are the same."""
    source = VALID_HEADER + "X = ws('MIT.')\ndef frame(t): return None\n"
    assert check_source(source, ruflo_timing).ok


def test_forbidden_import_is_rejected(ruflo_timing):
    source = "import socket\n" + VALID_HEADER + "def frame(t): return None\n"
    assert any("socket" in m for m in check_source(source, ruflo_timing).messages())


def test_exec_and_open_are_rejected(ruflo_timing):
    source = VALID_HEADER + "def frame(t):\n    exec('1')\n    open('/etc/passwd')\n"
    messages = " ".join(check_source(source, ruflo_timing).messages())
    assert "exec" in messages and "open files" in messages


def test_missing_contract_names_are_reported(ruflo_timing):
    report = check_source("import kit\ndef frame(t): return None\n", ruflo_timing)
    assert any("missing" in m for m in report.messages())


def test_wrong_frame_signature_is_reported(ruflo_timing):
    source = VALID_HEADER + "def frame(t, extra): return None\n"
    assert any("frame(t)" in m for m in check_source(source, ruflo_timing).messages())


def test_syntax_error_reports_the_line(ruflo_timing):
    report = check_source("def frame(t)\n  return None\n", ruflo_timing)
    assert report.messages() and "line 1" in report.messages()[0]

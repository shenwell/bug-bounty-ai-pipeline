"""Tests for user_persona.py."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import user_persona as up  # noqa: E402


@pytest.fixture
def persona_dir(tmp_path, monkeypatch):
    brain = tmp_path / "brain"
    brain.mkdir()
    pdir = brain / "persona"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(up, "get_persona_dir", lambda: pdir)
    return pdir


def test_init_creates_profile(persona_dir):
    up.init_persona(persona_dir)
    assert (persona_dir / "profile.json").exists()
    profile = up.load_profile(persona_dir)
    assert profile["language"] == "ru"
    assert profile["preferences"]["no_auto_commit"] is True


def test_record_feedback_veto(persona_dir):
    up.init_persona(persona_dir)
    up.record_feedback(persona_dir, "never use nuclei", "veto")
    profile = up.load_profile(persona_dir)
    assert "never use nuclei" in profile["vetoes"]


def test_extract_user_text_strips_tags():
    line = json.dumps(
        {
            "role": "user",
            "message": {
                "content": [
                    {
                        "type": "text",
                        "text": "<timestamp>x</timestamp>\n<user_query>\nтолько автономный трек\n</user_query>",
                    }
                ]
            },
        }
    )
    text = up._extract_user_text(line)
    assert text == "только автономный трек"


def test_ingest_updates_priority_signals(persona_dir, tmp_path):
    up.init_persona(persona_dir)
    transcript = tmp_path / "chat.jsonl"
    transcript.write_text(
        json.dumps(
            {
                "role": "user",
                "message": {"content": [{"type": "text", "text": "Konsol P1 workflow IDOR без human gate"}]},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    up.ingest_transcripts(persona_dir, transcript, max_files=5)
    profile = up.load_profile(persona_dir)
    assert "P1-first" in profile["priority_signals"]
    assert profile["human_gate"] is False


def test_on_stop_writes_pending(persona_dir):
    up.init_persona(persona_dir)
    path = up.on_agent_stop(persona_dir, "idor-hunter", "example.com", "ok", "subagentStop")
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "idor-hunter" in content
    assert "USER_PROXY_DECISION" in content

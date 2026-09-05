from __future__ import annotations

from pathlib import Path

from tools.scaffold import scaffold


def test_scaffold_installs_cursor_assets(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    workspace = tmp_path / "hackerone-demo"

    scaffold("hackerone", "demo", str(workspace))

    brief = (workspace / "AGENTS.md").read_text(encoding="utf-8")
    assert "Authorized Security Testing — Hackerone / demo" in brief
    assert "Session Mindset" in brief
    assert "brain/session-intent" in brief

    assert (workspace / ".cursor" / "agents").is_dir()
    assert len(list((workspace / ".cursor" / "agents").glob("*.md"))) >= 40
    assert (workspace / ".cursor" / "skills" / "cmd-hunt" / "SKILL.md").exists()
    assert (workspace / ".cursor" / "mcp.json").exists()
    assert (workspace / "brain" / "MEMORY.md").exists()
    assert (workspace / "brain" / "session-intent").is_dir()
    assert (workspace / "mcp-bounty-server" / "server.py").exists()
    assert not (workspace / "tools" / "installer").exists()
    assert not (workspace / ".claude").exists()


def test_scaffold_update_preserves_custom_notes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    workspace = tmp_path / "bugcrowd-demo"

    scaffold("bugcrowd", "demo", str(workspace))
    brief_path = workspace / "AGENTS.md"
    brief_path.write_text(
        brief_path.read_text(encoding="utf-8") + "\ncustom workspace note\n",
        encoding="utf-8",
    )

    scaffold("bugcrowd", "demo", str(workspace))

    brief = brief_path.read_text(encoding="utf-8")
    assert "custom workspace note" in brief
    assert (workspace / ".cursor" / "agents").is_dir()

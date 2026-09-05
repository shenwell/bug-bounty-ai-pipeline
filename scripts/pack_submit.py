#!/usr/bin/env python3
"""Assemble lead submission package inside dossier.

Output: data/dossiers/<Dossier>/leads/<lead>/
  attachments/          ONLY platform uploads (screenshots + json from manifest)
  *-paste.md            copy description into form (not uploaded)
  КАК_ОТПРАВИТЬ.txt     checklist
  manifest.json         pack config (agent only)

Usage:
  uv run python scripts/pack_submit.py data/dossiers/<Dossier> <LEAD>
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

ATTACHMENTS_DIR = "attachments"
KEEP_ON_CLEAN = frozenset({"manifest.json"})


def lead_key(lead: str) -> str:
    return re.sub(r"[^a-z0-9]", "", lead.lower())


def load_manifest(manifest_path: Path) -> dict:
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing {manifest_path}")
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def clean_lead_dir(out_dir: Path) -> None:
    if not out_dir.is_dir():
        out_dir.mkdir(parents=True, exist_ok=True)
        return
    for child in out_dir.iterdir():
        if child.name in KEEP_ON_CLEAN:
            continue
        if child.is_file():
            child.unlink()
        elif child.is_dir():
            shutil.rmtree(child)


def copy_attachment(dossier: Path, rel: str, attach_dir: Path) -> str:
    src = dossier / rel
    if not src.is_file():
        raise FileNotFoundError(rel)
    dst_name = Path(rel).name
    attach_dir.mkdir(parents=True, exist_ok=True)
    dst = attach_dir / dst_name
    shutil.copy2(src, dst)
    return dst_name


def pack(dossier: Path, lead: str, *, clean: bool = True) -> Path:
    dossier = dossier.resolve()
    key = lead_key(lead)
    out_dir = dossier / "leads" / key
    attach_dir = out_dir / ATTACHMENTS_DIR
    manifest_path = out_dir / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"No manifest at {manifest_path}. "
            f"Copy scripts/submit-manifest.example.json → leads/{key}/manifest.json"
        )

    manifest = load_manifest(manifest_path)
    platform = manifest.get("platform")
    lead_id = manifest.get("lead", lead)

    if clean:
        clean_lead_dir(out_dir)

    uploaded: list[str] = []
    paste_dst: Path | None = None

    paste_rel = manifest.get("paste")
    if paste_rel:
        paste_src = dossier / paste_rel
        if not paste_src.is_file():
            raise FileNotFoundError(paste_rel)
        paste_dst = out_dir / paste_src.name
        shutil.copy2(paste_src, paste_dst)
        print(f"paste -> {paste_dst.name}")

    for section in ("screenshots", "json"):
        for rel in manifest.get(section, []):
            name = copy_attachment(dossier, rel, attach_dir)
            uploaded.append(name)
            print(f"{section}: attachments/{name}")

    repo_root = dossier.parent.parent
    paste_validate = (
        paste_dst.relative_to(repo_root).as_posix()
        if paste_dst is not None
        else f"leads/{key}/*-paste.md"
    )

    platform_note = f" ({platform})" if platform else ""
    instr = out_dir / "КАК_ОТПРАВИТЬ.txt"
    instr.write_text(
        "\n".join(
            [
                f"Лид {lead_id}{platform_note} · досье {dossier.name}",
                "",
                "1. Текст отчёта: открыть *-paste.md в этой папке",
                "   • поля формы → заполнить на сайте",
                "   • «Описание (скопировать…)» → вставить в описание",
                "",
                f"2. Вложения: открыть папку attachments/",
                f"   {attach_dir}",
                "   Выделить все файлы (Ctrl+A) → загрузить в форму заявки.",
                "   В attachments/ только то, что нужно прикрепить.",
                "",
                "3. Проверка paste (из корня репозитория):",
                f"   uv run python scripts/validate_submit_paste.py {paste_validate} --lead {lead_id}",
                "",
                "4. Пересборка после правок:",
                f"   uv run python scripts/pack_submit.py {dossier.relative_to(repo_root)} {lead_id}",
                "",
            ]
        ),
        encoding="utf-8",
    )

    print(f"Packed {len(uploaded)} file(s) -> {attach_dir}")
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dossier", type=Path, help="Path to data/dossiers/<Dossier>/")
    parser.add_argument("lead", help="Lead id, e.g. BL-002, LEAD-024")
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Do not remove old packed files before copy (manifest always kept)",
    )
    args = parser.parse_args()
    try:
        out = pack(args.dossier, args.lead, clean=not args.no_clean)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"OK: {out}")


if __name__ == "__main__":
    main()

"""Rename AcroForm widgets in the Employee Information PDF to canonical names."""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

import fitz

from ee_pdf_field_map import EE_TRUTH_PDF_REL_PATH

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ee_pdf_field_map import EE_PDF_FIELD_RENAMES, canonical_acro


def rename_pdf_fields(pdf_path: Path, *, backup: bool = True) -> tuple[int, list[str]]:
    """Rename widgets in-place. Returns (count_renamed, log lines)."""
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)

    if backup:
        bak = pdf_path.with_suffix('.pdf.bak')
        if not bak.exists():
            shutil.copy2(pdf_path, bak)

    doc = fitz.open(str(pdf_path))
    log: list[str] = []
    renamed = 0
    target_names: set[str] = set()

    for page in doc:
        for widget in page.widgets() or []:
            old = (widget.field_name or '').strip()
            if not old:
                continue
            new = canonical_acro(old)
            if new == old:
                continue
            if new in target_names:
                raise ValueError(f'Duplicate target name {new!r} (from {old!r})')
            widget.field_name = new
            widget.update()
            target_names.add(new)
            renamed += 1
            log.append(f'{old} -> {new}')

    if renamed:
        doc.save(str(pdf_path), incremental=True, encryption=fitz.PDF_ENCRYPT_KEEP)
    doc.close()
    return renamed, log


if __name__ == '__main__':
    default = ROOT / EE_TRUTH_PDF_REL_PATH
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    count, lines = rename_pdf_fields(path)
    print(f'Renamed {count} field(s) in {path}')
    for line in lines:
        print(' ', line)

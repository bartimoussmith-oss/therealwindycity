"""Apply the owner's six-fix remediation without replacing the multipage UI."""
from __future__ import annotations
import ast
import py_compile
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def write(path, content):
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def apply():
    twins = [ROOT / "streamlit_app.py", ROOT / "Transparency_Index_App.py"]
    if twins[0].read_bytes() != twins[1].read_bytes():
        raise RuntimeError("Entrypoints diverged; refusing to overwrite either one.")
    original = twins[0].read_text(encoding="utf-8")
    marker = "# remediation: unified database bootstrap"
    if marker not in original:
        anchor = "import rwc_views as V"
        if original.count(anchor) != 1:
            raise RuntimeError("Unexpected entrypoint layout; no app replacement attempted.")
        block = marker + "\nfrom remediation_runtime import initialize_databases\ninitialize_databases()\nst.page_link('pages/24_Unified_Records.py', label='Unified Public Records: Vault + Entity Dossiers')\n\n"
        original = original.replace(anchor, block + anchor, 1)
        for path in twins:
            path.write_text(original, encoding="utf-8")
    vault = ROOT / "cheyenne_watchdog_vault.py"
    source = vault.read_text(encoding="utf-8")
    tree = ast.parse(source)
    replacements = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "vouchers" for t in node.targets):
            values = ast.literal_eval(node.value)
            seen = {}
            unique = []
            for value in values:
                if value[0] in seen:
                    if seen[value[0]] != value:
                        raise RuntimeError("Conflicting voucher IDs; human review required.")
                    continue
                seen[value[0]] = value
                unique.append(value)
            if len(unique) != len(values):
                indent = " " * node.col_offset
                replacement = indent + "vouchers = [\n" + "".join(indent + "    " + repr(value) + ",\n" for value in unique) + indent + "]\n"
                replacements.append((node.lineno - 1, node.end_lineno, replacement))
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "DB_NAME" for t in node.targets):
            replacements.append((node.lineno - 1, node.end_lineno, 'DB_NAME = str(__import__("pathlib").Path(__file__).resolve().parent / "cheyenne_watchdog.db")\n'))
    lines = source.splitlines(keepends=True)
    for start, end, replacement in sorted(replacements, reverse=True):
        lines[start:end] = [replacement]
    write("cheyenne_watchdog_vault.py", "".join(lines))
    views = ROOT / "rwc_views.py"
    source = views.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    replacements = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or not node.args.args:
            continue
        segment = ast.get_source_segment(source, node) or ""
        legacy = any(folder in segment for folder in ("Video_Transcripts", "Cheyenne_Extracted_Documents", "city of cheyenne gov files"))
        if node.name in ("read_raw_document", "_read_raw_document") or (legacy and ("read" in node.name or "raw" in node.name)):
            first = node.args.args[0].arg
            metadata = next((a.arg for a in node.args.args[1:] if a.arg in ("doc_meta", "metadata")), "None")
            indent = " " * node.col_offset
            replacement = indent + "def " + node.name + "(" + ast.unparse(node.args) + "):\n" + indent + "    from remediation_runtime import read_raw_document\n" + indent + "    return read_raw_document(" + first + ", " + metadata + ")\n"
            replacements.append((node.lineno - 1, node.end_lineno, replacement))
    for start, end, replacement in sorted(replacements, reverse=True):
        lines[start:end] = [replacement]
    if replacements:
        write("rwc_views.py", "".join(lines))
    write("pages/24_Unified_Records.py", 'import streamlit as st\nst.set_page_config(page_title="Unified Public Records", page_icon="📂", layout="wide")\nfrom remediation_runtime import render_records_page\nrender_records_page()\n')
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in (".sudo_as_admin_successful", "__pycache__/", "data/selftest/"):
        if pattern not in ignore.splitlines():
            ignore += "\n" + pattern + "\n"
    write(".gitignore", ignore)
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    for requirement in ("streamlit>=1.35", "pandas>=2.0", "beautifulsoup4>=4.12", "pypdf>=4.0", "pdfplumber>=0.11", "pytesseract>=0.3", "Pillow>=10"):
        package = requirement.split(">=")[0].lower()
        if not any(line.strip().lower().startswith(package + ">=") for line in requirements.splitlines()):
            requirements += "\n" + requirement + "\n"
    write("requirements.txt", requirements)
    (ROOT / ".sudo_as_admin_successful").unlink(missing_ok=True)
    for filename in ("streamlit_app.py", "Transparency_Index_App.py", "rwc_views.py", "cheyenne_watchdog_vault.py", "remediation_runtime.py", "pages/24_Unified_Records.py"):
        py_compile.compile(str(ROOT / filename), doraise=True)
    assert twins[0].read_bytes() == twins[1].read_bytes()
    subprocess.run(["git", "diff", "--check"], cwd=ROOT, check=True)
    print("Remediation patch generated; Python compilation and twin equality passed.")


if __name__ == "__main__":
    apply()

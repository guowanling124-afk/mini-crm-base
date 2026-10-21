#!/usr/bin/env python3
"""
Task A local reproduction harness -- script injection via issue title.

WHAT THIS DOES
    It takes the *actual* `run:` block out of
    .github/workflows/lab-a-script-injection.yml, substitutes the
    `${{ github.event.issue.title }}` expression with an attacker-controlled
    title the same way the Actions workflow engine does (plain textual
    replacement, before the shell ever sees the script), and then executes the
    resulting script with `bash -e` -- which is the default shell GitHub uses
    for `run:` steps on Linux runners (`bash -e {0}`).

WHAT THIS PROVES
    That the rendered script is valid shell in which the title becomes shell
    syntax: command substitution runs, and (in unquoted contexts) line breaks
    start new commands.

WHAT THIS DOES NOT PROVE
    That GitHub performs the interpolation. That is documented platform
    behaviour (see verification/README.md) and still needs ONE real Actions run
    on your own repository for the report's "GitHub returned Z" line.

SAFETY
    Payloads only run `date` and write a marker file inside a throwaway temp
    directory. No network, no secrets, no writes outside the temp dir.
    HOME is fenced to the temp dir so nothing under your real dotfiles is read.

USAGE
    python3 verification/repro-a-injection.py [--keep]
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE = REPO_ROOT / ".github" / "workflows" / "lab-a-script-injection.yml"
EXPRESSION = "${{ github.event.issue.title }}"

# The safe counterpart, mirroring bot.yml: pass the untrusted value through the
# environment and reference it as a quoted variable, never as script text.
SAFE_TEMPLATE = 'echo "Processing issue: $TITLE"'

# The same fixture with the quoting removed, used only to show a distinct
# failure mode (line-break injection) that quoting-of-$() would not explain.
UNQUOTED_TEMPLATE = f"echo Processing issue: {EXPRESSION}"

ISO_TS = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


def extract_run_block(path: Path) -> str:
    """Pull the literal `run: |` block out of the workflow file, dedented."""
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.strip() != "run: |":
            continue
        key_indent = len(line) - len(line.lstrip())
        block: list[str] = []
        for nxt in lines[i + 1:]:
            if not nxt.strip():
                block.append("")
                continue
            if len(nxt) - len(nxt.lstrip()) <= key_indent:
                break
            block.append(nxt)
        non_empty = [l for l in block if l.strip()]
        if not non_empty:
            break
        base = min(len(l) - len(l.lstrip()) for l in non_empty)
        return "\n".join(l[base:] for l in block).strip("\n")
    raise SystemExit(f"could not find a `run: |` block in {path}")


def render(template: str, title: str) -> str:
    """Model the workflow engine: substitute the expression into the script."""
    return template.replace(EXPRESSION, title)


def run_case(case: dict, template: str, keep: bool) -> dict:
    workdir = Path(tempfile.mkdtemp(prefix="lab-a-"))
    script = workdir / "script.sh"
    rendered = render(template, case["payload"])
    script.write_text(rendered + "\n", encoding="utf-8")

    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(workdir),          # fenced: no real dotfiles
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
    }
    if case.get("via_env"):
        env["TITLE"] = case["payload"]

    proc = subprocess.run(
        ["bash", "-e", "script.sh"],
        cwd=workdir,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )

    artifacts = {}
    for item in sorted(workdir.iterdir()):
        if item.name != "script.sh":
            artifacts[item.name] = item.read_text(encoding="utf-8", errors="replace")

    ok, executed, detail = case["validate"](proc.stdout, artifacts)
    result = {
        "case": case,
        "rendered": rendered,
        "exit": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "artifacts": artifacts,
        "executed": executed,
        "detail": detail,
        "ok": ok,
    }

    if keep:
        result["dir"] = str(workdir)
    else:
        shutil.rmtree(workdir, ignore_errors=True)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", action="store_true", help="keep temp dirs")
    args = parser.parse_args()

    fixture = extract_run_block(FIXTURE)
    if EXPRESSION not in fixture:
        raise SystemExit(
            f"fixture changed: {EXPRESSION!r} no longer appears in {FIXTURE}"
        )

    cases = [
        {
            "id": "A0",
            "label": "control / benign title",
            "payload": "Login button broken",
            "template": fixture,
            "via_env": False,
            "validate": lambda out, art: (
                "Login button broken" in out and not art,
                False,
                "title printed literally, no file created",
            ),
        },
        {
            "id": "A1",
            "label": "README payload -> $(echo injected > proof.txt)",
            "payload": "$(echo injected > proof.txt)",
            "template": fixture,
            "via_env": False,
            "validate": lambda out, art: (
                art.get("proof.txt") == "injected\n",
                True,
                "proof.txt created with content 'injected'; the title itself "
                "vanished from the log line",
            ),
        },
        {
            "id": "A2",
            "label": "observable payload -> $(date -u +%FT%TZ)",
            "payload": "$(date -u +%FT%TZ)",
            "template": fixture,
            "via_env": False,
            "validate": lambda out, art: (
                bool(ISO_TS.search(out)),
                True,
                "command output substituted into the log line",
            ),
        },
        {
            "id": "A3",
            "label": "line-break injection (unquoted variant)",
            "payload": "harmless\ndate -u +%FT%TZ",
            "template": UNQUOTED_TEMPLATE,
            "via_env": False,
            "validate": lambda out, art: (
                out.count("\n") >= 2 and bool(ISO_TS.search(out)),
                True,
                "the second line ran as its own command",
            ),
        },
        {
            "id": "A4",
            "label": "safe counterpart -> env + \"$TITLE\" (bot.yml pattern)",
            "payload": "$(date -u +%FT%TZ)",
            "template": SAFE_TEMPLATE,
            "via_env": True,
            "validate": lambda out, art: (
                "$(date -u +%FT%TZ)" in out and not ISO_TS.search(out),
                False,
                "payload printed literally, never executed",
            ),
        },
    ]

    print("=" * 72)
    print("Task A -- script injection, local reproduction")
    print("=" * 72)
    print(f"fixture   : {FIXTURE.relative_to(REPO_ROOT)}")
    print(f"expression: {EXPRESSION}")
    print("shell     : bash -e script.sh   (GitHub default: bash -e {0})")
    bash_version = subprocess.run(
        ["bash", "--version"], capture_output=True, text=True
    ).stdout.splitlines()[0]
    print(f"bash      : {bash_version}")
    print(f"when      : {datetime.now().astimezone().isoformat()}")
    print("secrets   : none in env; HOME is a temp dir")
    print()

    print("--- extracted `run:` block (verbatim from the fixture) ---")
    print(fixture)
    print()

    failures = 0
    results = []
    for case in cases:
        r = run_case(case, case["template"], args.keep)
        results.append(r)

        print("-" * 72)
        print(f"[{case['id']}] {case['label']}")
        print(f"  title    : {case['payload']!r}")
        print(f"  rendered : {r['rendered']!r}")
        print(f"  exit     : {r['exit']}   (stderr: {r['stderr'].strip() or '<empty>'})")
        print(f"  stdout   : {r['stdout']!r}")
        for name, content in r["artifacts"].items():
            print(f"  artifact : {name} = {content!r}")
        verdict = "EXECUTED" if r["executed"] else "not executed"
        expectation = (
            "expected" if r["ok"]
            else f"UNEXPECTED (wanted executed={case['expect']})"
        )
        print(f"  verdict  : {verdict} -- {expectation}")
        print(f"  detail   : {r['detail']}")
        print()
        if not r["ok"]:
            failures += 1

    print("=" * 72)
    print("summary")
    print("=" * 72)
    print(f"{'case':<5}{'executed':<11}{'matches model':<15}label")
    for r in results:
        c = r["case"]
        print(
            f"{c['id']:<5}{('yes' if r['executed'] else 'no'):<11}"
            f"{('yes' if r['ok'] else 'NO'):<15}{c['label']}"
        )

    print()
    print("notes for the report")
    print("-" * 72)
    print("* A1: the canonical README payload leaves NO visible trace in the log")
    print("  itself -- the line just reads 'Processing issue: '. The only")
    print("  evidence is the artefact on the (ephemeral) runner. Use A1 as the")
    print("  reproduction recipe, but capture A2-style output for the write-up.")
    print("* A2: execution happens because the expression is expanded into the")
    print("  script text BEFORE bash parses it. The fixture already wraps the")
    print("  line in double quotes, and that does not help -- quoting is applied")
    print("  after expansion, not before.")
    print("* A3: in an unquoted context a newline in the title starts a new")
    print("  command even without $(). This is why 'just remove $()' is not a")
    print("  fix either.")
    print("* A4: the actual fix is to stop the value being script at all -- pass")
    print("  it through env and reference \"$TITLE\" (bot.yml does exactly this).")
    print("* Scope: this job declares `permissions: contents: read` and holds no")
    print("  secrets, so the impact is runner-local code execution, not")
    print("  credential theft. Do not overstate it in the report.")
    print("* Still required for the report: one real `issues: opened` run on your")
    print("  own base repo, to evidence the platform side of the chain.")
    print()

    if failures:
        print(f"FAILED: {failures} case(s) did not behave as modelled")
        return 1
    print("all cases behaved as modelled")
    return 0


if __name__ == "__main__":
    sys.exit(main())

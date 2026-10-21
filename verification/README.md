# Task A — local reproduction

Local, offline reproduction of the script-injection mechanism in
[`../.github/workflows/lab-a-script-injection.yml`](../.github/workflows/lab-a-script-injection.yml).

## Run it

```bash
python3 verification/repro-a-injection.py                 # transcript to stdout
python3 verification/repro-a-injection.py | tee evidence.txt
```

Exit code is `0` only when every case behaves as modelled. The script fails
loudly if the fixture's `run:` block no longer contains
`${{ github.event.issue.title }}`, so it cannot silently go stale.

Latest transcript: [`evidence-a-local.txt`](evidence-a-local.txt).

## What it actually does

1. Reads the **real** `run:` block out of the fixture (not a hand-copied
   template).
2. Renders it by replacing `${{ github.event.issue.title }}` with an
   attacker-controlled title — a plain textual substitution, which is what the
   workflow engine does before the step runs.
3. Executes the rendered text as `bash -e script.sh`, matching GitHub's default
   Linux shell (`bash -e {0}`).

Payloads only run `date` and write a marker file inside a `mktemp -d`
directory. `HOME` is fenced to that directory, no secrets are placed in the
environment, and nothing is written outside it.

## The cases

| Case | Title | Rendered script | Outcome |
| --- | --- | --- | --- |
| A0 | `Login button broken` | `echo "Processing issue: Login button broken"` | control — printed literally |
| A1 | `$(echo injected > proof.txt)` | `echo "Processing issue: $(echo injected > proof.txt)"` | `proof.txt` created; log line goes blank |
| A2 | `$(date -u +%FT%TZ)` | `echo "Processing issue: $(date -u +%FT%TZ)"` | timestamp substituted into the log |
| A3 | `harmless\ndate -u +%FT%TZ` (unquoted variant) | two lines | second line runs as its own command |
| A4 | `$(date -u +%FT%TZ)` via `env`, `"$TITLE"` | literal `$(date ...)` | fix — printed, never executed |

Two points worth carrying into the write-up:

- **A1 is a trap for evidence collection.** The canonical README payload leaves
  the log line reading `Processing issue: ` — the only artefact is a file on
  the ephemeral runner, which is gone by the time you look. Capture A2-style
  output instead.
- **Quoting is not the fix.** The fixture already wraps the line in double
  quotes, and A2 still executes: expansion happens before quoting matters. A4
  is the actual fix — the value never becomes script text.

## What this proves, and what it does not

**Proves:** the rendered script is valid shell in which an untrusted title
becomes shell syntax, so command substitution (and, unquoted, line breaks)
execute. This is the `run:` step's behaviour, isolated from the platform.

**Does not prove:** that GitHub performs the substitution. That is documented
platform behaviour ([Security hardening for GitHub Actions — understanding the
risk of script
injections](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions#understanding-the-risk-of-script-injections)),
and it is the half of the chain the report still needs from a real run:

**Still to do for the report:** on your own base repo, open an issue titled
`$(date -u +%FT%TZ)` and read the `LAB-A` run log. The line should read
`Processing issue: <timestamp>` — that is the "GitHub returned Z" evidence.
Use the timestamp, not `proof.txt`, so the evidence is visible in the log
itself. Keep the repo private and the payload non-destructive; this job has
`permissions: contents: read` and no secrets, so do not claim credential
theft — the finding is runner-local code execution, classified **Not
Applicable (our config error)**.

## Relationship to `bot.yml`

[`bot.yml`](../.github/workflows/bot.yml) is the same shape of automation done
safely: untrusted text arrives via `env:` and is only ever referenced as
`"$USER_TEXT"`. Case A4 reproduces that pattern. The diff between A4 and A2 is
the entire remediation.

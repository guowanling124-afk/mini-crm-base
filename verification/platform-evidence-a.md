# Task A — platform evidence (real run)

The half of the chain the local harness cannot prove: that GitHub substitutes
`${{ github.event.issue.title }}` into the script text before the shell runs it.

| | |
| --- | --- |
| Repository | `guowanling124-afk/mini-crm-base` (public; default branch `main`) |
| Workflow | [`lab-a-script-injection.yml`](../.github/workflows/lab-a-script-injection.yml) |
| Trigger | `issues: [opened]` |
| Run | [run #1 — 39539793836](https://github.com/guowanling124-afk/mini-crm-base/actions/runs/39539793836) |
| Issue | [#2 — titled `$(date -u +%FT%TZ)`](https://github.com/guowanling124-afk/mini-crm-base/issues/2) |
| Runner | `ubuntu-latest`, `GITHUB_TOKEN` permissions: `contents: read` |
| Result | `success`, 2s |

## Evidence chain

**Assumption.** `${{ ... }}` is expanded into the `run:` script *before* bash
parses it, so an issue title becomes shell syntax on the runner.

**Evidence.** I confirmed Actions was enabled, opened issue #2 with the title
`$(date -u +%FT%TZ)`, and GitHub returned:

```text
Run echo "Processing issue: $(date -u +%FT%TZ)"
Processing issue: 2026-10-21T03:39:45Z
```

**How verified.** The `Run` line is GitHub echoing the script it is about to
execute. It already contains `$(date -u +%FT%TZ)` — the payload, not
`${{ github.event.issue.title }}` — which shows the substitution happened
before execution. The following line is that command substitution's output,
piped back into the `echo`.

## Attribution — what is ours, what is the platform's

| Line | Attribution |
| --- | --- |
| `run: echo "Processing issue: ${{ github.event.issue.title }}"` | **our config** — the defect: untrusted input interpolated into script text |
| issue #2 titled `$(date -u +%FT%TZ)` | **our input** — any user who can open an issue |
| `Run echo "Processing issue: $(date -u +%FT%TZ)"` | **platform response** — documented expansion, performed as promised |
| `Processing issue: 2026-10-21T03:39:45Z` | **platform response** — bash executed the substituted text |

Nothing in this chain is a platform defect. GitHub's documentation explicitly
warns against this pattern ("Understanding the risk of script injections", in
*Security hardening for GitHub Actions*), which is why the finding is
classified **Not Applicable (our config error)** — it defines the boundary the
B/C/D findings are measured against.

## Control group

The same issue event also triggered [`bot.yml`](../.github/workflows/bot.yml),
which was **skipped**: its `if:` requires `@bot` in the issue body, and it
passes user text through `env:` rather than into the script. Same trigger,
different handling, no execution — that contrast is the point of the pair.

## Impact

Runner-local arbitrary command execution as the `runner` user, on a job that
holds `permissions: contents: read` and **no secrets**. So:

- code execution: yes;
- credential theft: **no** — nothing sensitive is in scope for this job;
- persistence: no — the runner is ephemeral;
- but arbitrary command *output* does land in the log unmasked (see the
  timestamp above), so any readable non-secret data on the runner can be
  exfiltrated through the log.

Do not upgrade this to "secret leak" in the write-up.

## Failure / attack condition

The repository accepts issues from any account (public repo), and the workflow
fires on `opened`. No write access, no fork, no PR needed — the precondition is
just "can open an issue".

## Fix

Pass the untrusted value through the environment and reference it as a quoted
variable, so it never becomes script text:

```yaml
- env:
    TITLE: ${{ github.event.issue.title }}
  run: printf 'Processing issue: %s\n' "$TITLE"
```

[`bot.yml`](../.github/workflows/bot.yml) already does this. Note that adding
quotes to the existing line is *not* a fix — the fixture is already quoted, and
expansion happens before quoting matters (local case A2).

## Residual risk after the fix

- The variable is safe only while it stays data. Any later `eval`, unquoted
  expansion, or interpolation into another shell string reopens the hole.
- `permissions: contents: read` bounds the blast radius but does not prevent
  execution; it is defence in depth, not the fix.
- The log itself remains an exfiltration channel for anything the job can read.

## Local cross-check

`verification/evidence-a-local.txt` (cases A1–A4) reproduces the same mechanism
offline and pins the two counter-intuitive details: the canonical `proof.txt`
payload leaves the log line blank, and quoting does not help.

## Operational note

Issue #1 (03:34:53Z) produced no run because Actions was still disabled on this
forked repository — fork workflows require a one-time "I understand my
workflows, go ahead and enable them" click. Events are not replayed, so a new
issue (#2) was needed. Worth stating in the report as part of the setup, since
a reader reproducing this will hit the same gate.

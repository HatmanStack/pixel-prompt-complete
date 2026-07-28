# Pull request

## What changed and why

<!-- One paragraph. The why matters more than the what -- the diff already
     shows the what. If this fixes a defect, say what the defect did. -->

## How it was verified

<!-- Paste the commands you ran and what they printed. "Tested locally" is
     not evidence; `make check` with its output is. If something could not be
     verified locally (a deploy-time behaviour, a provider API), say so here
     rather than leaving it implied. -->

```text

```

## Checklist

- [ ] `make check` passes (lint, docs lint, lockfile, tests, build)
- [ ] Tests cover the change, and fail without it
- [ ] Docs updated if behaviour, an endpoint or a default changed
- [ ] New environment variables added to `CLAUDE.md`, `backend/.env.example`
      and `backend/template.yaml` -- or none were added
- [ ] `backend/requirements-lock.txt` regenerated if
      `backend/src/requirements.txt` changed

## Anything a reviewer should push back on

<!-- Optional, and the most useful section when it is filled in. Decisions you
     were unsure about, alternatives you rejected, debt you are knowingly
     taking on. -->

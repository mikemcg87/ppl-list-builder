# Publication Checklist

Use this before making the repository public or linking it from a CV/portfolio.

## Data

- [ ] `output/` does not exist or contains no files.
- [ ] `logs/` does not exist or contains no files.
- [ ] No scraped CSVs, CRM imports, send queues, Hunter caches, or Notion exports are tracked.
- [ ] `examples/` contains only synthetic companies and fake contact data.

## Secrets And Identifiers

- [ ] `.env` is ignored and untracked.
- [ ] `.env.example` contains placeholders only.
- [ ] No API keys, bearer tokens, GHL location IDs, pipeline IDs, stage IDs, or Notion database IDs are tracked.
- [ ] Scripts read CRM/Notion configuration from environment variables rather than local absolute paths.

## Private Operating Notes

- [ ] Private campaign docs remain ignored.
- [ ] Client-specific delivery docs remain ignored.
- [ ] Internal Codex task notes remain ignored.
- [ ] Public docs describe the architecture without exposing real targets, replies, or campaign assets.

## Public Proof

- [ ] `README.md` explains the business workflow and technical architecture.
- [ ] `docs/public-case-study.md` explains the problem, approach, and public data boundary.
- [ ] `make demo-tier` runs successfully using only synthetic example data.
- [ ] `python3 -m unittest discover` passes.
- [ ] Key scripts compile with `python3 -m py_compile`.

## Final Audit Commands

```bash
git status --short --ignored
git ls-files
git ls-files --others --exclude-standard
rg -n "(/Users/|GHL_PRIVATE_TOKEN=.*[^_here]$|PIPELINE_ID = \"|TO_SEND_STAGE_ID = \"|Bearer |sk-[A-Za-z0-9]|ghp_|locationId|pipelineId)" . -g '!output/**' -g '!logs/**' -g '!*.csv' -g '!docs/publication-checklist.md'
make demo-tier
python3 -m unittest discover
```

After `make demo-tier`, delete generated local data again:

```bash
rm -rf output logs
```

# Contributing

Thanks for looking under the hood. This is a research codebase: correctness and honest reporting matter more than features.

## Run the tests first
```bash
pip install -r requirements.txt
python -m pytest -q
```
Every change must keep the full suite green, and new behaviour needs new tests.

## Standards held in this repo
- **Real data or labelled synthetic** — say which, with provenance.
- **No lookahead, costs in, out-of-sample reported** — including when the benchmark wins.
- **Numbers in the README must be reproducible** by the code and its tests. If a change alters a headline number, update the README in the same commit and say why.
- **Limitations are documented, not buried.**

## Pull requests
Small, single-purpose PRs with a description of what changed and what the tests show. Discussion first for anything that changes methodology.

# Contributing

Issues and pull requests are welcome.

1. Open an issue first for anything bigger than a bug fix, so we can agree on the approach.
2. Keep `script-desk` and `footage-desk` on the Python standard library.
3. Run `python3 -m unittest discover -s tests -v` and `ruff check .` before you push.
4. Add an entry under `Unreleased` in `CHANGELOG.md`.
5. Use [Conventional Commits](https://www.conventionalcommits.org/): `feat(footage-desk): …`, `fix(script-desk): …`.

See [AGENTS.md](AGENTS.md) for the contracts that must not break.

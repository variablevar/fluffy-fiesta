# Contributing

RockSim is a research codebase. Read `docs/limitations.md` before proposing a
result-bearing change. Negative results are first-class contributions and
must be preserved.

## Ground rules

1. **Do not soften the black-box boundary.** The harvester must never reach
   internal material state. If a PR routes around this, it will be rejected.
2. **Do not insert hidden gates to satisfy a target function.** Search must
   succeed using surface measurements only.
3. **Every experiment must be reproducible** from its saved config and seeds.
4. **Document any new material model** in `docs/physics-model.md` with its
   assumed domain of validity. Avoid overclaiming physical realism.
5. Use type hints, prefer dataclasses, avoid circular imports.
6. Add or update tests. The test suite must pass before merging.

## Local checks

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m rocksim.cli generate --seed 0
.venv/bin/python -m rocksim.cli xor-search --model linear --seed 0 --iterations 200
```

## Commit style

We use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` for new capability
- `fix:` for bug fixes
- `docs:` for documentation only
- `test:` for tests only
- `refactor:` for restructuring without behaviour change
- `chore:` for tooling / housekeeping

## Suggested commit sequence for new work

1. `docs: describe what is being added and why`
2. `feat: add module skeleton`
3. `test: cover the new boundary behaviour`
4. `feat: implement the underlying behaviour`
5. `chore: update changelog and roadmap`

## Reporting issues

Please include: seeds, model id (`linear` / `nonlinear`), CLI invocation,
output directory path. Without these, results are not reproducible and the
issue cannot be investigated scientifically.

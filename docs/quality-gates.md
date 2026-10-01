# Quality Gates

Initial gates:

- Acceptance gate: every task has measurable acceptance criteria.
- Unit gate: deterministic SDK core tests.

Planned gates:

- Static quality: `ruff`, `mypy`.
- Contract tests: public SDK behavior.
- Integration tests: provider/tool adapters with fakes.
- Failure semantics: blocked tasks, failing gates, retry budget.
- Documentation drift: specs and decisions updated with behavior changes.

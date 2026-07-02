# Strategy quality regression

`strategy_quality_v1.json` freezes the eight regression dimensions introduced by the 2026-07-01 argument-synthesis review.

`ds_quality_golden.v1.json` is the first manually calibrated source case. Unit-level deterministic guards live in `tests/test_strategy_quality_guards.py`; full model pairwise evaluation should use these files as the nightly case contract.

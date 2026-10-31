# Requirements

User stories and acceptance criteria. Written the way a business systems analyst would, so each criterion can be checked by running something.

## Users
- **Reviewer:** a hiring manager or senior analyst who wants to judge the work in ten minutes.
- **Researcher (owner):** wants to add a strategy and see how it compares, without breaking the honesty guarantees.

## Stories

| ID | Story | Acceptance criteria |
| --- | --- | --- |
| R1 | As a reviewer, I can reproduce the results from a fresh clone. | `make install && make check` passes offline. `make demo` writes `reports/demo/`. With real data present, `make run && make report` writes `reports/real/`. |
| R2 | As a reviewer, I can trust there is no look-ahead. | `tests/test_causality.py` passes, and its oracle test proves a cheating strategy is caught. |
| R3 | As a reviewer, I can see what costs and delays do. | Cost sensitivity at 0, 2, 5, 10, 25 bps and lag 1 versus 2 appear in the report. |
| R4 | As a reviewer, I can tell signal from luck. | Bootstrap 95% confidence intervals for each Sharpe and for the difference versus both benchmarks. The README states the multiple-testing caveat. |
| R5 | As a reviewer, I can see how results hold up in bad markets. | Subperiod table for the GFC, COVID, and 2022 windows, out-of-sample only. |
| R6 | As a researcher, I can add a strategy cheaply. | A new strategy needs one file implementing the Strategy protocol, a config entry, and tests. The causality test picks it up automatically. |
| R7 | As a reviewer, I never see synthetic results presented as real. | Demo outputs live in `reports/demo/` and say DEMO. The README results block comes only from `reports/real/` or says NOT RUN ON REAL DATA. |

## Out of scope
See "Non-goals" in SPEC.md.

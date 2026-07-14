# Resources: Flow Matching + BCR Trees

## Core Project Code (to reference during teaching)
| Resource | Where |
|----------|-------|
| Project handoff (architecture, results, code map) | `docs/handoffs/2026-07-07-flow-matching-training-monitoring.md` |
| Coupled flow model | `src/flow/coupling.py` |
| Discrete flow core (Transformer → CTMC) | `src/flow/discrete_core.py` |
| Guidance MLP | `src/flow/guidance_mlp.py` |
| Training loop | `src/flow/trainer.py` |
| Evaluation metrics | `src/flow/evaluate.py` |
| Edge dataset builder | `scripts/_build_pairwise_edges.py` |
| Context / domain glossary | `CONTEXT.md` |
| Project CLAUDE.md (bug history, results) | `CLAUDE.md` |

## Foundational Papers
- **Flow Matching**: Lipman et al. (2023) "Flow Matching for Generative Modeling"
- **Discrete Flow Matching**: Campbell et al. (2024) "Generative Flow Matching for Discrete Data"
- **CTMC for discrete sequences**: Campbell et al. (2022) "Continuous-Time Markov Chains for Generative Modeling"
- **SHM biology**: Victora & Nussenzweig (2022) "Annual Review of Immunology"
- **BCR lineage inference**: Hoehn et al. (2022) "Phylogenetic analysis of B cell repertoires"

## External Learning (for self-study)
- 3Blue1Brown: Markov Chains / Linear Algebra intuition
- A. Ess: "Markov Chains Clearly Explained" (YouTube)
- Richard Turner's "Probabilistic ML" course — CTMC chapter

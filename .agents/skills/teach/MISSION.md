# Mission: Master Flow Matching + BCR Trees

## Why

I'm building a **flow matching model that learns SHM mutation dynamics from BCR lineage trees**. The project is already implemented and trained — but I need to deeply understand:
1. Whether the model design is correct
2. How to evaluate a generative model (I've never done this)
3. BCR tree construction and biological knowledge
4. How tree quality affects conclusions — I don't want to be misled

**Context:** This is a research project for BCR repertoire analysis. The model learns mutation patterns from parent→child edges in B cell lineage trees, using a hybrid discrete-continuous flow matching architecture. The core claim: *tree topology features improve BCR analysis beyond sequence embeddings alone* — which was falsified under initial conditions, but the model continues to evolve.

## Success Looks Like

- I can explain the CTMC math behind the model *in my own words* to someone else
- I know what metrics to look at to judge if the model is learning real biology
- I understand when tree quality is good enough vs when it's misleading
- I can make design decisions about Mode B (antigen guidance) and Mode C (tree conditioning) without asking Claude to decide for me
- I can read evaluation output and tell whether training is working

## Constraints

- **Math level:** High school algebra + ODE intuition. Failed some uni math. Teach concepts, not formulas without intuition.
- **Learning style:** Prefers multi-choice, deeper questions. Gets bored with "easy" tests. Wants algorithmic/mathematical concepts over code reading.
- **Role:** Applied ML researcher in drug delivery prediction. Not an academic.
- **Tool:** Interacts through Claude Code CLI. Needs lessons that open in browser from a single command.

## Out of Scope (for now)

- Autoregressive protein language model architectures (we use flow matching)
- nt-level tree construction (deferred to Phase 2)
- Detailed PyTorch implementation (wants concepts, not code)
- Paper writing / publication formatting

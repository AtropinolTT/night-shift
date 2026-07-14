# Learning Record 0001: CTMC Foundations

**Date:** 2026-07-07
**Lesson:** 0001-ctmc-the-math-of-mutation.html

## What I Learned

- A CTMC is defined by its rate matrix Q where Q[i][j] is the instantaneous rate of transition from state i to state j
- The diagonal Q[i][i] = -sum of all off-diagonal entries (rows sum to zero)
- Transition probabilities over time t are P(t) = exp(Q × t) — the matrix exponential, NOT element-wise exp
- The matrix exponential solves the ODE dP/dt = P × Q and correctly saturates (probabilities stay ≤ 1)
- Training: sample random t, maximize P(parent → child at time t)
- Regression to the mean: model learns average mutation count but misses variance
- Star trees (53% of our data before Bug #2) are artifacts — all internal nodes collapsed due to empty-string dict key
- Conservative rate (BLOSUM62 > 0) is a key metric beyond validity

## Connections Made

- CTMC bridges the biology (SHM mutations) and the math (rate matrices) of our flow matching model
- The tree-as-map intuition is correct: each edge is a training example for the CTMC
- Bug #2 shows why tree quality checks matter — I was right to be skeptical

## Still Unclear

- How matrix exponential is computed in practice (we use `torch.linalg.matrix_exp` but I don't know the algorithm)
- Why the guidance loss was ~0 (zero vectors) and what that means
- How to tell if the conservative rate is "good enough"

## Next Steps

- Lesson 2: Tree topology — what makes a good BCR tree, how to measure tree quality
- Lesson 3: Flow matching vs diffusion — the core algorithmic difference
- Lesson 4: Evaluating generative models — what metrics actually matter

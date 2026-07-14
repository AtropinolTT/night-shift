# Learning Record 0005: Flow Matching Theory

**Date:** 2026-07-07
**Lesson:** 5 — Theory Behind Flow Matching

## What I Learned

### Probability Paths
- A probability path describes how a parent sequence transforms into a child over time (t=0 → t=1)
- Multiple possible paths exist — flow matching learns the *average velocity* across all of them

### Conditional Flow Matching
- Global velocity field is intractable to compute directly
- Trick: define a local velocity for each single parent→child pair, supervise on that
- Summing over all edges approximates the global field
- Our `coupled_loss` = NLL(discrete) + λ·MSE(guidance) is a *valid upper bound* on the true loss

### Regression to the Mean — Root Cause
- It's baked into flow matching theory, not a code bug
- ODE is deterministic — averages over multiple possible children from similar parents
- Fix: better data (longer sequences, paired chains), better conditioning, stochastic decoding at generation

### Discrete vs Continuous Flow Matching
- Lipman (continuous): real-valued states, vector field dx/dt, MSE loss
- Campbell (discrete): discrete tokens, rate matrix dP/dt = P×Q, NLL loss
- Mathematically equivalent frameworks — rate matrix Q = discrete analogue of velocity v
- Our model uses the correct loss by theory

## Still Unclear
- How stochastic decoding would work in practice without breaking the ODE framework
- Whether better conditioning alone is enough to fix regression to mean

## Connections Made
- CTMC (Lesson 1) → why rate matrices are the right tool for discrete flow matching
- Coupling formula (Lesson 3) → guidance MLP adds a secondary velocity in embedding space
- Tree quality (Lesson 2) → better trees → better conditioning → less averaging

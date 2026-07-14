# Learning Record 0003: Coupling, Evaluation, Flow Matching vs Diffusion

**Date:** 2026-07-07
**Lesson:** 3 — Coupling Formula, Model Evaluation, FM vs Diffusion

## What I Learned

### Coupling Formula
- score = R[i→j] × exp(β · cos_sim(v, Δembedding))
- CTMC rates are data-driven empirical frequencies, not theoretical biochemistry
- Guidance MLP currently dead (zero embeddings) — Mode B implementation needed
- β = 0 → pure CTMC, β > 0 → guidance pulls

### Model Evaluation
- Current metrics: val_loss, valid_fraction, conservative_rate — all compare averages
- Missing: mutation spectrum (20×20), KL divergence, position entropy
- Bigger gap: distribution shape, not just mean. Variance, tails, modes.
- Track A (free metrics) vs Track B (distribution matching) both needed

### Flow Matching vs Diffusion
- FM uses ODE (deterministic velocity), Diffusion uses SDE (noise→denoise)
- FM: predict velocity. Diffusion: predict noise/score.
- FM can be faster with straight paths. In practice, similar step counts.
- FM fits our architecture (CTMC + guidance). Diffusion's stochasticity might help diversity.

## Still Unclear
- How to implement CDR/FW mutation ratio (need CDR position mapping)
- Whether to use energy distance or Wasserstein for distribution comparison

## Next Steps
- Fill in free evaluation metrics (spectrum, KL, entropy) in evaluate.py
- Design distribution-shape evaluation
- Mode B implementation (need real embeddings in edge data)

# Learning Record 0002: BCR Tree Quality

**Date:** 2026-07-07
**Lesson:** 2 — Tree Quality

## What I Learned

- 54% of our clones are star trees (NJ artifact with short CDR3s)
- Star trees produce zero edges — edge dataset is automatically star-free
- However, 68% of edges come from clones with only 1-4 internal nodes (marginal topology)
- Only 32% of edges from clones with ≥5 internal nodes
- Sackin index = ancestor count per leaf (normalized). Low = shallow. Our non-stars: 0.018
- Colless imbalance = left-right asymmetry. 0=balanced, 1=ladder. Non-star mean: 0.34
- Stemminess = internal / total branch length. High = deep (early) mutations. Non-star median: 0.33
- BCR trees are rooted using germline reference — wrong root = wrong mutation direction
- NJ doesn't provide bootstrap support — we don't know which branches are trustworthy
- Ultimate bottleneck: CDR3s are 15-40 AA — too short for any tree method to be reliable

## Connections Made

- The 53% star tree problem isn't the main data issue — it's the 68% marginal-topology edges
- Q3/Q4 NULL results make sense now: weak trees → weak topology features → no signal
- The open question is how to handle low-quality edges: filter, weight, or curriculum

## Still Unclear

- How to implement edge weighting by topology quality
- What threshold separates "reliable" from "marginal" tree quality
- Whether nt-level trees with ML would actually change the conclusions

## Next Steps

- Lesson 3: coupling formula, model evaluation, or flow matching vs diffusion

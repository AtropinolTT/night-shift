# Learning Record 0004: The Data Pipeline

**Date:** 2026-07-07
**Lesson:** 4 — Blood to Training Edges

## What I Learned

### Wet lab (Steps 1-2)
- Blood → PBMC isolation (Ficoll gradient) → FACS sorting (CD19+ B cells) → single-cell RNA extraction → RT-PCR → Illumina sequencing
- Each sequence = one real B cell from the donor

### V(D)J assignment (Step 3)
- IgBLAST matches reads against IMGT germline database
- Outputs: V gene, D gene, J gene, CDR3 boundaries, mutation count vs germline
- The germline sequence later becomes the tree root

### Clonal grouping (Step 4)
- Clone definition: same V + same J + same CDR3 length + ≥90% CDR3 similarity
- V gene is irreversible — different V = different clone guaranteed
- This strictness is why nt-level data only yields 16 clones

### Ancestral reconstruction (Step 6)
- Dowser infers internal node sequences from tree + leaf sequences
- **Every parent sequence in our 2,765 edges is an inference, not ground truth**
- Edge quality = tree quality

### Key Discovery
- Source data (OAS Paired) contains full heavy + light chain sequences
- Current pipeline only uses heavy chain CDR3 (15-40 AA)
- Opportunity: full V(D)J AA (~130 AA) or paired H+L (~250 AA) would greatly improve phylogenetic signal

## Connections Made
- Pipeline quality cascades: wet lab → clonal grouping → tree quality → edge quality → model quality
- The 68% marginal-topology edges problem originates from short CDR3s, not just NJ
- Paired data is a concrete, unblocked path to better trees without touching nt-level problems

## Next Steps
- Lesson 5 (user's choice)

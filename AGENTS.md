# Project: skills-repo (night-shift)

A skills repository for QoderCLI containing 74+ agent skills from three
sources: google-deepmind/science-skills, mattpocock/skills, and
Yuan1z0825/nature-skills. The root-level skill is `night-shift`, a
pricing-aware job scheduler for DeepSeek V4.

## Project Structure

- `.agents/skills/` -- canonical skill source files (SKILL.md + resources per skill)
- `.qoder/skills/` -- symlinks into `.agents/skills/` for QoderCLI discovery
- `skills-lock.json` -- installed skill manifest with source and hash tracking
- `scripts/` -- night-shift runtime scripts (check-window.sh, estimate-cost.sh, parse-queue.sh)
- `feishu-kb/`, `ara-manager/`, `ai-galaxy/` -- project-local skills with their own SKILL.md
- `night-shift/` -- night-shift skill references directory
- `tests/` -- integration tests
- `docs/` -- design specs and plans

## Conventions

- This is a skills repository. Most work involves skill creation, maintenance, or migration.
- The root `SKILL.md` is the night-shift skill definition.
- Skills are version-locked in `skills-lock.json` with computed hashes.
- Always run night-shift scripts rather than reasoning about pricing manually.

## Key Config

- `config.example.json` -- template for runtime config (`config.json` is gitignored)
- `pricing.json` -- DeepSeek V4 pricing data consumed by night-shift scripts

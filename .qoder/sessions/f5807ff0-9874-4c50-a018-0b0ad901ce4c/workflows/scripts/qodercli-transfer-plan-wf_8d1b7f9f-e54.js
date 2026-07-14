export const meta = {
  name: 'qodercli-transfer-plan',
  description: 'Create .qoder directory skeleton and symlinks for QoderCLI transfer plan',
  phases: [
    { title: 'Create directories', detail: 'mkdir -p .qoder/rules .qoder/skills' },
    { title: 'Create symlinks', detail: 'Symlink all skills from .agents/skills into .qoder/skills' },
    { title: 'Verify', detail: 'Check symlink count and spot-check resolution' },
  ],
}

const repo = '/sibcb1/chuyanyilab1/tangjunjie/skills-repo'

// Phase 1: Create directories
phase('Create directories')
await agent(`Run: mkdir -p ${repo}/.qoder/rules && mkdir -p ${repo}/.qoder/skills
Then confirm both directories exist with: ls -la ${repo}/.qoder/`, { label: 'mkdir' })

// Phase 2: Create symlinks for every name in .claude/skills/
phase('Create symlinks')
const claudeSkills = await agent(`List the contents of ${repo}/.claude/skills/ with ls. Output just the names, one per line.`, { label: 'list-claude-skills' })
const skillNames = claudeSkills.trim().split('\n').filter(Boolean)
log(`Found ${skillNames.length} skills in .claude/skills/`)

for (const name of skillNames) {
  await agent(`Run: ln -s "../../.agents/skills/${name}" "${repo}/.qoder/skills/${name}"
Then verify the symlink was created with: ls -la "${repo}/.qoder/skills/${name}"`, { label: `symlink-${name}`, phase: 'Create symlinks' })
}

// Phase 3: Verify
phase('Verify')
const verifyResult = await agent(`Run these verification commands and report the results:
1. echo "Count in .claude/skills:" && ls ${repo}/.claude/skills/ | wc -l
2. echo "Count in .qoder/skills:" && ls ${repo}/.qoder/skills/ | wc -l
3. echo "Spot-check chembl-database:" && ls -la ${repo}/.qoder/skills/chembl-database/SKILL.md
4. echo "Check if symlinks resolve:" && for f in ${repo}/.qoder/skills/*/SKILL.md; do [ -f "$f" ] && echo "OK: $f" || echo "MISSING: $f"; done | head -5`, { label: 'verify' })

log(verifyResult)
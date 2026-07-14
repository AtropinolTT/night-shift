export const meta = {
  name: 'create-rules-files',
  description: 'Create .qoder/rules/ directory and copy rule files from .claude/rules/',
  phases: [
    { title: 'Create', detail: 'Create .qoder/rules/ files' }
  ]
};

const repoRoot = '/sibcb1/chuyanyilab1/tangjunjie/skills-repo';
const rulesDir = `${repoRoot}/.qoder/rules`;

// Create the directory via subagent
await agent(`Create directory ${rulesDir} and copy these files from .claude/rules/ to it:
- global-rules.md
- frontend-rules.md
- python-rules.md
- malformed.md

Use Bash to mkdir -p ${rulesDir} and then cp each file from ${repoRoot}/.claude/rules/ to ${rulesDir}/.`, {
  label: 'create-rules-dir-and-copy-files',
  phase: 'Create'
});

log('Rule files created successfully');

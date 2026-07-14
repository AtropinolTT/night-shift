// ara-organize.js — Backend engine for /ara-manager organize
// Multi-agent ARA maintenance loop with Opus review and Sonnet response.

export const meta = {
  name: 'ara-organize',
  description: 'Backend engine for /ara-manager organize — multi-agent ARA maintenance loop',
  phases: [
    { title: 'Scout' },
    { title: 'Extract' },
    { title: 'Review' },
    { title: 'Respond' },
    { title: 'Execute' },
    { title: 'Verify' },
  ],
}

// ─── Dispatch ────────────────────────────────────────────────────────────────────

const focus = (args?.focus || 'all').trim().toLowerCase()
const isDaily = args?.mode === 'daily'
const ARA_DIR = './ara'

const DISPATCH = {
  scout:         ['Scout'],
  extract:       ['Extract'],
  crystallize:   ['Scout', 'Review', 'Respond'],
  audit:         ['Scout', 'Review', 'Respond'],
  clean:         ['Scout', 'Execute', 'Verify'],
  all:           ['Scout', 'Extract', 'Review', 'Respond', 'Execute', 'Verify'],
  daily:         ['Scout', 'Execute', 'Verify'],
  test:          ['Scout', 'Extract', 'Review', 'Respond', 'Execute', 'Verify'],
  validate:      ['Verify'],
}
const phases = DISPATCH[focus] || DISPATCH.all

// Auto-inject test fixture for test mode
let originalPaths
if (focus === 'test') {
  originalPaths = args?.paths
  args = { ...args, paths: ['ara/tests/test-extract-fixture.md'] }
}

// ─── Helper: read file as string ─────────────────────────────────────────────────

async function readFile(path) {
  try {
    // Use Bash to read file content
    return await agent(`Read the file at ${path} and return its full contents as a string.`, {
      label: `read:${path.split('/').pop()}`,
      agentType: 'claude',
      schema: { type: 'object', properties: { content: { type: 'string' } }, required: ['content'] },
    }).then(r => r?.content || '')
  } catch {
    return ''
  }
}

// ─── Helper: write YAML ──────────────────────────────────────────────────────────

async function appendObservations(newEntries) {
  if (!newEntries || newEntries.length === 0) return
  const obsPath = `${ARA_DIR}/staging/observations.yaml`
  const yamlStr = newEntries.map(e => `  - id: ${e.id}
    timestamp: "${e.timestamp}"
    provenance: ${e.provenance}
    content: "${e.content.replace(/"/g, '\\"')}"
    context: "${(e.context || '').replace(/"/g, '\\"')}"
    potential_type: ${e.potential_type}
    bound_to: ${JSON.stringify(e.bound_to || [])}
    promoted: ${e.promoted || false}
    promoted_to: ${e.promoted_to || null}
    crystallized_via: ${e.crystallized_via || null}
    stale: ${e.stale || false}`).join('\n')
  await agent(`Append the following YAML entries to ${obsPath} (use Bash to write):

${yamlStr}`, { label: 'staging-writer', phase: 'Execute' })
}

// ─── Helper: write daily report ──────────────────────────────────────────────────

async function writeDailyReport(reportContent) {
  const dateStr = new Date().toISOString().slice(0, 10)
  const dir = `${ARA_DIR}/daily`
  const filePath = `${dir}/${dateStr}.md`
  await agent(`Create directory ${dir} if it doesn't exist, then write the following content to ${filePath}:

${reportContent}`, { label: 'daily-report-writer', phase: 'Verify' })
}

// ═══════════════════════════════════════════════════════════════════════════════════
// SCOUT
// ═══════════════════════════════════════════════════════════════════════════════════

const SCOUT_SCHEMA = {
  type: 'object',
  properties: {
    claims: {
      type: 'object',
      properties: {
        total: { type: 'integer' },
        byStatus: {
          type: 'object',
          properties: {
            supported: { type: 'integer' }, testing: { type: 'integer' },
            hypothesis: { type: 'integer' }, weakened: { type: 'integer' },
            refuted: { type: 'integer' }, withdrawn: { type: 'integer' },
          },
          required: ['supported', 'testing', 'hypothesis', 'weakened', 'refuted', 'withdrawn'],
        },
        stale: { type: 'array', items: { type: 'string' } },
      },
      required: ['total', 'byStatus', 'stale'],
    },
    staging: {
      type: 'object',
      properties: {
        total: { type: 'integer' },
        nonPromoted: { type: 'integer' },
        staleCount: { type: 'integer' },
        byType: {
          type: 'object',
          properties: {
            claim: { type: 'integer' }, heuristic: { type: 'integer' },
            concept: { type: 'integer' }, constraint: { type: 'integer' },
          },
          required: ['claim', 'heuristic', 'concept', 'constraint'],
        },
      },
      required: ['total', 'nonPromoted', 'staleCount', 'byType'],
    },
    tree: {
      type: 'object',
      properties: {
        total: { type: 'integer' },
        byType: {
          type: 'object',
          properties: {
            decision: { type: 'integer' }, experiment: { type: 'integer' },
            dead_end: { type: 'integer' }, pivot: { type: 'integer' }, question: { type: 'integer' },
          },
          required: ['decision', 'experiment', 'dead_end', 'pivot', 'question'],
        },
        openQuestions: {
          type: 'array',
          items: {
            type: 'object',
            properties: { id: { type: 'string' }, title: { type: 'string' } },
            required: ['id', 'title'],
          },
        },
      },
      required: ['total', 'byType', 'openQuestions'],
    },
    experiments: {
      type: 'object',
      properties: { total: { type: 'integer' }, complete: { type: 'integer' }, inProgress: { type: 'integer' } },
      required: ['total', 'complete', 'inProgress'],
    },
  },
  required: ['claims', 'staging', 'tree', 'experiments'],
}

let scoutReport = null

if (phases.includes('Scout')) {
  phase('Scout')
  scoutReport = await agent(`Read the ARA project at ./ara/ and produce a structured health report.

Read these files:
1. ara/logic/claims.md — all claims with ID, Status, Statement (first 80 chars), Last revised
2. ara/staging/observations.yaml — count total, non-promoted, stale (timestamp >3 days ago), group by potential_type
3. ara/trace/exploration_tree.yaml — total nodes, count by type, open questions (type: question with no resolving children)
4. ara/logic/experiments.md — experiment count, complete vs in-progress

Return the data in the specified JSON format.`, {
    label: 'scout',
    phase: 'Scout',
    schema: SCOUT_SCHEMA,
  })
  log(`Scout complete: ${scoutReport?.claims?.total || 0} claims, ${scoutReport?.staging?.nonPromoted || 0} staging pending`)
}

// ═══════════════════════════════════════════════════════════════════════════════════
// EXTRACT
// ═══════════════════════════════════════════════════════════════════════════════════

let extractionResult = null

if (phases.includes('Extract')) {
  phase('Extract')
  const targetPaths = (args?.paths || ['docs/handoffs/', 'docs/hpo/', 'docs/xai/demo/README.md']).join(' ')

  extractionResult = await agent(`Scan the following files/directories for research findings, decisions, experiment results, and claims not yet in the ARA project.

Targets: ${targetPaths}

For each file:
1. Read it completely
2. Extract distinct factual claims, design decisions, experimental outcomes, concept definitions, constraints
3. Determine potential_type (claim|heuristic|concept|constraint|experiment|decision)
4. Check against existing staging observations — skip semantic duplicates
5. Return novel extractions

Return JSON:
{
  "extractions": [
    {
      "content": "falsifiable assertion or finding",
      "potential_type": "claim|heuristic|concept|constraint|experiment|decision",
      "source": "path/to/file.md",
      "provenance": "ai-executed",
      "reason_for_skip": null
    }
  ],
  "stats": {"total": N, "novel": N, "duplicates": N}
}`, {
    label: 'extractor',
    phase: 'Extract',
  })

  if (extractionResult && extractionResult.extractions) {
    const novel = extractionResult.extractions.filter(e => !e.reason_for_skip)
    log(`Extractor found ${novel.length} novel items from ${extractionResult.stats?.total || 0} total`)
  }
}

// ═══════════════════════════════════════════════════════════════════════════════════
// REVIEW
// ═══════════════════════════════════════════════════════════════════════════════════

let crystallizeProposals = null
let auditProposals = null
let gapAnalysis = null
let reviewResult = null

if (phases.includes('Review')) {
  phase('Review')

  // Crystallizer
  if (focus === 'crystallize' || focus === 'all') {
    crystallizeProposals = await agent(`Based on the scout report and direct reading of ara/staging/observations.yaml, propose observations ready for crystallization.

For each non-promoted observation, evaluate:
1. Is evidence sufficient? (bound_to experiments completed? user affirmed?)
2. What closure signal applies? (resolution|affirmation|commitment|abandonment)
3. Which target layer? (logic/claims.md, logic/solution/heuristics.md, etc.)

Scout context:
${JSON.stringify(scoutReport, null, 2)}

Return JSON:
{
  "ready": [
    {"id": "O{XX}", "content": "first 80 chars",
     "suggested_signal": "resolution|affirmation|commitment|abandonment",
     "target_layer": "logic/claims.md", "rationale": "why ready"}
  ],
  "needs_discussion": [
    {"id": "O{XX}", "reason": "what's blocking"}
  ]
}`, {
      label: 'crystallizer',
      phase: 'Review',
    })
    log(`Crystallizer: ${crystallizeProposals?.ready?.length || 0} ready, ${crystallizeProposals?.needs_discussion?.length || 0} blocked`)
  }

  // Claim Auditor
  if (focus === 'audit' || focus === 'all') {
    auditProposals = await agent(`Based on the scout report and direct reading of ara/logic/claims.md and ara/logic/experiments.md, propose claim status advancements.

For each claim:
1. Does its Proof field reference completed experiments?
2. Do those experiments' results support the claim?
3. Is there new evidence justifying advance or raising concerns?

Scout:
${JSON.stringify(scoutReport, null, 2)}

Return JSON:
{
  "advancements": [
    {"claim_id": "C{XX}", "current_status": "testing", "suggested_status": "supported",
     "evidence": ["E{XX} completed: ..."], "rationale": "...", "confidence": "high|medium|low"}
  ],
  "blocked": [
    {"claim_id": "C{XX}", "reason": "blocker", "suggestion": "fix"}
  ],
  "data_issues": [
    {"claim_id": "C{XX}", "issue": "empty Proof field", "fix": "Add [E22]"}
  ]
}`, {
      label: 'claim-auditor',
      phase: 'Review',
    })
    log(`Auditor: ${auditProposals?.advancements?.length || 0} advancements, ${auditProposals?.blocked?.length || 0} blocked`)
  }

  // Knowledge Gap Analyzer — find gaps in ARA structure and produce improvement proposals
  if (scoutReport) {
    gapAnalysis = await agent(`You are the ARA Knowledge Gap Analyst. Analyze the current ARA state and identify knowledge gaps, missing evidence, incomplete coverage, and improvement opportunities.

Current ARA state:
${JSON.stringify(scoutReport, null, 2)}

Read the following files to assess completeness:
- ara/logic/claims.md — check each claim for empty Proof, Falsification, or Provenance fields; check if status (supported/testing/hypothesis) matches evidence quality
- ara/logic/experiments.md — check for experiments not linked to any claim, or with incomplete results
- ara/logic/problem.md — check if problem statement has sub-problems or constraints defined
- ara/logic/concepts.md — check if key concepts are defined for all referenced terms
- ara/logic/solution/constraints.md — check if design constraints are documented
- ara/trace/exploration_tree.yaml — check if all decisions capture alternatives and evidence

For each gap found, produce an actionable improvement proposal.

Return JSON:
{
  "gaps": [
    {
      "area": "claims|experiments|problem|concepts|constraints|tree",
      "severity": "critical|major|minor",
      "finding": "description of the gap",
      "evidence": "what was found (or not found)",
      "proposal": "specific actionable improvement to make",
      "target_file": "path/to/file.md"
    }
  ],
  "summary": {
    "total_gaps": N,
    "critical": N,
    "major": N,
    "minor": N,
    "top_priority": "most important gap finding"
  }
}`, {
      label: 'gap-analyst',
      phase: 'Review',
    })
    log(`Gap Analysis: ${gapAnalysis?.summary?.total_gaps || 0} gaps found (${gapAnalysis?.summary?.critical || 0} critical, ${gapAnalysis?.summary?.major || 0} major)`)
  }

  // Reviewer — Opus quality gate
  const hasProposals = crystallizeProposals || auditProposals || extractionResult || (gapAnalysis?.gaps?.length > 0)
  if (hasProposals) {
    const reviewInput = {
      crystallization: crystallizeProposals || null,
      audit: auditProposals || null,
      extraction: extractionResult
        ? { stats: extractionResult.stats, novelCount: extractionResult.extractions?.filter(e => !e.reason_for_skip)?.length }
        : null,
      gap_analysis: gapAnalysis
        ? { total_gaps: gapAnalysis.summary?.total_gaps || 0, critical: gapAnalysis.summary?.critical || 0 }
        : null,
    }

    reviewResult = await agent(`You are the ARA Reviewer, powered by nature-reviewer. Review proposals and gap analysis for academic rigor, evidence quality, and internal consistency. Identify missing knowledge areas and recommend priorities.

${JSON.stringify(reviewInput, null, 2)}

For each proposal:
1. Verify evidence supports the conclusion
2. Check falsifiability
3. Check cross-references (experiment IDs, claim IDs)
4. Assess confidence calibration

For gap analysis:
5. Endorse or challenge each gap finding
6. Suggest priority order for addressing gaps
7. Recommend specific next steps

Return:
{
  "verdicts": [
    {"target_id": "C{XX} or O{XX}", "proposal_type": "advancement|crystallization|extraction",
     "verdict": "approved|needs_revision|rejected",
     "findings": [{"severity": "critical|major|minor", "description": "...", "affected_area": "evidence|falsifiability|referencing|calibration"}],
     "rationale": "academic justification"}
  ],
  "knowledge_gaps": [
    {"gap": "description", "priority": "high|medium|low", "endorsed": true|false, "rationale": "...", "suggested_action": "..."}
  ],
  "summary": {"approved": N, "needs_revision": N, "rejected": N, "gaps_endorsed": N}
}`, {
      label: 'reviewer',
      phase: 'Review',
      model: 'opus',
    })
    log(`Review: ${reviewResult?.summary?.approved || 0} approved, ${reviewResult?.summary?.needs_revision || 0} needs revision, ${reviewResult?.summary?.gaps_endorsed || 0} gaps endorsed`)
  }
}

// ═══════════════════════════════════════════════════════════════════════════════════
// RESPOND
// ═══════════════════════════════════════════════════════════════════════════════════

let remediationPlan = null

if (phases.includes('Respond') && reviewResult && (reviewResult.verdicts || reviewResult.knowledge_gaps)) {
  phase('Respond')

  remediationPlan = await agent(`You are the ARA Responder, powered by nature-response. Receive review verdicts and gap analysis, produce structured remediation with formal academic replies.

Review output: ${JSON.stringify(reviewResult, null, 2)}

For each finding and gap:
1. Formal academic reply addressing the concern
2. Concrete remediation action
3. Assignment to correct agent type

Return:
{
  "replies": [
    {"target_id": "C{XX} or O{XX}", "finding": "...", "reply": "academic response",
     "accepts": true|false, "remediation": "what will be done"}
  ],
  "dispatch": [
    {"target_agent": "crystallizer|claim_auditor|extractor|housekeeper|gap_analyst",
     "actions": ["action 1", "action 2"], "priority": "high|medium|low", "depends_on": []}
  ],
  "dispatch_order": ["claim_auditor", "crystallizer"]
}`, {
    label: 'responder',
    phase: 'Respond',
    model: 'sonnet',
  })
  log(`Responder: ${remediationPlan?.dispatch?.length || 0} dispatch items`)
}

// ═══════════════════════════════════════════════════════════════════════════════════
// EXECUTE
// ═══════════════════════════════════════════════════════════════════════════════════

phase('Execute')

let housekeeperReport = null

// Housekeeper — runs validate, detects stale/duplicate observations
if (focus === 'clean' || focus === 'all' || focus === 'daily') {
  housekeeperReport = await agent(`Inspect the ARA project at ./ara/ for cleanup opportunities.

Read:
1. ara/staging/observations.yaml — find observations where:
   - stale: false but timestamp is >7 days old → mark stale
   - content is semantically identical to another (duplicates)
   - promoted: true but promoted_to is null → orphaned
2. Structural check:
   - Every claim's Proof references a valid experiment ID
   - Every experiment's Verifies references a valid claim ID

Report findings as JSON:
{
  "toMarkStale": [{"id": "O{XX}", "reason": "no activity >7 days"}],
  "duplicates": [{"ids": ["O{XX}", "O{YY}"], "keep": "O{XX}"}],
  "orphanedPromotions": ["O{XX}"],
  "structuralIssues": [{"type": "broken_ref", "description": "..."}]
}`, {
    label: 'housekeeper',
    phase: 'Execute',
  })
  log(`Housekeeper: ${housekeeperReport?.toMarkStale?.length || 0} to stale, ${housekeeperReport?.duplicates?.length || 0} duplicates`)
}

// Extractor staging writer — append novel extractions to observations.yaml
if (extractionResult && extractionResult.extractions) {
  const novel = extractionResult.extractions.filter(e => !e.reason_for_skip)
  if (novel.length > 0) {
    // Read current observations.yaml to find next O{XX} id
    const obsContent = await agent(`Read ./ara/staging/observations.yaml and return the highest O{XX} ID number (the integer XX).
Return just the number as an integer (0 if no observations exist).`, {
      label: 'find-next-id',
      phase: 'Execute',
      schema: { type: 'object', properties: { maxId: { type: 'integer' } }, required: ['maxId'] },
    })
    const maxId = obsContent?.maxId || 0

    const newEntries = novel.map((n, i) => ({
      id: `O${String(maxId + i + 1).padStart(3, '0')}`,
      timestamp: new Date().toISOString().slice(0, 16).replace('T', 'T'),
      provenance: n.provenance || 'ai-executed',
      content: n.content,
      context: `Extracted from ${n.source}`,
      potential_type: n.potential_type,
      bound_to: [],
      promoted: false,
      promoted_to: null,
      crystallized_via: null,
      stale: false,
    }))

    await appendObservations(newEntries)
    log(`Staged ${newEntries.length} new observations`)
  }
}

// Remediation dispatcher — routes remediation actions to correct agent
if (remediationPlan && remediationPlan.dispatch) {
  const dispatchResults = await pipeline(
    remediationPlan.dispatch.filter(d => d.actions.length > 0),
    async (item) => {
      return await agent(`You are the ${item.target_agent} agent. Execute these remediation actions by modifying ARA project files at ./ara/.

Actions:
${item.actions.join('\n')}

Rules:
- logic/ files: edit in place (mutable)
- staging/ observations: append or set stale:true (append-only)
- Read current state first, then make targeted edits

Return:
{"agent": "${item.target_agent}", "changes": [{"file": "path", "action": "done"}], "errors": []}`, {
        label: `exec:${item.target_agent}`,
        phase: 'Execute',
      })
    },
    async (result) => result,
  )
  log(`Dispatch complete: ${dispatchResults.filter(Boolean).length} agents executed`)
}

// ═══════════════════════════════════════════════════════════════════════════════════
// VERIFY
// ═══════════════════════════════════════════════════════════════════════════════════

phase('Verify')

const VALIDATOR_17_SCHEMA = {
  type: 'object',
  properties: {
    passed: { type: 'boolean' },
    summary: { type: 'string' },
    checks: {
      type: 'object',
      properties: { total: { type: 'integer' }, passed: { type: 'integer' }, failed: { type: 'integer' } },
      required: ['total', 'passed', 'failed'],
    },
    failures: {
      type: 'array',
      items: {
        type: 'object',
        properties: { check: { type: 'string' }, details: { type: 'string' } },
        required: ['check', 'details'],
      },
    },
  },
  required: ['passed', 'summary', 'checks', 'failures'],
}

// Detect whether src/ has files for check #11 (heuristics Code ref)
const srcHasFiles = await agent(`Check if ./ara/src/ has any files beyond environment.md.
Return true/false.`, {
  label: 'src-check',
  phase: 'Verify',
  schema: { type: 'object', properties: { hasFiles: { type: 'boolean' } }, required: ['hasFiles'] },
}).then(r => r?.hasFiles || false)

const validationResult = await agent(`Run Seal Level 1 structural validation on the ARA project at ./ara/.

(src/ has extra files beyond environment.md: ${srcHasFiles})

Check all 17 items:

**Directory & file presence**:
1. PAPER.md exists and has YAML frontmatter with title, claims_summary
2. logic/{problem,claims,concepts,experiments,related_work}.md exist, non-empty
3. logic/solution/constraints.md exists, non-empty
4. src/environment.md exists, non-empty
5. trace/exploration_tree.yaml exists and parses as YAML
6. evidence/README.md exists
7. staging/observations.yaml exists and parses as YAML

**Cross-layer binding**:
8. Every claim Proof references a valid experiment ID
9. Every experiment Verifies references a valid claim ID
10. Tree evidence fields referencing C{XX} resolve to claims
11. Heuristic Code ref paths exist in src/ (only if both exist — srcHasFiles=${srcHasFiles})

**Provenance hygiene**:
12. Every claim has Provenance with valid ARA value (user|ai-suggested|ai-executed|user-revised)
13. Every claim has Falsification criteria

**Exploration tree hygiene**:
14. Tree nodes declare support_level (explicit|inferred)
15. No dead_end/pivot has empty lesson/trigger (warn only, do not fail)

**Self-consistency**:
16. PAPER.md claims_summary matches claim block count
17. IDs are unique within each file

Return the data in the specified JSON format.`, {
  label: 'validator',
  phase: 'Verify',
  schema: VALIDATOR_17_SCHEMA,
})

// ─── Build final report ──────────────────────────────────────────────────────────

const report = `ARA Organize Report (${focus}):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Claims: ${scoutReport?.claims?.total || 'N/A'} | Staging pending: ${scoutReport?.staging?.nonPromoted || 'N/A'}
Extracted: ${extractionResult?.stats?.novel || 0} new
Review: ${reviewResult?.summary?.approved || 0} approved, ${reviewResult?.summary?.needs_revision || 0} needs revision
Validation: ${validationResult?.passed ? 'PASS' : 'FAIL'} (${validationResult?.checks?.passed}/${validationResult?.checks?.total})
Summary: ${validationResult?.summary || 'N/A'}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`

log(report)

// ─── Daily report writer ─────────────────────────────────────────────────────────

if (isDaily) {
  const dateStr = new Date().toISOString().slice(0, 10)
  const dailyContent = `# ARA Daily Maintenance — ${dateStr}

\`\`\`
${report}
\`\`\`

## Scout Details

Claims by status: ${JSON.stringify(scoutReport?.claims?.byStatus)}
Staging: ${scoutReport?.staging?.nonPromoted} non-promoted, ${scoutReport?.staging?.staleCount} stale
Tree nodes: ${scoutReport?.tree?.total}

## Housekeeping

Stale marked: ${housekeeperReport?.toMarkStale?.length || 0}
Duplicates found: ${housekeeperReport?.duplicates?.length || 0}
Structural issues: ${housekeeperReport?.structuralIssues?.length || 0}

## Validation

${validationResult?.passed ? '✅ PASS' : '❌ FAIL'} (${validationResult?.checks?.passed}/${validationResult?.checks?.total})
${validationResult?.failures?.map(f => `- ${f.check}: ${f.details}`).join('\n') || ''}
`
  await writeDailyReport(dailyContent)
  log(`Daily report written to ara/daily/${dateStr}.md`)
}

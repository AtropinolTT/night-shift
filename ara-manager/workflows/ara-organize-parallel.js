export const meta = {
  name: 'ara-organize',
  description: 'Multi-agent ARA maintenance loop — parallel dispatch, iterative Review→Respond→Crystallize/Audit refinement loop',
  phases: [
    { title: 'Scout', detail: 'Parallel health report (claims + experiments + tree + sessions merge)' },
    { title: 'Extract', detail: 'Fan-out per-report extractors dedup merge' },
    { title: 'Iterate', detail: 'Crystallize+Audit Review(Opus) Respond(Sonnet) refine loop until PASS' },
    { title: 'Execute', detail: 'Pipeline parallel writes to ARA files' },
    { title: 'Verify', detail: 'Seal Level 1 structural validation' },
  ],
}

const ARA_DIR = '/sibcb1/chuyanyilab1/tangjunjie/project_BCR_Tree/ara'
const OUTPUT_DIR = '/sibcb1/chuyanyilab1/tangjunjie/project_BCR_Tree/output'
const MAX_LOOPS = 3
// Phase 1: Scout — parallel subagents
phase('Scout')

const [
  claimsAnalysis,
  experimentAnalysis,
  treeAnalysis,
  sessionAnalysis,
] = await Promise.all([
  agent(
    'Read ' + ARA_DIR + '/logic/claims.md and analyze:\n' +
    '- Count claims by status (supported/testing/hypothesis/weakened/refuted/withdrawn)\n' +
    '- Flag stale or missing fields (Provenance, Falsification criteria)\n' +
    '- Flag claims where completed experiments could justify advancement\n\n' +
    'Return JSON: { by_status:{}, stale_fields:[{claim_id,field,issue}], ready_for_advancement:[{claim_id,from,to,reason}] }',
    {
      label: 'scout-claims', phase: 'Scout',
      schema: { type: 'object', properties: {
        by_status: { type: 'object' },
        stale_fields: { type: 'array', items: { type: 'object' } },
        ready_for_advancement: { type: 'array', items: { type: 'object' } },
      }, required: ['by_status'] },
    }),
  agent(
    'Read ' + ARA_DIR + '/logic/experiments.md and analyze:\n' +
    '- Count total experiments, categorize by status\n' +
    '- Identify validated and complete experiments that could justify claim advancement\n\n' +
    'Return JSON: { total:N, by_status:{}, completed_unreflected:[] }',
    {
      label: 'scout-experiments', phase: 'Scout',
      schema: { type: 'object', properties: {
        total: { type: 'number' },
        by_status: { type: 'object' },
        completed_unreflected: { type: 'array' },
      }, required: ['total', 'by_status'] },
    }),
  agent(
    'Read ' + ARA_DIR + '/trace/exploration_tree.yaml and analyze:\n' +
    '- Count nodes by type (question/decision/experiment/dead_end/pivot)\n' +
    '- Identify dead_ends with missing lessons\n' +
    '- Open questions with no resolving children\n\n' +
    'Return JSON: { total:N, by_type:{}, missing_lessons:[], open_questions:[] }',
    {
      label: 'scout-tree', phase: 'Scout',
      schema: { type: 'object', properties: {
        total: { type: 'number' },
        by_type: { type: 'object' },
        missing_lessons: { type: 'array' },
        open_questions: { type: 'array' },
      }, required: ['total'] },
    }),
  agent(
    'Read ' + ARA_DIR + '/trace/sessions/session_index.yaml and extract:\n' +
    '- Latest session summary, open_threads, ai_suggestions_pending, key_context\n\n' +
    'Return JSON: { total_sessions:N, latest:{} }',
    {
      label: 'scout-sessions', phase: 'Scout',
      schema: { type: 'object', properties: {
        total_sessions: { type: 'number' },
        latest: { type: 'object' },
      }, required: ['total_sessions'] },
    }),
])

const scoutMerged = await agent(
  'Merge these parallel scout analyses into a unified health report.\n\n' +
  'CLAIMS: ' + JSON.stringify(claimsAnalysis) + '\n' +
  'EXPERIMENTS: ' + JSON.stringify(experimentAnalysis) + '\n' +
  'TREE: ' + JSON.stringify(treeAnalysis) + '\n' +
  'SESSION: ' + JSON.stringify(sessionAnalysis) + '\n\n' +
  'Return JSON with summary(string), issues(string array), claims_count(N), claims_by_status(object), experiments_count(N), experiments_by_status(object).',
  {
    label: 'scout-merge', phase: 'Scout',
    schema: { type: 'object', properties: {
      summary: { type: 'string' },
      issues: { type: 'array', items: { type: 'string' } },
      claims_count: { type: 'number' },
      claims_by_status: { type: 'object' },
      experiments_count: { type: 'number' },
      experiments_by_status: { type: 'object' },
    }, required: ['summary', 'issues'] },
  })

// Phase 2: Extract — fan-out per-report
phase('Extract')
log('Fanning out parallel extractors per report file...')

const reportFiles = [
  { path: OUTPUT_DIR + '/pipeline_final/BCR_Tree_Report_2026-05-17.md', label: 'r0517' },
  { path: OUTPUT_DIR + '/pipeline_final/BCR_Tree_Report_2026-05-18.md', label: 'r0518' },
  { path: OUTPUT_DIR + '/pipeline_final/BCR_Tree_Report_2026-05-20.md', label: 'r0520' },
  { path: OUTPUT_DIR + '/pipeline_final/BCR_Tree_Report_2026-05-21.md', label: 'r0521' },
  { path: OUTPUT_DIR + '/analysis_report_2026-06-10.md', label: 'analysis' },
  { path: OUTPUT_DIR + '/pipeline_final/q2a_isotype_results.json', label: 'q2a' },
  { path: OUTPUT_DIR + '/pipeline_final/q2b_neutralization_results.json', label: 'q2b' },
  { path: OUTPUT_DIR + '/pipeline_final/q3_selection_results.json', label: 'q3' },
]

const fileContents = await Promise.all(
  reportFiles.map(function(f) {
    return agent(
      'Read file at ' + f.path + '. If it exists, return full content. If not found, return "NOT_FOUND".',
      { label: 'read:' + f.label, phase: 'Extract' })
  })
)

const existingFiles = []
for (var i = 0; i < fileContents.length; i++) {
  if (fileContents[i] !== 'NOT_FOUND') {
    existingFiles.push({ path: reportFiles[i].path, label: reportFiles[i].label, content: fileContents[i] })
  }
}
log('Found ' + existingFiles.length + ' files for parallel extraction')

const perReportExtractions = await Promise.all(
  existingFiles.map(function(f) {
    return agent(
      'Extract novel observations from this research report.\n\n' +
      'EXISTING CLAIMS: C01(paired clustering), C02(tree+embedding), C03(antigen mapping), C04(tree vs labels)\n' +
      'EXISTING EXPERIMENTS: Q1(clustering comparison), Q2A(isotype classification), Q2B(CDRH3 prediction), Q3(antigen retrieval), Q4(label correlation), PPLM bridge\n\n' +
      'REPORT(' + f.label + '):\n' + (f.content || '').slice(0, 15000) + '\n\n' +
      'Return novel observations NOT in existing claims/experiments.\n' +
      'Each: { content:"falsifiable observation", potential_type:"claim|concept|constraint|heuristic|experiment|decision", context:"source", bound_to:[] }',
      {
        label: 'extract:' + f.label, phase: 'Extract',
        schema: { type: 'object', properties: {
          observations: { type: 'array', items: {
            type: 'object', properties: {
              content: { type: 'string' }, potential_type: { type: 'string' },
              context: { type: 'string' }, bound_to: { type: 'array', items: { type: 'string' } },
            }, required: ['content', 'potential_type', 'context'],
          }},
        }, required: ['observations'] },
      })
  })
)

var allObs = []
for (var i = 0; i < perReportExtractions.length; i++) {
  var obs = perReportExtractions[i]
  if (obs && obs.observations) {
    allObs = allObs.concat(obs.observations)
  }
}

const merged = await agent(
  'Deduplicate and merge these observations from ' + existingFiles.length + ' parallel extractors.\n\n' +
  'RAW observations (may have duplicates across reports):\n' + JSON.stringify(allObs) + '\n\n' +
  'Merge semantically identical findings (same insight from different reports, keep the richest version).\n\n' +
  'Return JSON: { observations:[{content,potential_type,context,bound_to}], stats:{total_raw:N, after_dedup:N, duplicates_removed:N} }',
  {
    label: 'dedup-merge', phase: 'Extract',
    schema: { type: 'object', properties: {
      observations: { type: 'array', items: {
        type: 'object', properties: {
          content: { type: 'string' }, potential_type: { type: 'string' },
          context: { type: 'string' }, bound_to: { type: 'array', items: { type: 'string' } },
        }, required: ['content', 'potential_type', 'context'],
      }},
      stats: { type: 'object' },
    }, required: ['observations'] },
  })

log('Extract: ' + merged.observations.length + ' observations after dedup')

// Phase 3: Iterative refinement loop
phase('Iterate')

var refinedCount = 0
var reviewVerdict = 'REVISE'
var finalDispatch = []
var finalCrystallize = []
var finalAudit = []
var finalReviewSummary = ''
var finalRespondSummary = ''
var prevFeedback = {}

for (var iter = 1; iter <= MAX_LOOPS; iter++) {
  var iterationLog = 'Refinement iteration ' + iter + '/' + MAX_LOOPS
  log(iterationLog)

  // Step 1: Generate proposals (parallel crystallizer + auditor)
  var revisionContext = ''
  if (iter > 1) {
    revisionContext = 'REVISE your previous proposals based on this feedback:\n' +
      JSON.stringify(prevFeedback) + '\n\n'
  }

  var crystallizeResult = await agent(
    revisionContext +
    'You are an ARA Crystallizer. Review observations for crystallization.\n\n' +
    'OBSERVATIONS:\n' + JSON.stringify(merged.observations) + '\n\n' +
    'CLAIMS: ' + JSON.stringify(claimsAnalysis) + '\n' +
    'EXPERIMENTS: ' + JSON.stringify(experimentAnalysis) + '\n\n' +
    'For each observation with a clear closure signal, suggest crystallization.\n' +
    'Signals: "resolution" (experiment complete), "commitment" (code/config depends on it), "affirmation" (confirmed), "abandonment" (no activity).\n\n' +
    'Return JSON: { suggestions: [{ observation_index:N, target_layer:"claims|concepts|constraints|experiments|heuristics", signal:"...", rationale:"..." }] }',
    {
      label: 'crystallize-iter' + iter, phase: 'Iterate',
      schema: { type: 'object', properties: {
        suggestions: { type: 'array', items: {
          type: 'object', properties: {
            observation_index: { type: 'number' }, target_layer: { type: 'string' },
            signal: { type: 'string' }, rationale: { type: 'string' },
          }, required: ['observation_index', 'target_layer', 'signal', 'rationale'],
        }},
      }, required: ['suggestions'] },
    })

  var auditResult = await agent(
    revisionContext +
    'You are an ARA Claim Auditor. Review claim statuses against experiment outcomes.\n\n' +
    'CLAIMS: ' + JSON.stringify(claimsAnalysis) + '\n' +
    'EXPERIMENTS: ' + JSON.stringify(experimentAnalysis) + '\n' +
    'EXTRACTED FINDINGS: ' + JSON.stringify(
      (merged.observations || []).filter(function(o) {
        return o.potential_type === 'claim' || o.potential_type === 'experiment'
      }).slice(0, 10)) + '\n\n' +
    'Allowed transitions: hypothesis-testing, testing-supported, testing-weakened, any-refuted, any-withdrawn, any-revised.\n' +
    'Rules: testing needs experiment evidence. If Q2A/Q2B are validated but C02 is still "testing", flag this.\n\n' +
    'Return JSON: { suggestions: [{ claim_id:"C0X", current_status:"...", suggested_status:"...", rationale:"...", blocker:null|"..." }] }',
    {
      label: 'audit-iter' + iter, phase: 'Iterate',
      schema: { type: 'object', properties: {
        suggestions: { type: 'array', items: {
          type: 'object', properties: {
            claim_id: { type: 'string' }, current_status: { type: 'string' },
            suggested_status: { type: 'string' }, rationale: { type: 'string' },
            blocker: { type: ['string', 'null'] },
          }, required: ['claim_id', 'current_status', 'suggested_status', 'rationale'],
        }},
      }, required: ['suggestions'] },
    })

  // Step 2: Review (Opus) — academic quality gate
  var reviewResult = await agent(
    'You are the ARA Reviewer (Opus). Academic quality gate. Iteration ' + iter + '/' + MAX_LOOPS + '.\n\n' +
    'CRITICALLY evaluate the Crystallize and Audit proposals for epistemic rigor before any writes proceed.\n\n' +
    'CLAIMS: ' + JSON.stringify(claimsAnalysis) + '\n' +
    'EXPERIMENTS: ' + JSON.stringify(experimentAnalysis) + '\n\n' +
    'CRYSTALLIZE PROPOSALS:\n' + JSON.stringify(crystallizeResult.suggestions) + '\n\n' +
    'AUDIT PROPOSALS:\n' + JSON.stringify(auditResult.suggestions) + '\n\n' +
    (iter > 1 ? 'Previous round feedback and how it was addressed:\n' + JSON.stringify(prevFeedback) + '\n\n' : '') +
    'Evaluate each proposal:\n' +
    '1. Is evidence sufficient? Are falsification criteria genuinely met?\n' +
    '2. Is the signal correct? (resolution vs interesting-result, etc.)\n' +
    '3. Would the proposed change make the ARA more or less rigorous?\n' +
    '4. Are there hidden assumptions?\n\n' +
    'For each proposal: APPROVE or REVISE with specific remediation.\n' +
    'CRITICAL: If REVISE, revisions_needed MUST include specific, actionable feedback.\n' +
    'Vague feedback like "needs more evidence" is useless. Say exactly what evidence is missing.\n\n' +
    'Return JSON: { approved_crystallizations:[indices], approved_audits:["C0X",...], revisions_needed:[{target,issue,remediation}], overall_verdict:"PASS"|"REVISE", summary:"..." }',
    {
      label: 'opus-review-iter' + iter, phase: 'Iterate',
      model: 'opus',
      schema: { type: 'object', properties: {
        approved_crystallizations: { type: 'array', items: { type: 'number' } },
        approved_audits: { type: 'array', items: { type: 'string' } },
        revisions_needed: { type: 'array', items: { type: 'object', properties: {
          target: { type: 'string' }, issue: { type: 'string' }, remediation: { type: 'string' },
        }, required: ['target', 'issue', 'remediation'] } },
        overall_verdict: { type: 'string', enum: ['PASS', 'REVISE'] },
        summary: { type: 'string' },
      }, required: ['overall_verdict', 'summary'] },
    })

  reviewVerdict = reviewResult.overall_verdict

  // Step 3: Respond (Sonnet) — refinement feedback or final dispatch
  var respondResult = await agent(
    'You are the ARA Responder (Sonnet). You receive Opus review verdicts and produce either:\n' +
    '- refinement feedback (if verdict=REVISE) to send back to Crystallizer and Auditor\n' +
    '- final dispatch actions (if verdict=PASS) for writing to ARA files\n\n' +
    'OPUS REVIEW (iter ' + iter + '):\n' + JSON.stringify(reviewResult) + '\n\n' +
    'CRYSTALLIZE: ' + JSON.stringify(crystallizeResult.suggestions) + '\n' +
    'AUDIT: ' + JSON.stringify(auditResult.suggestions) + '\n\n' +
    'IF REVISE:\n' +
    '- Extract specific revision feedback from reviewResult.revisions_needed\n' +
    '- Return as structured feedback_to_crystallizer and feedback_to_auditor arrays\n' +
    '- These will be injected into the next iteration for refinement\n\n' +
    'IF PASS:\n' +
    '- Generate final dispatch actions for approved proposals\n' +
    '- Each dispatch: { action:"write_to_logic"|"update_claim_status"|"stage_observation"|"log_trace", target_file:"path relative to ARA_DIR", content_draft:"exact content to write", rationale:"why" }\n\n' +
    'Return JSON: { mode:"refine"|"dispatch", feedback_to_crystallizer:[], feedback_to_auditor:[], dispatch:[], summary:"..." }',
    {
      label: 'sonnet-respond-iter' + iter, phase: 'Iterate',
      model: 'sonnet',
      schema: { type: 'object', properties: {
        mode: { type: 'string', enum: ['refine', 'dispatch'] },
        feedback_to_crystallizer: { type: 'array', items: { type: 'string' } },
        feedback_to_auditor: { type: 'array', items: { type: 'string' } },
        dispatch: { type: 'array', items: { type: 'object', properties: {
          action: { type: 'string', enum: ['write_to_logic', 'update_claim_status', 'stage_observation', 'log_trace'] },
          target_file: { type: 'string' }, content_draft: { type: 'string' }, rationale: { type: 'string' },
        }, required: ['action', 'target_file', 'content_draft', 'rationale'] } },
        summary: { type: 'string' },
      }, required: ['mode', 'summary'] },
    })

  if (respondResult.mode === 'refine') {
    prevFeedback = {
      crystallizer: respondResult.feedback_to_crystallizer || [],
      auditor: respondResult.feedback_to_auditor || [],
    }
    refinedCount++
    log('  Refining: ' + prevFeedback.crystallizer.length + ' crystallizer notes, ' +
        prevFeedback.auditor.length + ' auditor notes')
    continue
  }

  if (respondResult.mode === 'dispatch') {
    log('  PASS: ' + (respondResult.dispatch ? respondResult.dispatch.length : 0) + ' dispatch items ready')
    finalDispatch = respondResult.dispatch || []
    finalCrystallize = crystallizeResult.suggestions || []
    finalAudit = auditResult.suggestions || []
    finalReviewSummary = reviewResult.summary || ''
    finalRespondSummary = respondResult.summary || ''
    break
  }
}

if (reviewVerdict === 'REVISE' && refinedCount >= MAX_LOOPS) {
  log('Max iterations reached without PASS. Forcing dispatch of approved items.')
}

var iterationNote = ''
if (refinedCount > 0) {
  iterationNote = refinedCount + ' refinements over ' + Math.min(refinedCount + 1, MAX_LOOPS) + ' rounds'
} else {
  iterationNote = 'No refinements needed (first-pass PASS)'
}
log('Iteration complete: ' + iterationNote)

// Phase 4: Execute — staging + pipeline parallel writes
phase('Execute')
log('Staging observations + pipeline-parallel writes...')

if (merged.observations.length > 0) {
  await agent(
    'Read ' + ARA_DIR + '/staging/observations.yaml, find the highest O{XX} id number, ' +
    'then append these observations with sequential IDs:\n\n' +
    JSON.stringify((merged.observations || []).map(function(o, i) {
      return {
        id: 'O{next_id_plus_' + i + '}',
        timestamp: 'YYYY-MM-DDTHH:MM',
        provenance: 'ai-executed',
        content: o.content,
        context: o.context,
        potential_type: o.potential_type,
        bound_to: o.bound_to || [],
        promoted: false,
        promoted_to: null,
        crystallized_via: null,
        stale: false,
      }
    })) + '\n\nReturn the assigned ID range.',
    { label: 'stage-observations', phase: 'Execute' })
  log('Staged ' + merged.observations.length + ' observations')
}

// Execute dispatch actions via pipeline
var dispatchItems = (finalDispatch || []).filter(function(d) {
  return d.action !== 'stage_observation'
})

var results = await pipeline(
  dispatchItems,
  async function(item) {
    var fp = ARA_DIR + '/' + item.target_file
    if (item.action === 'write_to_logic') {
      return agent(
        'Read ' + fp + ', then append this content after the last entry:\n' +
        item.content_draft + '\nReturn DONE.',
        { label: 'write:' + item.target_file, phase: 'Execute' })
    } else if (item.action === 'update_claim_status') {
      return agent(
        'Edit ' + fp + ' per:\n' + item.content_draft +
        '\nFind the matching claim section and change only the Status field. Return DONE.',
        { label: 'update:' + item.target_file, phase: 'Execute' })
    } else if (item.action === 'log_trace') {
      return agent(
        'Read ' + fp + ', find the highest existing N{XX} id, then append a new node ' +
        'with the next sequential id:\n' + item.content_draft + '\nReturn DONE with the new node ID.',
        { label: 'log:' + item.target_file, phase: 'Execute' })
    }
    return null
  })

var executed = 0
for (var j = 0; j < results.length; j++) {
  if (results[j]) executed++
}
log('Executed ' + executed + '/' + dispatchItems.length + ' dispatch actions')

// Phase 5: Verify — Seal Level 1
phase('Verify')

var v = await agent(
  'Run Seal Level 1 structural validation on the ARA project at ' + ARA_DIR + '.\n\n' +
  'Perform all 17 checks:\n' +
  '1. PAPER.md exists, has YAML frontmatter with title, year, claims_summary\n' +
  '2. logic/problem.md, claims.md, concepts.md, experiments.md, related_work.md exist and non-empty\n' +
  '3. logic/solution/constraints.md exists and non-empty\n' +
  '4. src/environment.md exists and non-empty\n' +
  '5. trace/exploration_tree.yaml exists and parses as YAML\n' +
  '6. evidence/README.md exists\n' +
  '7. staging/observations.yaml exists and parses as YAML\n' +
  '8. Every claim Proof references a valid experiment ID (warn if absent)\n' +
  '9. Every experiment Verifies references a valid claim ID\n' +
  '10. Tree evidence fields referencing C{XX} resolve to claims\n' +
  '11. Heuristic Code ref paths exist in src/ (only if heuristics exist)\n' +
  '12. Every claim has Provenance with valid ARA value (user|ai-suggested|ai-executed|user-revised)\n' +
  '13. Every claim has Falsification criteria\n' +
  '14. Tree nodes declare support_level (warn, do not fail)\n' +
  '15. dead_end/pivot nodes have non-empty lesson/trigger (warn, do not fail)\n' +
  '16. PAPER.md claims_summary count matches number of ## C{XX}: blocks in claims.md\n' +
  '17. No duplicate IDs within any file\n\n' +
  'Return JSON: { passed_count:N, total_checks:17, overall:"PASS"|"FAIL", checks:[{check_id, name, passed, detail}] }',
  {
    label: 'seal1-verify', phase: 'Verify',
    schema: { type: 'object', properties: {
      passed_count: { type: 'number' },
      total_checks: { type: 'number' },
      overall: { type: 'string' },
      checks: { type: 'array', items: { type: 'object' } },
    }, required: ['passed_count', 'total_checks', 'overall'] },
  })

// Final report
log(
  'organize all completed.\n' +
  'Iterations: ' + iterationNote + '\n' +
  'Observations staged: ' + merged.observations.length + '\n' +
  'Crystallize proposals: ' + finalCrystallize.length + '\n' +
  'Audit suggestions: ' + finalAudit.length + '\n' +
  'Opus verdict: ' + reviewVerdict + ' - ' + finalReviewSummary.slice(0, 80) + '\n' +
  'Dispatch actions: ' + executed + '/' + dispatchItems.length + '\n' +
  'Validation: ' + v.passed_count + '/' + v.total_checks + ' checks (' + v.overall + ')'
)

return {
  scout: { summary: scoutMerged.summary },
  observations: merged.observations,
  iterations: refinedCount,
  crystallize: finalCrystallize,
  audit: finalAudit,
  review: { verdict: reviewVerdict, summary: finalReviewSummary },
  respond: { summary: finalRespondSummary },
  executed_count: executed,
  validation: v,
}

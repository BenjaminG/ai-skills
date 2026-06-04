export const meta = {
  name: "gate",
  description:
    "Deterministic quality gate: parallel reviewers + adversarial verify + context check",
  whenToUse:
    "Run on a feature branch before merge to surface BLOCKER/MAJOR/NIT findings, refuted by independent skeptics and cross-checked against project rules.",
  phases: [{ title: "Review" }, { title: "Verify" }, { title: "Context" }],
};

// args shape (from SKILL.md):
// {
//   diff:           string,   // full git diff $BASE...HEAD (may be truncated marker if too large)
//   diffSummary:    string,   // git diff --name-only output
//   plusLines:      string,   // formatted '+' lines per file
//   contextBundle:  string,   // contents of context-bundle.md
//   spawnFlags: {
//     react:     boolean,
//     a11y:      boolean,
//     i18n:      boolean,
//     migration: boolean,
//   },
//   sessionId:     string,
// }

const FINDING_SCHEMA_PROPS = {
  rule_id: { type: "string" },
  file: { type: "string" },
  line: { type: "integer" },
  location: { type: "string", enum: ["diff-line", "adjacent"] },
  tier: { type: "string", enum: ["BLOCKER", "MAJOR", "NIT"] },
  message: { type: "string" },
  evidence: { type: "string" },
  suggested_fix: { type: "string" },
};

const FINDING_REQUIRED = [
  "rule_id",
  "file",
  "line",
  "location",
  "tier",
  "message",
  "evidence",
  "suggested_fix",
];

const REVIEW_SCHEMA = {
  type: "object",
  properties: {
    findings: {
      type: "array",
      items: {
        type: "object",
        properties: FINDING_SCHEMA_PROPS,
        required: FINDING_REQUIRED,
      },
    },
  },
  required: ["findings"],
};

const SKEPTIC_SCHEMA = {
  type: "object",
  properties: {
    refuted: { type: "boolean" },
    reason: { type: "string" },
  },
  required: ["refuted", "reason"],
};

const CONTEXT_SCHEMA = {
  type: "object",
  properties: {
    annotations: {
      type: "array",
      items: {
        type: "object",
        properties: {
          file: { type: "string" },
          line: { type: "integer" },
          rule_id: { type: "string" },
          verdict: { type: "string", enum: ["OK", "CONFLICT", "UNCERTAIN"] },
          source: {
            type: "string",
            enum: ["linear", "pr", "session", "claude-md", "adr", "none"],
          },
          citation: { type: "string" },
          reason: { type: "string" },
        },
        required: ["file", "line", "rule_id", "verdict", "source", "reason"],
      },
    },
    synthesized: {
      type: "array",
      items: {
        type: "object",
        properties: {
          ...FINDING_SCHEMA_PROPS,
          citation: { type: "string" },
          source: { type: "string", enum: ["claude-md", "adr"] },
        },
        required: [...FINDING_REQUIRED, "citation", "source"],
      },
    },
  },
  required: ["annotations", "synthesized"],
};

const REVIEWERS = [
  { key: "bug", agentType: "ai-skills:bug-reviewer", condition: () => true },
  {
    key: "solid",
    agentType: "ai-skills:solid-reviewer",
    condition: () => true,
  },
  {
    key: "security",
    agentType: "ai-skills:security-reviewer",
    condition: () => true,
  },
  {
    key: "simplify",
    agentType: "ai-skills:simplify-reviewer",
    condition: () => true,
  },
  { key: "slop", agentType: "ai-skills:slop-reviewer", condition: () => true },
  {
    key: "react",
    agentType: "ai-skills:react-reviewer",
    condition: (f) => f.react,
  },
  {
    key: "a11y",
    agentType: "ai-skills:a11y-reviewer",
    condition: (f) => f.a11y,
  },
  {
    key: "i18n",
    agentType: "ai-skills:i18n-reviewer",
    condition: (f) => f.i18n,
  },
  {
    key: "migration",
    agentType: "ai-skills:migration-reviewer",
    condition: (f) => f.migration,
  },
];

function buildReviewPrompt(args, reviewerKey) {
  const sections = [
    "Review the diff below. Return findings via the structured-output tool.",
    "",
    "## `+` lines per file",
    "",
    args.plusLines || "(none)",
    "",
    "## Changed files",
    "",
    args.diffSummary || "(none)",
    "",
    "## Diff",
    "",
    args.diff,
  ];
  // bug-reviewer needs the PR body / Linear ticket / CLAUDE.md to detect
  // spec-vs-code mismatches and cross-file parity gaps. Other reviewers receive
  // the bundle only via the dedicated context-checker phase.
  if (reviewerKey === "bug" && args.contextBundle) {
    sections.push("", "## Project context", "", args.contextBundle);
  }
  return sections.join("\n");
}

function buildSkepticPrompt(finding, args) {
  return [
    "Refute this finding. Default to refuted=true if uncertain.",
    "",
    "## Finding under review",
    "",
    `- rule_id: ${finding.rule_id}`,
    `- file: ${finding.file}`,
    `- line: ${finding.line}`,
    `- location: ${finding.location}`,
    `- tier: ${finding.tier}`,
    `- message: ${finding.message}`,
    `- evidence: ${finding.evidence}`,
    `- suggested_fix: ${finding.suggested_fix}`,
    "",
    "## Diff context",
    "",
    args.diff,
  ].join("\n");
}

function buildContextPrompt(findings, bundle) {
  return [
    "Annotate the input findings against the project context bundle, and synthesize new findings for documented-rule violations.",
    "",
    "## Input findings",
    "",
    JSON.stringify(findings, null, 2),
    "",
    "## Context bundle",
    "",
    bundle || "(empty bundle)",
  ].join("\n");
}

const enabledReviewers = REVIEWERS.filter((r) => r.condition(args.spawnFlags));
log(`Reviewers enabled: ${enabledReviewers.map((r) => r.key).join(", ")}`);

const reviewerResults = await pipeline(
  enabledReviewers,
  // Stage 1: review
  (r) =>
    agent(buildReviewPrompt(args, r.key), {
      agentType: r.agentType,
      schema: REVIEW_SCHEMA,
      label: `review:${r.key}`,
      phase: "Review",
    }),
  // Stage 2: adversarial verify — 3 skeptics per finding
  (review, r) => {
    if (!review || !review.findings || review.findings.length === 0) {
      return { reviewer: r.key, findings: [] };
    }
    return parallel(
      review.findings.map(
        (f, fi) => () =>
          parallel(
            Array.from(
              { length: 3 },
              (_, si) => () =>
                agent(buildSkepticPrompt(f, args), {
                  agentType: "ai-skills:skeptic",
                  schema: SKEPTIC_SCHEMA,
                  label: `verify:${r.key}:${fi}:${si}`,
                  phase: "Verify",
                }),
            ),
          ).then((verdicts) => ({
            ...f,
            reviewer: r.key,
            verifications: (verdicts || []).filter(Boolean),
          })),
      ),
    ).then((annotated) => ({
      reviewer: r.key,
      findings: (annotated || []).filter(Boolean),
    }));
  },
);

// Drop findings refuted by ≥2 of 3 skeptics
const surviving = (reviewerResults || [])
  .filter(Boolean)
  .flatMap((r) => r.findings || [])
  .filter((f) => {
    const refuted = (f.verifications || []).filter((v) => v.refuted).length;
    return refuted < 2;
  });

log(`Surviving findings: ${surviving.length} (after adversarial verify)`);

// Context check phase — annotate survivors and synthesize CLAUDE.md/ADR violations
phase("Context");
let contextResult = { annotations: [], synthesized: [] };
if (
  surviving.length > 0 ||
  (args.contextBundle && args.contextBundle.trim().length > 0)
) {
  const result = await agent(
    buildContextPrompt(surviving, args.contextBundle),
    {
      agentType: "ai-skills:context-checker",
      schema: CONTEXT_SCHEMA,
      label: "context-check",
      phase: "Context",
    },
  );
  if (result) contextResult = result;
}

// Apply context annotations to survivors (badge them; verdict math is in SKILL.md)
const annotationKey = (a) => `${a.file}::${a.line}::${a.rule_id}`;
const annotationMap = {};
for (const a of contextResult.annotations || []) {
  annotationMap[annotationKey(a)] = a;
}

const annotated = surviving.map((f) => {
  const a = annotationMap[`${f.file}::${f.line}::${f.rule_id}`];
  if (!a) return { ...f, context_verdict: "OK", context_source: "none" };
  return {
    ...f,
    context_verdict: a.verdict,
    context_source: a.source,
    context_citation: a.citation || "",
    context_reason: a.reason || "",
  };
});

const synthesized = (contextResult.synthesized || []).map((f) => ({
  ...f,
  reviewer: "context-checker",
  verifications: [],
  context_verdict: "OK",
  context_source: f.source,
  context_citation: f.citation || "",
}));

const findings = [...annotated, ...synthesized];

return { findings };

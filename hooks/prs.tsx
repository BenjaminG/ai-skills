/* @jsxRuntime classic */
/* @jsx h */
/* @jsxFrag Fragment */
import type { EngineInterface as Engine, Register, Timer } from 'claude-code'

const ID = 'prs'
const POLL_MS = 60_000
const FIELDS =
  'number,title,headRefName,isDraft,reviewDecision,statusCheckRollup,url'
const DASH_SCRIPT = '/skills/babysit-prs/scripts/pr-dash.py'

type Check = { conclusion?: string | null; status?: string; state?: string }

type Pr = {
  number: number
  title: string
  isDraft: boolean
  reviewDecision: string
  statusCheckRollup: Check[]
}

const REVIEW: Record<string, [label: string, color: string]> = {
  APPROVED: ['approved', 'green'],
  CHANGES_REQUESTED: ['changes', 'red'],
  REVIEW_REQUIRED: ['review', 'gray'],
}

/** Red on any failed check, yellow while one runs, green once all passed. */
function checksOf(checks: Check[]): [glyph: string, color: string] {
  const verdicts = checks.map(c => c.conclusion || c.state || c.status || '')

  if (verdicts.some(v => /FAILURE|TIMED_OUT|CANCELLED|ACTION_REQUIRED|ERROR/.test(v))) {
    return ['✗', 'red']
  }

  if (verdicts.some(v => /PENDING|IN_PROGRESS|QUEUED|WAITING|EXPECTED/.test(v))) {
    return ['◐', 'yellow']
  }

  return verdicts.length === 0 ? ['·', 'gray'] : ['✓', 'green']
}

type Run = { exitCode: number; stdout: string; stderr: string }

// Module state: one hooks module runs per session. The loader lets `$` reach
// only functions declared at the module's top, so `refresh` lives here too.
let prs: Pr[] | null = null
let error: string | null = null
let isOpen = false
let poll: Timer | null = null

// The extended view: pr-dash's own snapshot over babysit-prs' state, run
// read-only, drawn as text. The script is the one reader of that state.
type View = 'compact' | 'detailed'
let view: View = 'compact'
let dash: string | null = null
let dashError: string | null = null

// This module's address, as the loader seated it: the plugin's hooks/ folder.
// `plugin.register` fires before a module's hooks join the chain, so it cannot
// hand this over — import.meta can.
const HOOKS_DIR = new URL('.', import.meta.url).pathname
const DASH_PATH = new URL(`../..${DASH_SCRIPT}`, import.meta.url).pathname

async function refresh($: Engine) {
  const run = await $.process
    .run(['gh', 'pr', 'list', '--author', '@me', '--json', FIELDS])
    .catch((e: unknown): Run => ({
      exitCode: 1,
      stdout: '',
      stderr: e instanceof Error ? e.message : String(e),
    }))

  if (run.exitCode === 0) {
    prs = JSON.parse(run.stdout) as Pr[]
    error = null
  } else {
    error = run.stderr.trim() || `gh exited ${run.exitCode}`
  }

  $.ui.invalidate('ui.render')
}

async function refreshDash($: Engine) {
  const run = await $.process
    .run(['python3', DASH_PATH, 'status'])
    .catch((e: unknown): Run => ({
      exitCode: 1,
      stdout: '',
      stderr: e instanceof Error ? e.message : String(e),
    }))

  if (run.exitCode === 0 && run.stdout.trim() !== '') {
    dash = run.stdout.replace(/\n+$/, '\n')
    dashError = null
  } else {
    dashError = run.stderr.trim() || `pr-dash exited ${run.exitCode}`
  }

  $.ui.invalidate('ui.render')
}

function load($: Engine) {
  void (view === 'detailed' ? refreshDash($) : refresh($))
}

export const COMMAND = {
  name: ID,
  description:
    'My open PRs: compact (checks, review state, a button per PR filling /pr-feedback) or detailed (pr-dash stacks, threads, notes)',
} as const

/** The pane's hooks; `session.start` registers COMMAND once for every pane, in register.ts. */
export const register: Register = on => {
  on('command.run', { command: ID }, async $ => {
    if (isOpen) {
      await $.ui.close({ id: ID })

      return { text: 'PRs panel hidden' }
    }

    isOpen = true
    view = 'compact'
    dash = null
    dashError = null
    await $.ui.open({ id: ID, title: 'PRs' })
    poll = $.clock.every(POLL_MS, () => load($))
    load($)

    return { text: 'PRs panel shown' }
  })

  on('ui.close', { id: ID }, async ($, e, next) => {
    const result = await next(e)

    if (result.deny === undefined) {
      isOpen = false
      poll?.cancel()
      poll = null
    }

    return result
  })

  on('ui.render', { component: 'Pane', requestId: ID }, async ($, e, next) => {
    if (e.surface === 'mobile') {
      return next(e)
    }

    const { Box, Text, Button } = await $.ui.resolve(e)
    const width = e.props.bodyColumns - 2

    const header = (
      <Box flexDirection="row" gap={1}>
        <Text bold>{`PRs · ${view === 'detailed' ? 'stacks' : (prs?.length ?? '…')}`}</Text>
        <Button
          key="prs:view"
          plain
          onPress={() => {
            view = view === 'compact' ? 'detailed' : 'compact'
            load($)
          }}
        >
          {view === 'compact' ? '[detailed]' : '[compact]'}
        </Button>
      </Box>
    )

    if (view === 'detailed') {
      return (
        <Box flexDirection="column" paddingX={1}>
          {header}
          {dashError === null ? (
            dash === null ? (
              <Text dimColor>Loading pr-dash…</Text>
            ) : (
              <Text wrap="wrap">{dash}</Text>
            )
          ) : (
            <Text color="red">{dashError}</Text>
          )}
          <Text dimColor>babysit-prs state · /prs to close</Text>
        </Box>
      )
    }

    const rows = (prs ?? []).map(pr => {
      const [glyph, glyphColor] = checksOf(pr.statusCheckRollup)
      const [review, reviewColor] = pr.isDraft
        ? ['draft', 'gray']
        : (REVIEW[pr.reviewDecision] ?? ['', 'gray'])
      const label = `#${pr.number} ${pr.title}`.slice(
        0,
        Math.max(8, width - review.length - 4),
      )

      return (
        <Box key={`pr:${pr.number}`} flexDirection="row" gap={1}>
          <Text color={glyphColor}>{glyph}</Text>
          <Button
            key={`pr:${pr.number}`}
            plain
            onPress={() =>
              void $.prompt.fill({ text: `/pr-feedback ${pr.number}` })
            }
          >
            {label}
          </Button>
          <Text color={reviewColor} dimColor>
            {review}
          </Text>
        </Box>
      )
    })

    const note = error ?? (prs === null ? 'Loading…' : rows.length === 0 ? 'No open PR' : null)

    return (
      <Box flexDirection="column" paddingX={1}>
        {header}
        {note === null ? null : <Text color={error ? 'red' : undefined} dimColor={!error}>{note}</Text>}
        {rows}
        <Text dimColor>Click a PR to fill /pr-feedback · refreshes every 60 s</Text>
      </Box>
    )
  })
}

/* @jsxRuntime classic */
/* @jsx h */
/* @jsxFrag Fragment */
import type { EngineInterface as Engine, Register, Timer } from 'claude-code'

const ID = 'prs'
// The state is a local file: stat it often, run pr-dash only when it moved — or once a minute
// regardless, since each run is also what keeps the scan service alive.
const TICK_MS = 5_000
const RELOAD_TICKS = 12
const DASH_SCRIPT = '/skills/pr-dash/scripts/pr-dash.py'

/** One row as `pr-dash status --json` hands it over, in stack order. */
type Pr = { number: number; title: string; url: string; ci: string; status: string }

type Summary = { state: string; text: string; prs: Pr[] }

const CI: Record<string, [glyph: string, color: string]> = {
  SUCCESS: ['✓', 'green'],
  FAILURE: ['✗', 'red'],
  PENDING: ['◐', 'yellow'],
}

type Run = { exitCode: number; stdout: string; stderr: string }

// Module state: one hooks module runs per session. The loader lets `$` reach
// only functions declared at the module's top, so `load` and `tick` live here too.
let summary: Summary | null = null
let error: string | null = null
let isOpen = false
let poll: Timer | null = null
let ticks = 0
let seen = -1

// Both views read one pr-dash run: compact draws its rows, detailed its table.
type View = 'compact' | 'detailed'
let view: View = 'compact'

// This module sits in the plugin's hooks/ folder; the script, one level up.
const DASH_PATH = new URL(`..${DASH_SCRIPT}`, import.meta.url).pathname

/** The state file's mtime in seconds, or -1: `date -r` reads it on macOS and GNU alike. */
async function stateMtime($: Engine, path: string) {
  const run = await $.process.run(['date', '-r', path, '+%s']).catch(() => null)

  return run?.exitCode === 0 ? Number(run.stdout.trim()) : -1
}

async function load($: Engine) {
  ticks = 0
  const run = await $.process
    .run(['python3', DASH_PATH, 'status', '--json'])
    .catch((e: unknown): Run => ({
      exitCode: 1,
      stdout: '',
      stderr: e instanceof Error ? e.message : String(e),
    }))

  if (run.exitCode === 0) {
    summary = JSON.parse(run.stdout) as Summary
    error = null
    seen = await stateMtime($, summary.state)
  } else {
    error = run.stderr.trim() || `pr-dash exited ${run.exitCode}`
  }

  $.ui.invalidate('ui.render')
}

async function tick($: Engine) {
  ticks += 1

  if (summary !== null && error === null && ticks < RELOAD_TICKS) {
    if ((await stateMtime($, summary.state)) === seen) {
      return
    }
  }

  await load($)
}

export const COMMAND = {
  name: ID,
  description:
    'My open PRs: compact (checks, status, a button per PR filling /pr-feedback) or detailed (pr-dash stacks, threads, notes)',
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
    summary = null
    error = null
    await $.ui.open({ id: ID, title: 'PRs' })
    poll = $.clock.every(TICK_MS, () => void tick($))
    void load($)

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
    const prs = summary?.prs ?? []

    const header = (
      <Box flexDirection="row" gap={1}>
        <Text bold>{`PRs · ${view === 'detailed' ? 'stacks' : summary === null ? '…' : prs.length}`}</Text>
        <Button
          key="prs:view"
          plain
          onPress={() => {
            view = view === 'compact' ? 'detailed' : 'compact'
            $.ui.invalidate('ui.render')
          }}
        >
          {view === 'compact' ? '[detailed]' : '[compact]'}
        </Button>
      </Box>
    )

    if (error !== null || summary === null) {
      return (
        <Box flexDirection="column" paddingX={1}>
          {header}
          {error === null ? <Text dimColor>Loading…</Text> : <Text color="red">{error}</Text>}
        </Box>
      )
    }

    if (view === 'detailed') {
      return (
        <Box flexDirection="column" paddingX={1}>
          {header}
          <Text wrap="wrap">{summary.text}</Text>
          <Text dimColor>pr-scan state · /prs to close</Text>
        </Box>
      )
    }

    const rows = prs.map(pr => {
      const [glyph, glyphColor] = CI[pr.ci] ?? ['·', 'gray']
      const label = `#${pr.number} ${pr.title}`.slice(
        0,
        Math.max(8, width - pr.status.length - 4),
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
          <Text dimColor>{pr.status}</Text>
        </Box>
      )
    })

    return (
      <Box flexDirection="column" paddingX={1}>
        {header}
        {rows.length === 0 ? <Text dimColor>No open PR</Text> : null}
        {rows}
        <Text dimColor>Click a PR to fill /pr-feedback · live from pr-scan</Text>
      </Box>
    )
  })
}

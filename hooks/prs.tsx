/* @jsxRuntime classic */
/* @jsx h */
/* @jsxFrag Fragment */
import type { EngineInterface as Engine, Register, Timer } from 'claude-code'

const ID = 'prs'
// state.json is a local file pr-dash's Scan service rewrites each pass: read it often, and
// `ensure` now and then, since a Reader's ensure is what keeps the service alive.
const TICK_MS = 5_000
const ENSURE_MS = 5 * 60_000
const SCHEMA_VERSION = 4
const INSTALL = 'pr-dash not found: npm i -g github:BenjaminG/pr-dash'

/** The fields of a state.json row this pane draws. */
type Pr = { number: number; title: string; ci: string; status: string; draft: boolean }

type State = { schema_version: number; taken_at: string; error: { at: string; message: string } | null; prs: Pr[] }

const CI: Record<string, [glyph: string, color: string]> = {
  SUCCESS: ['✓', 'green'],
  FAILURE: ['✗', 'red'],
  PENDING: ['◐', 'yellow'],
}

// Module state: one hooks module runs per session. The loader lets `$` reach
// only functions declared at the module's top, so `open` and `tick` live here too.
let state: State | null = null
let error: string | null = null
let dir: string | null = null
let isOpen = false
let poll: Timer | null = null
let keepAlive: Timer | null = null
/** What the drawn State was: its pass and its error, so a failing pass that keeps taken_at still redraws. */
let drawn = ''

async function prDash($: Engine, ...args: string[]) {
  return $.process.run(['pr-dash', ...args]).catch(() => null)
}

async function tick($: Engine) {
  if (dir === null) {
    return
  }

  const text = await $.fs.read(`${dir}/state.json`).catch(() => null)

  if (typeof text !== 'string') {
    return // the service's first pass is still running
  }

  const next = JSON.parse(text) as State
  const key = `${next.taken_at} ${next.error?.at ?? ''}`

  if (key !== drawn) {
    drawn = key
    state = next
    $.ui.invalidate('ui.render')
  }
}

async function open($: Engine) {
  const run = await prDash($, 'state-dir')

  if (run?.exitCode !== 0) {
    error = run === null ? INSTALL : run.stderr.trim() || `pr-dash exited ${run.exitCode}`
    $.ui.invalidate('ui.render')

    return
  }

  dir = run.stdout.trim().replace(/\/$/, '')
  await prDash($, 'ensure')
  await tick($)
}

export const COMMAND = {
  name: ID,
  description: 'My open PRs, drafts aside: checks, status, a button per PR filling /pr-feedback',
} as const

/** The pane's hooks; `session.start` registers COMMAND once for every pane, in register.ts. */
export const register: Register = on => {
  on('command.run', { command: ID }, async $ => {
    if (isOpen) {
      await $.ui.close({ id: ID })

      return { text: 'PRs panel hidden' }
    }

    isOpen = true
    state = null
    error = null
    dir = null
    drawn = ''
    await $.ui.open({ id: ID, title: 'PRs' })
    poll = $.clock.every(TICK_MS, () => void tick($))
    keepAlive = $.clock.every(ENSURE_MS, () => void (dir !== null && prDash($, 'ensure')))
    void open($)

    return { text: 'PRs panel shown' }
  })

  on('ui.close', { id: ID }, async ($, e, next) => {
    const result = await next(e)

    if (result.deny === undefined) {
      isOpen = false
      poll?.cancel()
      keepAlive?.cancel()
      poll = null
      keepAlive = null
    }

    return result
  })

  on('ui.render', { component: 'Pane', requestId: ID }, async ($, e, next) => {
    if (e.surface === 'mobile') {
      return next(e)
    }

    const { Box, Text, Button } = await $.ui.resolve(e)
    const width = e.props.bodyColumns - 2
    const prs = state?.prs?.filter(pr => !pr.draft) ?? []
    const header = <Text bold>{`PRs · ${state === null ? '…' : prs.length}`}</Text>

    if (error !== null || state === null) {
      return (
        <Box flexDirection="column" paddingX={1}>
          {header}
          {error === null ? <Text dimColor>Loading…</Text> : <Text color="red">{error}</Text>}
        </Box>
      )
    }

    if (state.schema_version !== SCHEMA_VERSION) {
      return (
        <Box flexDirection="column" paddingX={1}>
          {header}
          <Text color="yellow">
            {`outdated: pr-dash writes State v${state.schema_version}, this pane reads v${SCHEMA_VERSION}; update ai-skills or pr-dash`}
          </Text>
        </Box>
      )
    }

    const rows = prs.map(pr => {
      const [glyph, glyphColor] = CI[pr.ci] ?? ['·', 'gray']
      const label = `#${pr.number} ${pr.title}`.slice(0, Math.max(8, width - pr.status.length - 4))

      return (
        <Box key={`pr:${pr.number}`} flexDirection="row" gap={1}>
          <Text color={glyphColor}>{glyph}</Text>
          <Button key={`pr:${pr.number}`} plain onPress={() => void $.prompt.fill({ text: `/pr-feedback ${pr.number}` })}>
            {label}
          </Button>
          <Text dimColor>{pr.status}</Text>
        </Box>
      )
    })

    return (
      <Box flexDirection="column" paddingX={1}>
        {header}
        {state.error === null ? null : <Text color="red">{state.error.message}</Text>}
        {rows.length === 0 ? <Text dimColor>No open PR</Text> : null}
        {rows}
        <Text dimColor>Click a PR to fill /pr-feedback · live from pr-dash</Text>
      </Box>
    )
  })
}

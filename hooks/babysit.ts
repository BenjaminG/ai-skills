import type { EngineInterface as Engine, Register, Timer } from 'claude-code'

const ID = 'shepherd'
// The skill's first pass spawns in waves of about four; the same bound caps a runaway loop.
const MAX_AGENTS = 4
const DEBOUNCE_MS = 2_000
const POLL_MS = 5_000
const ENSURE_MS = 5 * 60_000
// ponytail: a flat grace for an agent's background command; one running longer than this with no
// report yet loses its mute early. Per-agent tracking of background children if that ever happens.
const GRACE_MS = 10 * 60_000
const LOCKED = 'babysit-prs already active'
const ARGS = /^(?:\d+|--include-drafts)$/
const USAGE = 'Usage: /shepherd [dry|stop] [PR…] [--include-drafts]'
const INSTALL = 'pr-dash not found: npm i -g github:BenjaminG/pr-dash'
const SCHEMA_VERSION = 4
const WATCH = '/skills/babysit-prs/scripts/watch.sh'
const PROMPT = '/skills/babysit-prs/references/agent-prompt.md'

/** One row of pr-dash's state.json, the fields the manager reads. */
type Row = {
  number: number
  draft: boolean
  branch: string
  base: string
  head: string
  parent: number | null
  needs_agent: boolean
  waits_on: number | null
  agent_running: boolean
  merge_ready: boolean
  held: number
  report: { blocked?: string | null } | null
}

type State = { schema_version: number; error: { message: string } | null; prs: Row[] }

type Follow = ReturnType<Engine['process']['spawn']>

// Module state. A reload drops it: the watch dies with the module and the mutes on disk keep
// every live agent's stack reserved until /shepherd runs again.
let mode: 'off' | 'dry' | 'on' = 'off'
let args: string[] = []
let follow: Follow | null = null
let poll: Timer | null = null
let keepAlive: Timer | null = null
let pending: Timer | null = null
let passing = false
let again = false
let stateDir: string | null = null
let seen = -1
/** The PRs whose agent this module started and has not seen end. */
const started = new Set<number>()
/** A PR whose agent ended a turn without a report → when that turn ended. */
const lastTurn = new Map<number, number>()
/** `ready:<n>`, `held:<n>`, `would:<n>`: what was told already, until it stops being true. */
const told = new Set<string>()

export const COMMAND = {
  name: ID,
  description: 'Babysit my open PRs with no manager in the conversation: one Opus agent per PR that needs one',
  argumentHint: '[dry|stop] [PR…] [--include-drafts]',
} as const

async function shell($: Engine, argv: readonly string[]) {
  return $.process.run(argv).catch((err: unknown) => ({ exitCode: 1, stdout: '', stderr: String(err) }))
}

async function tell($: Engine, key: string, isTrue: boolean, text: string) {
  if (!isTrue) {
    told.delete(key)
  } else if (!told.has(key)) {
    told.add(key)
    await $.ui.toast(text)
  }
}

/** The prompt between references/agent-prompt.md's two rules, filled from the PR's row. */
async function promptFor($: Engine, r: Row, dir: string) {
  const file = await $.fs.read(`${$.plugin.root}${PROMPT}`)
  const text = typeof file === 'string' ? file : ''
  const body = text.slice(text.indexOf('\n---\n') + 5, text.lastIndexOf('\n---\n')).trim()

  return body
    .replace(/\s*\[stacked: ([\s\S]*?)\]/, (_, clause: string) => (r.parent === null ? '' : ` ${clause}`))
    .replaceAll('<n>', String(r.number))
    .replaceAll('<parent>', String(r.parent))
    .replaceAll('<base>', r.base)
    .replaceAll('<head>', r.branch)
    .replaceAll('<state_dir>', dir)
}

async function spawnFor($: Engine, r: Row, dir: string) {
  const mute = `${dir}/${r.number}.muted`
  const prompt = await promptFor($, r, dir)
  // Before the agent: the mute is what keeps its stack reserved while it works.
  await $.fs.write(mute, '')
  const spawn = await $.agent
    .spawn({
      prompt,
      description: `Own PR #${r.number}`,
      subagentType: 'general-purpose',
      model: 'opus',
    })
    .catch((err: unknown) => ({ deny: String(err) }))

  if (spawn.deny !== undefined) {
    await shell($, ['rm', '-f', mute])
    await $.ui.toast(`babysit: no agent on #${r.number}: ${spawn.deny}`)

    return
  }

  started.add(r.number)
}

/** Has PR `n`'s agent reported, or has the scan already folded its report and lifted the mute? */
async function reported($: Engine, n: number) {
  return (
    stateDir === null ||
    (await $.fs.exists(`${stateDir}/${n}.report.json`)) ||
    !(await $.fs.exists(`${stateDir}/${n}.muted`))
  )
}

/**
 * An agent of this module's ended a turn. With its report written, its PR is done. Without one it
 * may still be waiting on a background command (it then takes another turn), or it died: past
 * the grace with no other turn, its mute goes, or it would hold its stack for the hour.
 */
async function agentEnded($: Engine, agentId: string) {
  const agent = (await $.agent.list().catch(() => [])).find(a => a.id === agentId && a.spawnedBy === $.plugin.name)
  const n = Number(/^Own PR #(\d+)$/.exec(agent?.description ?? '')?.[1])

  if (!started.has(n)) {
    return
  }

  if (await reported($, n)) {
    started.delete(n)

    return
  }

  const at = await $.clock.now()
  lastTurn.set(n, at)
  $.clock.after(GRACE_MS, () => void reap($, n, at))
}

async function reap($: Engine, n: number, at: number) {
  if (lastTurn.get(n) !== at) {
    return
  }

  lastTurn.delete(n)
  started.delete(n)

  if (!(await reported($, n))) {
    await shell($, ['rm', '-f', `${stateDir}/${n}.muted`])
    await $.ui.toast(`babysit: the agent on #${n} ended without a report`)
  }

  await status($)
}

/** The State's rows this run babysits: the named PRs, else every one but the drafts unless asked. */
async function select($: Engine, prs: Row[]) {
  const named = args.filter(a => a !== '--include-drafts').map(Number)

  if (named.length === 0) {
    return args.includes('--include-drafts') ? prs : prs.filter(r => !r.draft)
  }

  for (const n of named) {
    await tell($, `absent:${n}`, !prs.some(r => r.number === n), `babysit: #${n} is not one of your open PRs; skipped`)
  }

  return prs.filter(r => named.includes(r.number))
}

/** state.json, or why there is none to act on. */
async function readState($: Engine, dir: string): Promise<State | string> {
  const text = await $.fs.read(`${dir}/state.json`).catch(() => null)
  const state = typeof text === 'string' ? (JSON.parse(text) as State) : null

  if (state === null) {
    return 'no State yet'
  }

  if (state.schema_version !== SCHEMA_VERSION) {
    return `pr-dash writes State v${state.schema_version}, this reads v${SCHEMA_VERSION}; update ai-skills or pr-dash`
  }

  return state
}

async function passOnce($: Engine) {
  if (stateDir === null) {
    return
  }

  if (mode === 'on') {
    // wake --wait exits 1 when no fresh State came in time; the last one is still worth a pass.
    await shell($, ['pr-dash', 'wake', '--wait'])
  }

  const state = await readState($, stateDir)

  if (typeof state === 'string') {
    await tell($, 'scan', true, `babysit: ${state}`)

    return
  }

  told.delete('scan')
  // A failed pass keeps the last good rows: say why once, and act on them.
  await tell($, 'error', state.error !== null, `babysit: pr-dash: ${state.error?.message}`)
  const prs = await select($, state.prs)
  const due: Row[] = []

  for (const r of prs) {
    const isDue = r.needs_agent && r.waits_on === null && !r.agent_running && !r.report?.blocked
    if (isDue) {
      due.push(r)
    }

    await tell($, `ready:${r.number}`, r.merge_ready, `#${r.number} is merge-ready`)
    await tell($, `held:${r.number}`, r.held > 0, `#${r.number} waits on you: /pr-explain ${r.number}`)

    if (mode === 'dry') {
      await tell($, `would:${r.number}`, isDue, `babysit dry: would spawn an agent on #${r.number}`)
    }
  }

  if (mode === 'on') {
    const slots = MAX_AGENTS - prs.filter(r => r.agent_running).length

    for (const r of due.slice(0, Math.max(0, slots))) {
      await spawnFor($, r, stateDir)
    }
  }

  await status($)
}

/** One pass at a time; a request landing meanwhile runs one more pass after it. */
async function pass($: Engine) {
  if (passing) {
    again = true

    return
  }

  passing = true
  try {
    do {
      again = false
      await passOnce($).catch((err: unknown) => $.ui.toast(`babysit: the pass failed: ${String(err)}`))
    } while (again && mode !== 'off')
  } finally {
    passing = false
  }
}

/** Events come in bursts (a push moves head, ci and merge state): one pass per burst. */
function schedule($: Engine) {
  pending ??= $.clock.after(DEBOUNCE_MS, () => {
    pending = null
    void pass($)
  })
}

async function status($: Engine) {
  if (mode === 'off') {
    await $.ui.status(undefined)
  } else if (mode === 'dry') {
    await $.ui.status('babysit dry')
  } else {
    await $.ui.status(`babysit · ${started.size} agent${started.size === 1 ? '' : 's'}`)
  }
}

async function stop($: Engine) {
  mode = 'off'
  const stream = follow
  follow = null
  poll?.cancel()
  keepAlive?.cancel()
  pending?.cancel()
  poll = null
  keepAlive = null
  pending = null
  void stream?.return({ code: null, signal: null })
  await status($)
}

/** watch.sh holds babysit.lock around `pr-dash follow`, which keeps the service alive; each line is a transition. */
async function watch($: Engine, stream: Follow) {
  try {
    for await (const { text } of stream) {
      if (text.includes(LOCKED)) {
        await $.ui.toast('babysit: another session is already babysitting this repo')
        await stop($)

        return
      }

      schedule($)
    }
  } catch (err) {
    await $.ui.toast(`babysit: the watch failed: ${String(err)}`)
  }

  if (follow === stream) {
    await $.ui.toast('babysit: the watch ended')
    await stop($)
  }
}

async function stateMtime($: Engine) {
  const stat = stateDir === null ? null : await $.fs.stat(`${stateDir}/state.json`).catch(() => null)

  return stat?.mtimeMs ?? -1
}

/** Dry mode never takes the lock, so it runs beside a babysit-prs manager: it follows state.json. */
async function tick($: Engine) {
  const mtime = await stateMtime($)

  if (mtime !== seen) {
    seen = mtime
    await pass($)
  }
}

async function start($: Engine, next: 'dry' | 'on', selection: string[]) {
  mode = next
  args = selection
  told.clear()
  const run = await $.process.run(['pr-dash', 'state-dir']).catch(() => null)

  if (run?.exitCode !== 0) {
    await $.ui.toast(`babysit: ${run === null ? INSTALL : run.stderr.trim()}`)
    await stop($)

    return
  }

  stateDir = run.stdout.trim().replace(/\/$/, '')

  if (next === 'on') {
    const stream = $.process.spawn({
      argv: [`${$.plugin.root}${WATCH}`, ...selection.filter(a => a !== '--include-drafts')],
    })
    follow = stream
    void watch($, stream)
    await pass($)
  } else {
    await shell($, ['pr-dash', 'ensure'])
    keepAlive = $.clock.every(ENSURE_MS, () => void shell($, ['pr-dash', 'ensure']))
    await pass($)
    seen = await stateMtime($)
    poll = $.clock.every(POLL_MS, () => void tick($))
  }
}

export const register: Register = on => {
  on('command.run', { command: ID }, async ($, e) => {
    const words = e.args.trim().split(/\s+/).filter(Boolean)
    const verb = words[0] === 'dry' || words[0] === 'stop' ? words.shift() : undefined

    if (!words.every(word => ARGS.test(word))) {
      return { text: USAGE }
    }

    if (verb === 'stop' || (verb === undefined && words.length === 0 && mode !== 'off')) {
      const wasOn = mode !== 'off'
      await stop($)

      return { text: wasOn ? `babysit off; ${started.size} agent(s) still finishing` : 'babysit is not running' }
    }

    await stop($)
    void start($, verb === 'dry' ? 'dry' : 'on', words)

    return {
      text:
        verb === 'dry'
          ? 'babysit dry: says which PR would get an agent, starts none. /shepherd stop to end'
          : 'babysit on: one Opus agent per PR that needs one, no manager in this conversation. /shepherd stop to end',
    }
  })

  // A turn of an unnamed agent ended (a named one idles as a teammate instead, so this module
  // never names its own).
  on('turn.complete', { agentId: /^a[0-9a-f]+$/ }, async ($, e, next) => {
    const result = await next(e)

    if (started.size === 0 || e.agentId === undefined) {
      return result
    }

    await agentEnded($, e.agentId)

    if (mode === 'on') {
      schedule($)
    }

    await status($)

    return result
  })
}

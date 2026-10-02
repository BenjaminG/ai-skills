import type { EngineInterface as Engine, Register, Timer } from 'claude-code'

const ID = 'babysit'
// pr-scan's own first pass spawns in waves of about four; the same bound caps a runaway loop.
const MAX_AGENTS = 4
const DEBOUNCE_MS = 2_000
const POLL_MS = 5_000
// ponytail: a flat grace for an agent's background command; one running longer than this with no
// report yet loses its mute early. Per-agent tracking of background children if that ever happens.
const GRACE_MS = 10 * 60_000
const LOCKED = 'babysit-prs already active'
const ARGS = /^(?:\d+|--include-drafts)$/
const USAGE = 'Usage: /babysit [dry|stop] [PR…] [--include-drafts]'
const SCAN = '/skills/pr-dash/scripts/pr-scan.py'
const PROMPT = '/skills/babysit-prs/references/agent-prompt.md'

/** One PR of pr-scan's blob, the fields the manager reads. */
type Row = {
  number: number
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

type Scan = { state_dir: string; prs: Row[] }

type Follow = ReturnType<Engine['process']['spawn']>

// Module state. A reload drops it: the watch dies with the module and the mutes on disk keep
// every live agent's stack reserved until /babysit runs again.
let mode: 'off' | 'dry' | 'on' = 'off'
let args: string[] = []
let follow: Follow | null = null
let poll: Timer | null = null
let pending: Timer | null = null
let passing = false
let again = false
let stateDir: string | null = null
let seen = -1
/** The PRs whose agent this module started and has not seen end. */
const started = new Set<number>()
/** A PR whose agent ended a turn without a report → when that turn ended. */
const lastTurn = new Map<number, number>()
/** A blocked report holds its PR while the head it was written at is still the head. */
const blockedAt = new Map<number, string>()
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

  blockedAt.delete(r.number)
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

function parsed(stdout: string): Scan | null {
  try {
    return JSON.parse(stdout) as Scan
  } catch {
    return null
  }
}

async function passOnce($: Engine) {
  const run = await shell($, ['python3', `${$.plugin.root}${SCAN}`, ...args])
  const scan = run.exitCode === 0 ? parsed(run.stdout) : null

  if (scan === null) {
    await tell($, 'scan', true, `babysit: pr-scan failed: ${(run.stderr.trim() || run.stdout.trim()).slice(0, 200)}`)

    return
  }

  told.delete('scan')
  stateDir = scan.state_dir
  const due: Row[] = []

  for (const r of scan.prs) {
    const blocked = r.report?.blocked

    if (!blocked) {
      blockedAt.delete(r.number)
    } else if (!blockedAt.has(r.number)) {
      blockedAt.set(r.number, r.head)
    }

    const isDue = r.needs_agent && r.waits_on === null && !r.agent_running && blockedAt.get(r.number) !== r.head
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
    const slots = MAX_AGENTS - scan.prs.filter(r => r.agent_running).length

    for (const r of due.slice(0, Math.max(0, slots))) {
      await spawnFor($, r, scan.state_dir)
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
  pending?.cancel()
  poll = null
  pending = null
  void stream?.return({ code: null, signal: null })
  await status($)
}

/** pr-scan's watch: it holds babysit.lock and keeps the scan service alive; each line is a transition. */
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

  if (next === 'on') {
    const stream = $.process.spawn({ argv: ['python3', `${$.plugin.root}${SCAN}`, '--follow', ...selection] })
    follow = stream
    void watch($, stream)
    await pass($)
  } else {
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
          ? 'babysit dry: says which PR would get an agent, starts none. /babysit stop to end'
          : 'babysit on: one Opus agent per PR that needs one, no manager in this conversation. /babysit stop to end',
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

import type { On, TurnCompleteInput } from 'claude-code'
import { describe, expect, test } from 'claude-code/testing'

import { SESSION, command, stateOf, stateRow, world } from './fixtures'

const DIR = '/state/naboo'
const WATCH = new URL('../skills/babysit-prs/scripts/watch.sh', import.meta.url).pathname

/** The shared agent prompt, as references/agent-prompt.md frames it. */
const PROMPT = `# PR agent prompt

How to fill it.

---

Own PR #<n> on <head> onto \`<base>\` [stacked: (stacked on **PR #<parent>**)], report to <state_dir>/<n>.report.json.

---
`

/** A state.json row with one bot thread waiting and no agent on it. */
const row = (number: number, over: Record<string, unknown> = {}) =>
  stateRow(number, { status: 'bot', unresolved_bot: 1, threads_bot_open: 1, needs_agent: true, ...over })

type Row = ReturnType<typeof row>

/** A spawn as the engine beneath receives it: the Agent tool's input. */
type Spawn = { description: string; prompt: string; name?: string; model?: string; subagent_type?: string }

/**
 * The world beneath /shepherd: pr-dash on PATH with its state dir at DIR, state.json holding
 * `scan.prs` and `scan.error` (written at `scan.mtimeMs`), the watch fed line by line, files, the session's
 * agents (`agents`) and the status line kept.
 */
function engine(on: On, { deny = false, prompt = true, missing = false } = {}) {
  const scan = { prs: [] as Row[], mtimeMs: 1, error: null as { at: string; message: string } | null }
  const files = new Set<string>()
  const spawned: Spawn[] = []
  const agents: { id: string; description: string; type: string; status: string; spawnedBy?: string }[] = []
  const statuses: (string | undefined)[] = []
  const follow = { argv: [] as readonly string[], queue: [] as string[], wake: null as (() => void) | null, ended: false }

  on('agent.spawn', ($, e) => {
    spawned.push({ ...(e as unknown as Spawn) })

    return deny ? { deny: 'agents are off' } : { model: 'opus' }
  })
  on('agent.list', () => ({
    value: agents,
  }))

  const w = world(on, {
    run: argv => {
      if (argv[0] === 'pr-dash') {
        if (missing) {
          throw new Error('spawn pr-dash ENOENT')
        }

        return argv[1] === 'state-dir' ? { stdout: `${DIR}/\n` } : {}
      }
      if (argv[0] === 'rm') {
        files.delete(argv[2] ?? '')

        return {}
      }

      return { stderr: `unexpected ${argv.join(' ')}` }
    },
  })

  on('fs.read', ($, e) => {
    if (e.path === `${DIR}/state.json`) {
      // As the Scan service writes it: a mute file on disk is an agent alive on that PR.
      return {
        value: stateOf(
          scan.prs.map(r => ({ ...r, agent_running: r.agent_running || files.has(`${DIR}/${r.number}.muted`) })),
          { error: scan.error },
        ),
      }
    }
    if (!prompt) {
      throw new Error(`ENOENT: ${e.path}`)
    }

    return { value: e.path.endsWith('/skills/babysit-prs/references/agent-prompt.md') ? PROMPT : '' }
  })
  on('fs.write', ($, e) => {
    files.add(e.path)

    return { value: undefined }
  })
  on('fs.exists', ($, e) => ({ value: files.has(e.path) }))
  on('fs.stat', () => ({ value: { kind: 'file' as const, size: 1, mtimeMs: scan.mtimeMs, isLink: false } }))
  on('ui.status', ($, e) => {
    statuses.push(e.text)

    return { value: undefined }
  })
  on('turn.complete', ($, e) => ({ text: e.answer }))
  on('process.spawn', async function* ($, e) {
    follow.argv = e.argv
    try {
      while (true) {
        while (follow.queue.length === 0) {
          await new Promise<void>(resolve => {
            follow.wake = resolve
          })
        }
        yield { stream: 'stdout' as const, text: `${follow.queue.shift()}\n` }
      }
    } finally {
      follow.ended = true
    }
  })

  /** The watch prints an events.log line; the pass it sets off runs after the debounce. */
  const emit = async (line: string) => {
    follow.queue.push(line)
    follow.wake?.()
    await w.clock.advance(2_000)
  }

  return { ...w, scan, files, spawned, agents, statuses, follow, emit }
}

const babysit = (args = '') => ({ ...command('shepherd'), args })

/** The final turn of an unnamed agent. */
const finished = (id: string): TurnCompleteInput => ({
  answer: 'report written',
  durationMs: 10,
  isAborted: false,
  turnId: 't',
  reason: 'answer',
  agentId: id,
})

describe('babysit', () => {
  test('a PR with bot feedback gets its mute, then one Opus agent with the shared prompt filled', async ($, on) => {
    const w = engine(on)
    w.scan.prs = [row(12, { parent: 11, head: 'bbbbbbb' }), row(13, { needs_agent: false })]
    await $.session.start(SESSION)

    expect(await $.command.run(babysit())).toMatchObject({ text: expect.stringContaining('babysit on') })
    await w.clock.settle()

    expect(w.follow.argv, 'the lock wrapper around pr-dash follow, every PR').toEqual([WATCH])
    expect(w.runs.slice(0, 2), 'a pass reads the State a fresh wake wrote').toEqual([
      ['pr-dash', 'state-dir'],
      ['pr-dash', 'wake', '--wait'],
    ])
    expect(w.files.has(`${DIR}/12.muted`)).toBe(true)
    expect(w.spawned).toHaveLength(1)
    expect(w.spawned[0]).toMatchObject({ subagent_type: 'general-purpose', model: 'opus', description: 'Own PR #12' })
    expect(w.spawned[0]?.name, 'an unnamed agent finishes quietly; a named one idles as a teammate').toBeUndefined()
    expect(w.spawned[0]?.prompt).toBe(
      `Own PR #12 on feat/12 onto \`dev\` (stacked on **PR #11**), report to ${DIR}/12.report.json.`,
    )
    expect(w.statuses.at(-1)).toBe('babysit · 1 agent')
  })

  test('a PR at the bottom of a stack has no stacked clause; one waiting on its stack or with a live agent gets none', async ($, on) => {
    const w = engine(on)
    w.scan.prs = [row(20), row(21, { parent: 20, waits_on: 20 }), row(30, { agent_running: true })]
    await $.session.start(SESSION)

    await $.command.run(babysit())
    await w.clock.settle()

    expect(w.spawned.map(s => s.description)).toEqual(['Own PR #20'])
    expect(w.spawned[0]?.prompt).toBe(`Own PR #20 on feat/20 onto \`dev\`, report to ${DIR}/20.report.json.`)

    // #20's agent pushed and reported, and the scan folded it: the next pass releases #21.
    w.files.delete(`${DIR}/20.muted`)
    w.scan.prs = [row(20, { needs_agent: false, head: 'ccccccc' }), row(21, { parent: 20 }), row(30, { agent_running: true })]
    await w.emit('#20 report: pushed 1, inflight 0, held 0, blocked -')

    expect(w.spawned.map(s => s.description)).toEqual(['Own PR #20', 'Own PR #21'])
  })

  test('a blocked report holds the PR until the scan lifts it', async ($, on) => {
    const w = engine(on)
    w.scan.prs = [row(40, { report: { blocked: 'OOM in jest' } })]
    await $.session.start(SESSION)

    await $.command.run(babysit())
    await w.clock.settle()
    await w.emit('#40 ci PENDING→FAILURE')
    expect(w.spawned, 'the same failure on the same head').toHaveLength(0)

    w.scan.prs = [row(40, { report: { blocked: null } })]
    await w.emit('#40 unresolved_bot 0→5')
    expect(w.spawned.map(s => s.description), 'new bot threads on the same head').toEqual(['Own PR #40'])
  })

  test('four agents at most at once: the rest wait for a slot', async ($, on) => {
    const w = engine(on)
    w.scan.prs = [1, 2, 3, 4, 5, 6].map(n => row(n))
    await $.session.start(SESSION)

    await $.command.run(babysit())
    await w.clock.settle()
    expect(w.spawned).toHaveLength(4)

    w.files.delete(`${DIR}/1.muted`)
    w.scan.prs = [row(1, { needs_agent: false }), ...[2, 3, 4].map(n => row(n)), row(5), row(6)]
    await w.emit('#1 report: pushed 1, inflight 0, held 0, blocked -')
    expect(w.spawned.map(s => s.description).slice(4)).toEqual(['Own PR #5'])
  })

  test('dry mode says what it would spawn, once per PR, and touches nothing', async ($, on) => {
    const w = engine(on)
    w.scan.prs = [row(50)]
    await $.session.start(SESSION)

    expect(await $.command.run(babysit('dry'))).toMatchObject({ text: expect.stringContaining('babysit dry') })
    await w.clock.settle()
    w.scan.mtimeMs = 2
    await w.clock.advance(5_000)

    expect(w.toasts.filter(t => t.includes('would spawn an agent on #50'))).toHaveLength(1)

    w.scan.prs = [row(50), row(51)]
    w.scan.mtimeMs = 3
    await w.clock.advance(5_000)
    expect(w.toasts.filter(t => t.includes('would spawn')), 'state.json moved: one more pass').toEqual([
      'babysit dry: would spawn an agent on #50',
      'babysit dry: would spawn an agent on #51',
    ])

    await w.clock.advance(5 * 60_000)
    expect(w.spawned).toHaveLength(0)
    expect(w.files.size).toBe(0)
    expect(w.follow.argv, 'dry runs beside a manager: it never takes the watch lock').toEqual([])
    expect(w.runs.filter(r => r[1] === 'wake'), 'dry never asks for a pass').toHaveLength(0)
    expect(w.runs.filter(r => r[1] === 'ensure'), 'on start, then every 5 min').toHaveLength(2)
  })

  test('another manager holding the watch: a toast, no agent', async ($, on) => {
    const w = engine(on)
    await $.session.start(SESSION)

    await $.command.run(babysit())
    await w.clock.settle()
    w.scan.prs = [row(60)]
    await w.emit('babysit-prs already active (pid 4242)')

    expect(w.toasts.some(t => t.includes('already babysitting'))).toBe(true)
    expect(w.spawned).toHaveLength(0)
    expect(w.statuses.at(-1)).toBeUndefined()
  })

  test('a missing agent prompt starts nothing and leaves no mute behind', async ($, on) => {
    const w = engine(on, { prompt: false })
    w.scan.prs = [row(75)]
    await $.session.start(SESSION)

    await $.command.run(babysit())
    await w.clock.settle()

    expect(w.spawned).toHaveLength(0)
    expect(w.files.size).toBe(0)
    expect(w.toasts.some(t => t.includes('the pass failed'))).toBe(true)
  })

  test('a refused spawn lifts its mute and says why', async ($, on) => {
    const refused = engine(on, { deny: true })
    refused.scan.prs = [row(70)]
    await $.session.start(SESSION)

    await $.command.run(babysit())
    await refused.clock.settle()

    expect(refused.files.has(`${DIR}/70.muted`)).toBe(false)
    expect(refused.toasts.some(t => t.includes('#70') && t.includes('agents are off'))).toBe(true)
  })

  test('an agent that reported is done; one that did not loses its mute after the grace, unless it takes another turn', async ($, on) => {
    const w = engine(on)
    w.scan.prs = [row(80), row(81), row(83)]
    await $.session.start(SESSION)

    await $.command.run(babysit())
    await w.clock.settle()
    expect(w.statuses.at(-1)).toBe('babysit · 3 agents')

    // As agent.list shows them once their turn ended; a model-spawned agent naming #80 is not ours.
    const ours = (n: number) => ({ id: `a${n}`, description: `Own PR #${n}`, type: 'general-purpose', status: 'completed', spawnedBy: 'ai-skills' })
    w.agents.push(ours(80), ours(81), ours(83), { id: 'a99', description: 'Own PR #80', type: 'general-purpose', status: 'running' })
    w.files.add(`${DIR}/81.report.json`)

    await $.turn.complete(finished('a80'))
    await $.turn.complete(finished('a81'))
    await $.turn.complete(finished('a83'))
    expect(w.statuses.at(-1), '#81 reported').toBe('babysit · 2 agents')
    expect(w.files.has(`${DIR}/80.muted`), 'a background command may still be running').toBe(true)

    // #83's background command finished: its agent takes one more turn, then reports.
    await w.clock.advance(5 * 60_000)
    await $.turn.complete(finished('a83'))
    await w.clock.advance(5 * 60_000)

    expect(w.files.has(`${DIR}/80.muted`), 'no report and no other turn: it would hold its stack an hour').toBe(false)
    expect(w.toasts.filter(t => t.includes('without a report'))).toEqual(['babysit: the agent on #80 ended without a report'])
    expect(w.files.has(`${DIR}/81.muted`), 'the scan folds the report and lifts it').toBe(true)
    expect(w.files.has(`${DIR}/83.muted`), 'its later turn restarted the grace').toBe(true)

    await w.clock.advance(5 * 60_000)
    expect(w.files.has(`${DIR}/83.muted`)).toBe(false)
    expect(w.statuses.at(-1)).toBe('babysit · 0 agents')
  })

  test('named PRs are the selection: merge-ready and held told once each, one not in the State skipped', async ($, on) => {
    const w = engine(on)
    w.scan.prs = [row(90, { needs_agent: false, merge_ready: true }), row(91, { needs_agent: false, held: 1 }), row(92)]
    await $.session.start(SESSION)

    await $.command.run(babysit('90 91 99'))
    await w.clock.settle()
    await w.emit('#90 ci PENDING→SUCCESS')

    expect(w.follow.argv).toEqual([WATCH, '90', '91', '99'])
    expect(w.spawned, '#92 is not selected').toHaveLength(0)
    expect(w.toasts.filter(t => t.includes('#99'))).toEqual(['babysit: #99 is not one of your open PRs; skipped'])
    expect(w.toasts.filter(t => t.includes('#90 is merge-ready'))).toHaveLength(1)
    expect(w.toasts.filter(t => t.includes('#91') && t.includes('/pr-explain 91'))).toHaveLength(1)

    expect(await $.command.run(babysit())).toMatchObject({ text: expect.stringContaining('babysit off') })
    await w.emit('#90 merge_state CLEAN→BEHIND')
    expect(w.follow.ended).toBe(true)
    expect(w.statuses.at(-1)).toBeUndefined()
  })

  test('a draft gets no agent unless --include-drafts', async ($, on) => {
    const w = engine(on)
    w.scan.prs = [row(95, { draft: true }), row(96)]
    await $.session.start(SESSION)

    await $.command.run(babysit())
    await w.clock.settle()
    expect(w.spawned.map(s => s.description)).toEqual(['Own PR #96'])
  })

  test('--include-drafts babysits a draft like any PR', async ($, on) => {
    const w = engine(on)
    w.scan.prs = [row(95, { draft: true })]
    await $.session.start(SESSION)

    await $.command.run(babysit('--include-drafts'))
    await w.clock.settle()
    expect(w.spawned.map(s => s.description)).toEqual(['Own PR #95'])
    expect(w.follow.argv, 'a flag of the selection, not of pr-dash follow').toEqual([WATCH])
  })

  test('a State with an error is told once and its last good rows still get their agent', async ($, on) => {
    const w = engine(on)
    w.scan.prs = [row(98)]
    w.scan.error = { at: '2026-10-24T10:02:00.000Z', message: 'API rate limit exceeded' }
    await $.session.start(SESSION)

    await $.command.run(babysit())
    await w.clock.settle()
    await w.emit('scan error: API rate limit exceeded')
    expect(w.toasts.filter(t => t.includes('rate limit'))).toEqual(['babysit: pr-dash: API rate limit exceeded'])
    expect(w.spawned.map(s => s.description)).toEqual(['Own PR #98'])
  })

  test('a missing pr-dash stops with the install line', async ($, on) => {
    const w = engine(on, { missing: true })
    w.scan.prs = [row(97)]
    await $.session.start(SESSION)

    await $.command.run(babysit())
    await w.clock.settle()
    expect(w.toasts).toContain('babysit: pr-dash not found: npm i -g github:BenjaminG/pr-dash')
    expect(w.spawned).toHaveLength(0)
    expect(w.statuses.at(-1)).toBeUndefined()
  })

  test('arguments other than dry, stop, PR numbers and --include-drafts are refused', async ($, on) => {
    const w = engine(on)
    await $.session.start(SESSION)

    expect(await $.command.run(babysit('12; rm -rf /'))).toMatchObject({ text: expect.stringContaining('Usage') })
    expect(w.runs).toHaveLength(0)
  })
})

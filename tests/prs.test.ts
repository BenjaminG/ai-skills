import { describe, expect, test } from 'claude-code/testing'

import { PLUGIN, SESSION, command, pane, textOf, world } from './fixtures'

const TABLE = `pr-dash · naboo-team/naboo · updated 15:21:11
│ S1 ╭ HEAD   │ #16579 map a re-invoicing extraction onto a quote │ ⏳ WAITS #16578 │
│ S1 ╰ BASE   │ #16578 let a client read their own post-stay      │ ✅ READY        │`
const DASH = JSON.stringify({
  state: '/home/.claude/pr-state/naboo-team_naboo/state.json',
  text: TABLE,
  prs: [
    { number: 42, title: 'the thing', url: 'u42', ci: 'SUCCESS', status: '✅ READY' },
    { number: 7, title: 'another', url: 'u7', ci: 'PENDING', status: '📝 DRAFT' },
    { number: 3, title: 'broken', url: 'u3', ci: 'FAILURE', status: '🤖 BOT 2' },
  ],
})
const PR_DASH = ['python3', 'status', '--json']

describe('prs', () => {
  test('/prs opens the pane, lists my PRs, a press fills /pr-feedback', async ($, on) => {
    const w = world(on, { python3: { stdout: DASH } })

    await $.session.start(SESSION)

    expect(await $.command.run(command('prs'))).toEqual({ text: 'PRs panel shown' })
    await w.clock.settle()

    expect(w.opened).toEqual(['prs'])
    expect(w.runs.map(r => [r[0], ...r.slice(2)])).toEqual([PR_DASH])
    expect(w.runs[0]?.[1], 'the script next to hooks/, in this plugin').toBe(
      new URL('../skills/pr-dash/scripts/pr-dash.py', import.meta.url).pathname,
    )

    const drawn = textOf(await $.ui.render(pane('prs')))

    expect(drawn).toContain('PRs · 3')
    expect(drawn).toContain('✓#42 the thing✅ READY')
    expect(drawn).toContain('◐#7 another📝 DRAFT')
    expect(drawn).toContain('✗#3 broken🤖 BOT 2')

    expect(await $.ui.press({ plugin: PLUGIN, key: 'pr:42' })).toEqual({ element: 'pr:42' })
    expect(w.filled).toEqual(['/pr-feedback 42'])

    expect(await $.command.run(command('prs'))).toEqual({ text: 'PRs panel hidden' })
    expect(w.closed).toEqual(['prs'])
  })

  test('pr-dash reruns when the state moves, once a minute regardless, never once closed', async ($, on) => {
    const w = world(on, { python3: { stdout: DASH } })

    await $.session.start(SESSION)
    await $.command.run(command('prs'))
    await w.clock.settle()
    expect(w.runs).toHaveLength(1)

    await w.clock.advance(15_000)
    expect(w.runs, 'an unchanged state costs a stat, not a run').toHaveLength(1)

    w.files.mtimeMs = 2
    await w.clock.advance(5_000)
    await w.clock.settle()
    expect(w.runs, 'the service wrote: redraw').toHaveLength(2)

    await w.clock.advance(60_000)
    await w.clock.settle()
    expect(w.runs, 'a quiet minute still runs pr-dash, which keeps the service alive').toHaveLength(3)

    await $.command.run(command('prs'))
    await w.clock.advance(120_000)
    expect(w.runs, 'closed: no more runs').toHaveLength(3)
  })

  test('the toggle draws pr-dash\'s table from the same run, then the rows again', async ($, on) => {
    const w = world(on, { python3: { stdout: DASH } })

    await $.session.start(SESSION)
    await $.command.run(command('prs'))
    await w.clock.settle()

    expect(textOf(await $.ui.render(pane('prs')))).toContain('PRs · 3')
    expect(await $.ui.press({ plugin: PLUGIN, key: 'prs:view' })).toEqual({ element: 'prs:view' })
    expect(textOf(await $.ui.render(pane('prs')))).toContain('S1 ╭ HEAD   │ #16579')
    expect(w.runs, 'no second run: both views read one').toHaveLength(1)

    await $.ui.press({ plugin: PLUGIN, key: 'prs:view' })
    expect(textOf(await $.ui.render(pane('prs'))), 'back to the rows').toContain('#42 the thing')
  })

  test('a failing pr-dash shows its error, and the next tick retries', async ($, on) => {
    const w = world(on, {
      python3: { exitCode: 1, stderr: 'pr-dash: cannot resolve the GitHub repository; run from its checkout' },
    })

    await $.session.start(SESSION)
    await $.command.run(command('prs'))
    await w.clock.settle()

    expect(textOf(await $.ui.render(pane('prs')))).toContain('cannot resolve the GitHub repository')

    await w.clock.advance(5_000)
    await w.clock.settle()
    expect(w.runs, 'an error is not a state to wait on').toHaveLength(2)
  })
})

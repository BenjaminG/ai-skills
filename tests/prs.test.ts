import { describe, expect, test } from 'claude-code/testing'

import { PLUGIN, SESSION, command, pane, textOf, world } from './fixtures'

const DASH = `  Stack     PR                                                                        Issue
  S1 ╭ BASE #16578 let a client read, extract and cancel their own post-stay  BOF-1112   ✅ READY   ·  ✅ PASS   ✅ CLEAN
  S1 ╰ HEAD #16579 map a re-invoicing extraction onto a quote and decide each BOF-1113   ⏳ WAITS   ·  ⏳ RUN    ↩ BEHIND
  ◆ SINGLE #17212 drop declines from the Confirmed badge                      BOF-1208   ✅ READY   ·  ✅ PASS   ✅ CLEAN
`
const GH = JSON.stringify([
  {
    number: 42,
    title: 'fix: the thing',
    isDraft: false,
    reviewDecision: 'APPROVED',
    statusCheckRollup: [{ conclusion: 'SUCCESS', status: 'COMPLETED' }],
  },
  {
    number: 7,
    title: 'feat: another',
    isDraft: true,
    reviewDecision: '',
    statusCheckRollup: [
      { conclusion: 'SUCCESS', status: 'COMPLETED' },
      { conclusion: null, status: 'IN_PROGRESS' },
    ],
  },
  {
    number: 3,
    title: 'chore: broken',
    isDraft: false,
    reviewDecision: 'CHANGES_REQUESTED',
    statusCheckRollup: [{ state: 'FAILURE' }],
  },
])

describe('prs', () => {
  test('/prs opens the pane, lists my PRs, a press fills /pr-feedback', async ($, on) => {
    const w = world(on, { stdout: GH })

    await $.session.start(SESSION)

    expect(await $.command.run(command('prs'))).toEqual({ text: 'PRs panel shown' })
    await w.clock.settle()

    expect(w.opened).toEqual(['prs'])
    expect(w.runs).toEqual([
      ['gh', 'pr', 'list', '--author', '@me', '--json', 'number,title,headRefName,isDraft,reviewDecision,statusCheckRollup,url'],
    ])

    const drawn = textOf(await $.ui.render(pane('prs')))

    expect(drawn).toContain('PRs · 3')
    expect(drawn).toContain('✓#42 fix: the thingapproved')
    expect(drawn).toContain('◐#7 feat: anotherdraft')
    expect(drawn).toContain('✗#3 chore: brokenchanges')

    expect(await $.ui.press({ plugin: PLUGIN, key: 'pr:42' })).toEqual({ element: 'pr:42' })
    expect(w.filled).toEqual(['/pr-feedback 42'])

    expect(await $.command.run(command('prs'))).toEqual({ text: 'PRs panel hidden' })
    expect(w.closed).toEqual(['prs'])
  })

  test('the pane polls gh every minute while open, and stops once closed', async ($, on) => {
    const w = world(on, { stdout: GH })

    await $.session.start(SESSION)
    await $.command.run(command('prs'))
    await w.clock.settle()

    expect(w.runs).toHaveLength(1)

    await w.clock.advance(60_000)
    expect(w.runs).toHaveLength(2)

    await $.command.run(command('prs'))
    await w.clock.advance(120_000)
    expect(w.runs, 'closed: no more polls').toHaveLength(2)
  })

  test('the toggle draws pr-dash\'s snapshot, then the compact rows again', async ($, on) => {
    const w = world(on, { stdout: GH, python3: { stdout: DASH } })

    await $.session.start(SESSION)
    await $.command.run(command('prs'))
    await w.clock.settle()

    expect(textOf(await $.ui.render(pane('prs')))).toContain('PRs · 3')
    expect(await $.ui.press({ plugin: PLUGIN, key: 'prs:view' })).toEqual({ element: 'prs:view' })
    await w.clock.settle()

    expect(w.runs.some(r => r[0] === 'python3' && r[1]?.includes('pr-dash.py')), 'pr-dash runs read-only').toBe(true)
    expect(textOf(await $.ui.render(pane('prs')))).toContain('S1 ╭ BASE #16578')

    await $.ui.press({ plugin: PLUGIN, key: 'prs:view' })
    expect(textOf(await $.ui.render(pane('prs'))), 'back to the rows').toContain('#42 fix: the thing')
  })

  test('a failing pr-dash shows its error in the detailed view', async ($, on) => {
    const w = world(on, {
      stdout: GH,
      python3: { exitCode: 1, stderr: 'no babysit state; start babysit-prs first' },
    })

    await $.session.start(SESSION)
    await $.command.run(command('prs'))
    await w.clock.settle()
    expect(textOf(await $.ui.render(pane('prs')))).toContain('PRs · 3')
    await $.ui.press({ plugin: PLUGIN, key: 'prs:view' })
    await w.clock.settle()

    expect(textOf(await $.ui.render(pane('prs')))).toContain('no babysit state; start babysit-prs first')
  })

  test('a failing gh shows its error in the pane', async ($, on) => {
    const w = world(on, { stderr: 'gh: not logged in' })

    await $.session.start(SESSION)
    await $.command.run(command('prs'))
    await w.clock.settle()

    expect(textOf(await $.ui.render(pane('prs')))).toContain('gh: not logged in')
  })
})

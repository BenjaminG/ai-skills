import type { On } from 'claude-code'
import { describe, expect, mock, test } from 'claude-code/testing'

import { SESSION, command, pane, textOf, world } from './fixtures'

/** The engine beneath: a skill's text read back as computed, this plugin's skills/ listing three skills. */
function engine(on: On) {
  on('skill.prompt', ($, e) => ({ text: e.text }))
  on('fs.list', () => ({
    value: ['gate-wf', 'commit', 'pr-demo'].map(name => ({ name, kind: 'dir' as const, size: 0, mtimeMs: 0, isLink: false })),
  }))
}

describe('skill-xray', () => {
  test('/xray lists the skills that ran with their cost, and the plugin skills that never did', async ($, on) => {
    const w = world(on, {})
    mock.store(on)
    engine(on)
    await $.session.start(SESSION)

    expect(await $.skill.prompt({ skill: 'ai-skills:gate-wf', text: 'x'.repeat(4000) })).toEqual({ text: 'x'.repeat(4000) })
    await $.skill.prompt({ skill: 'ai-skills:gate-wf', text: 'x'.repeat(8000) })
    await $.skill.prompt({ skill: 'commit', text: 'x'.repeat(400) })

    expect(await $.command.run(command('xray'))).toEqual({ text: 'Skill X-ray panel shown' })
    await w.clock.settle()
    expect(w.opened).toEqual(['xray'])

    const drawn = textOf(await $.ui.render(pane('xray')))

    expect(drawn).toContain('Skills · 2 used since 1970-01-01')
    expect(drawn).toMatch(/ai-skills:gate-wf\s+×2\s+~1500 tok\/run\s+~3000 total\s+1970-01-01/)
    expect(drawn).toMatch(/commit\s+×1\s+~100 tok\/run\s+~100 total/)
    expect(drawn.indexOf('gate-wf'), 'the most used first').toBeLessThan(drawn.indexOf('commit'))
    expect(drawn).toContain('Never used: pr-demo')

    expect(await $.command.run(command('xray'))).toEqual({ text: 'Skill X-ray panel hidden' })
  })

  test('the counts outlive the session', async ($, on) => {
    const w = world(on, {})
    mock.store(on, {
      'skill-xray': { since: '2026-09-01', skills: { 'pr-demo': { count: 4, tokens: 2000, last: '2026-09-20' } } },
    })
    engine(on)
    await $.session.start(SESSION)

    await $.skill.prompt({ skill: 'pr-demo', text: 'x'.repeat(2000) })
    await $.command.run(command('xray'))
    await w.clock.settle()

    const drawn = textOf(await $.ui.render(pane('xray')))

    expect(drawn).toContain('used since 2026-09-01')
    expect(drawn).toMatch(/pr-demo\s+×5\s+~500 tok\/run\s+~2500 total\s+1970-01-01/)
    expect(drawn).toContain('Never used: gate-wf, commit')
  })

  test("the open pane follows each run; another plugin's skill of a shipped name is not that skill", async ($, on) => {
    const w = world(on, {})
    mock.store(on)
    engine(on)
    await $.session.start(SESSION)

    await $.skill.prompt({ skill: 'other:commit', text: 'x' })
    await $.command.run(command('xray'))
    await w.clock.settle()
    expect(textOf(await $.ui.render(pane('xray')))).toContain('Never used: gate-wf, commit, pr-demo')

    await $.skill.prompt({ skill: 'ai-skills:pr-demo', text: 'x' })
    await w.clock.settle()
    expect(textOf(await $.ui.render(pane('xray')))).toContain('Never used: gate-wf, commit/xray to close')
  })
})

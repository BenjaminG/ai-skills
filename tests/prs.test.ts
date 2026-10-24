import type { On } from 'claude-code'
import { describe, expect, test } from 'claude-code/testing'

import { PLUGIN, SESSION, command, pane, stateOf, stateRow, textOf, world } from './fixtures'

const STATE = '/state/o_n/state.json'
const PRS = [
  stateRow(42, { title: 'the thing', status: 'ready', merge_ready: true, merge_state: 'CLEAN' }),
  stateRow(7, { title: 'a draft', draft: true, status: 'draft', ci: 'PENDING' }),
  stateRow(3, { title: 'broken', status: 'bot', ci: 'FAILURE', unresolved_bot: 2, needs_agent: true }),
]

/** The world beneath /prs: pr-dash on PATH (unless `missing`), state.json holding `file.text` once written. */
function dash(on: On, { missing = false } = {}) {
  const file = { text: stateOf(PRS) as string | null }
  const w = world(on, {
    run: argv => {
      if (missing) {
        throw new Error('spawn pr-dash ENOENT')
      }

      return argv[1] === 'state-dir' ? { stdout: '/state/o_n/\n' } : {}
    },
  })

  on('fs.read', ($, e) => {
    if (e.path !== STATE || file.text === null) {
      throw new Error(`ENOENT: ${e.path}`)
    }

    return { value: file.text }
  })

  return { ...w, file }
}

describe('prs', () => {
  test('/prs lists my open PRs without the drafts, a press fills /pr-feedback', async ($, on) => {
    const w = dash(on)

    await $.session.start(SESSION)
    expect(await $.command.run(command('prs'))).toEqual({ text: 'PRs panel shown' })
    await w.clock.settle()

    expect(w.opened).toEqual(['prs'])
    expect(w.runs).toEqual([
      ['pr-dash', 'state-dir'],
      ['pr-dash', 'ensure'],
    ])

    const drawn = textOf(await $.ui.render(pane('prs')))

    expect(drawn).toContain('PRs · 2')
    expect(drawn).toContain('✓#42 the thingready')
    expect(drawn).toContain('✗#3 brokenbot')
    expect(drawn).not.toContain('a draft')
    expect(drawn).not.toContain('pr-scan')

    expect(await $.ui.press({ plugin: PLUGIN, key: 'pr:42' })).toEqual({ element: 'pr:42' })
    expect(w.filled).toEqual(['/pr-feedback 42'])

    expect(await $.command.run(command('prs'))).toEqual({ text: 'PRs panel hidden' })
    expect(w.closed).toEqual(['prs'])
  })

  test('a new taken_at redraws, the same one does not; ensure every 5 min; nothing once closed', async ($, on) => {
    const w = dash(on)

    await $.session.start(SESSION)
    await $.command.run(command('prs'))
    await w.clock.settle()

    w.file.text = stateOf([stateRow(42, { title: 'renamed' })])
    await w.clock.advance(10_000)
    expect(textOf(await $.ui.render(pane('prs'))), 'same pass: the drawn rows stand').toContain('the thing')

    w.file.text = stateOf([stateRow(42, { title: 'renamed' })], { taken_at: '2026-10-24T10:01:00.000Z' })
    await w.clock.advance(5_000)
    expect(textOf(await $.ui.render(pane('prs')))).toContain('#42 renamed')

    await w.clock.advance(5 * 60_000)
    expect(w.runs.filter(r => r[1] === 'ensure'), 'a Reader keeps the service alive').toHaveLength(2)
    expect(w.runs.filter(r => r[1] === 'state-dir'), 'the dir is asked once').toHaveLength(1)

    await $.command.run(command('prs'))
    const before = w.runs.length
    await w.clock.advance(10 * 60_000)
    expect(w.runs, 'closed: no more ensure').toHaveLength(before)
  })

  test('a State with an error shows it over the last good rows; another schema says outdated', async ($, on) => {
    const w = dash(on)
    w.file.text = stateOf(PRS, { error: { at: '2026-10-24T10:02:00.000Z', message: 'API rate limit exceeded' } })

    await $.session.start(SESSION)
    await $.command.run(command('prs'))
    await w.clock.settle()

    const drawn = textOf(await $.ui.render(pane('prs')))
    expect(drawn).toContain('API rate limit exceeded')
    expect(drawn).toContain('#42 the thing')

    w.file.text = stateOf(PRS, { schema_version: 5, taken_at: '2026-10-24T10:03:00.000Z' })
    await w.clock.advance(5_000)
    expect(textOf(await $.ui.render(pane('prs')))).toContain('outdated')
  })

  test('no State yet reads Loading until the first pass writes one', async ($, on) => {
    const w = dash(on)
    w.file.text = null

    await $.session.start(SESSION)
    await $.command.run(command('prs'))
    await w.clock.settle()
    expect(textOf(await $.ui.render(pane('prs')))).toContain('Loading')

    w.file.text = stateOf(PRS)
    await w.clock.advance(5_000)
    expect(textOf(await $.ui.render(pane('prs')))).toContain('#42 the thing')
  })

  test('a missing pr-dash says how to install it', async ($, on) => {
    const w = dash(on, { missing: true })

    await $.session.start(SESSION)
    await $.command.run(command('prs'))
    await w.clock.settle()

    expect(textOf(await $.ui.render(pane('prs')))).toContain('npm i -g github:BenjaminG/pr-dash')
  })
})

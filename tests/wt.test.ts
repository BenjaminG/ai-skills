import { describe, expect, test } from 'claude-code/testing'

import { PLUGIN, SESSION, command, pane, textOf, world } from './fixtures'

const CLEAN = { staged: false, modified: false, untracked: false, diff: { added: 0, deleted: 0 } }

const WT = JSON.stringify([
  { branch: 'main', path: '/work', is_current: true, working_tree: { ...CLEAN, untracked: true }, remote: { ahead: 0, behind: 0 } },
  {
    branch: 'feat/pane',
    path: '/work.feat-pane',
    is_current: false,
    working_tree: { ...CLEAN, modified: true, diff: { added: 12, deleted: 3 } },
    remote: { ahead: 1, behind: 0 },
  },
])

describe('wt', () => {
  test('/wt opens the pane, lists worktrees, a press enters one', async ($, on) => {
    const w = world(on, { stdout: WT })

    await $.session.start(SESSION)

    expect(await $.command.run(command('wt'))).toEqual({ text: 'Worktrees panel shown' })
    await w.clock.settle()

    expect(w.opened).toEqual(['wt'])
    expect(w.runs).toEqual([['wt', 'list', '--format', 'json', '--config-set', 'list.json-schema=1']])

    const drawn = textOf(await $.ui.render(pane('wt')))

    expect(drawn).toContain('Worktrees · 2')
    expect(drawn).toContain('❯main?/work')
    expect(drawn).toContain(' feat/pane+12 −3 * ↑1/work.feat-pane')

    expect(await $.ui.press({ plugin: PLUGIN, key: 'wt:feat/pane' })).toEqual({ element: 'wt:feat/pane' })
    await w.clock.settle()

    expect(w.toolCalls).toEqual([
      expect.objectContaining({ tool: 'EnterWorktree', path: '/work.feat-pane' }),
    ])
    expect(w.toasts).toEqual(['→ feat/pane'])
    expect(w.runs, 'the switch refreshes the list').toHaveLength(2)

    expect(await $.command.run(command('wt'))).toEqual({ text: 'Worktrees panel hidden' })
    expect(w.closed).toEqual(['wt'])
  })

  test('a failing wt shows its error in the pane', async ($, on) => {
    const w = world(on, { stderr: 'wt: not a git repository' })

    await $.session.start(SESSION)
    await $.command.run(command('wt'))
    await w.clock.settle()

    expect(textOf(await $.ui.render(pane('wt')))).toContain('wt: not a git repository')
  })
})

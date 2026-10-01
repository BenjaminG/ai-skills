import type { On, TurnCompleteInput } from 'claude-code'
import { type Engine, describe, expect, test } from 'claude-code/testing'

import { SESSION, world } from './fixtures'

const TURN: TurnCompleteInput = { answer: 'done', durationMs: 10, isAborted: false, turnId: 't1', reason: 'answer' }

/** git and gh as a branch sees them; `pr` says whether it has a pull request, or that gh itself failed. */
const repo = (branch: string, pr: boolean | 'offline') => (argv: readonly string[]) => {
  const command = argv.join(' ')

  if (command === 'git branch --show-current') return { stdout: `${branch}\n` }
  if (command === 'git rev-parse --abbrev-ref origin/HEAD') return { stdout: 'origin/main\n' }
  if (command.startsWith('gh pr view')) {
    if (pr === 'offline') return { stderr: 'error connecting to api.github.com' }

    return pr ? { stdout: '{"number":12}' } : { stderr: 'no pull requests found for branch "feat/x"' }
  }

  return { stderr: `unexpected ${command}` }
}

function engine(on: On) {
  on('turn.complete', ($, e) => ({ text: e.answer }))
  on('prompt.submit', ($, e) => ({ text: e.text }))
}

/** The main conversation's model calling the Skill tool. */
const skill = ($: Engine, name: string) => $.tool.call({ tool: 'Skill', skill: name })

describe('next-step', () => {
  test('a gate-wf turn proposes /triage-findings, a pr-feedback turn /pr-respond', async ($, on) => {
    const w = world(on, {})
    engine(on)
    await $.session.start(SESSION)

    await skill($, 'ai-skills:gate-wf')
    await $.turn.complete(TURN)
    expect(w.suggested).toEqual(['/triage-findings blockers'])

    await skill($, 'pr-feedback')
    await $.turn.complete(TURN)
    expect(w.suggested).toEqual(['/triage-findings blockers', '/pr-respond'])

    await $.turn.complete(TURN)
    expect(w.suggested, 'a turn with no chained skill proposes nothing').toHaveLength(2)
  })

  test('a typed /pr-feedback counts like the Skill tool', async ($, on) => {
    const w = world(on, {})
    engine(on)
    await $.session.start(SESSION)

    await $.prompt.submit({ text: '/pr-feedback 42', wait: false, origin: { kind: 'composer' } })
    await $.turn.complete(TURN)
    expect(w.suggested).toEqual(['/pr-respond'])
  })

  test('an interrupted turn proposes nothing; a subagent skill or turn never reaches the main box', async ($, on) => {
    const w = world(on, {})
    engine(on)
    await $.session.start(SESSION)

    await skill($, 'gate-wf')
    await $.turn.complete({ ...TURN, isAborted: true, reason: 'aborted' })
    expect(w.suggested).toEqual([])

    // A subagent's call carries its loop's id, which the typed call input leaves out.
    await $.tool.call({ tool: 'Skill', skill: 'pr-feedback', agentId: 'a1' } as Parameters<Engine['tool']['call']>[0])
    await $.turn.complete({ ...TURN, agentId: 'a1' })
    await $.turn.complete(TURN)
    expect(w.suggested).toEqual([])
  })

  test('a skill outside the chain keeps the proposal; the proposed skill itself having run cancels it', async ($, on) => {
    const w = world(on, {})
    engine(on)
    await $.session.start(SESSION)

    await skill($, 'pr-feedback')
    await skill($, 'humanizer')
    await $.turn.complete(TURN)
    expect(w.suggested).toEqual(['/pr-respond'])

    await skill($, 'pr-feedback')
    await skill($, 'ai-skills:pr-respond')
    await $.turn.complete(TURN)
    expect(w.suggested, 'pr-feedback --auto already ran pr-respond').toEqual(['/pr-respond'])
  })

  test("another plugin's skill of the same name is not this chain", async ($, on) => {
    const w = world(on, {})
    engine(on)
    await $.session.start(SESSION)

    await skill($, 'other:gate-wf')
    await $.turn.complete(TURN)
    expect(w.suggested).toEqual([])
  })

  test('a commit proposes /pr-create on a branch with no pull request only', async ($, on) => {
    const answers: { branch: string; pr: boolean | 'offline' } = { branch: 'feat/x', pr: false }
    const w = world(on, { run: argv => repo(answers.branch, answers.pr)(argv) })
    engine(on)
    await $.session.start(SESSION)

    await skill($, 'commit')
    await $.turn.complete(TURN)
    expect(w.suggested).toEqual(['/pr-create'])

    for (const [branch, pr] of [['feat/x', true], ['feat/x', 'offline'], ['main', false]] as const) {
      answers.branch = branch
      answers.pr = pr
      await skill($, 'commit')
      await $.turn.complete(TURN)
    }

    expect(w.suggested, 'the branch has a PR, gh is offline, then the commit is on main').toEqual(['/pr-create'])
  })

  test("the engine's own guess after a chained turn shows the next skill instead", async ($, on) => {
    const w = world(on, {})
    engine(on)
    await $.session.start(SESSION)

    await skill($, 'gate-wf')
    await $.turn.complete(TURN)
    await $.prompt.suggest({ text: 'thanks!', origin: { kind: 'suggestion' } })
    expect(w.suggested).toEqual(['/triage-findings blockers', '/triage-findings blockers'])

    await $.turn.complete(TURN)
    await $.prompt.suggest({ text: 'thanks!', origin: { kind: 'suggestion' } })
    expect(w.suggested.at(-1), 'the next turn ran no chained skill').toBe('thanks!')
  })
})

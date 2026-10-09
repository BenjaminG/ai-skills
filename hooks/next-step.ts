import type { EngineInterface as Engine, Register } from 'claude-code'

/** A skill of this plugin a turn ran → the prompt that usually follows it, proposed dim in the empty box. */
const NEXT: Record<string, string> = {
  'gate-wf': '/triage-findings blockers',
  'pr-feedback': '/pr-respond',
  commit: '/pr-create',
}

// Module state, as in wt.tsx: a reload between a skill and its turn's end loses one proposal.
let chained: string | null = null
let proposal: string | null = null

/** The main conversation ran `skill` (`gate-wf`, `ai-skills:gate-wf`); another plugin's is not ours. */
function ran(skill: string) {
  const [plugin, name] = skill.includes(':') ? skill.split(':') : ['ai-skills', skill]

  if (plugin !== 'ai-skills' || name === undefined) {
    return
  }

  const proposed = chained === null ? undefined : NEXT[chained]?.slice(1).split(' ')[0]

  if (name in NEXT) {
    chained = name
  } else if (name === proposed) {
    // The proposed skill already ran this turn (pr-feedback --auto runs pr-respond).
    chained = null
  }
}

/** `git <args>`'s trimmed stdout, or null when it fails. Not shared: `$` never crosses an import. */
async function git($: Engine, args: readonly string[]): Promise<string | null> {
  const run = await $.process.run(['git', ...args]).catch(() => null)

  return run?.exitCode === 0 ? run.stdout.trim() : null
}

async function nextFor($: Engine, skill: string): Promise<string | null> {
  if (skill !== 'commit') {
    return NEXT[skill] ?? null
  }

  const branch = await git($, ['branch', '--show-current'])
  const base = (await git($, ['rev-parse', '--abbrev-ref', 'origin/HEAD']))?.replace(/^origin\//, '') ?? 'main'

  if (!branch || branch === base) {
    return null
  }

  // Only gh's own "no pull requests found" means none: offline or logged out proposes nothing.
  const pr = await $.process.run(['gh', 'pr', 'view', '--json', 'number']).catch(() => null)

  return pr?.stderr.includes('no pull requests found') ? (NEXT.commit ?? null) : null
}

export const register: Register = on => {
  // Skills are read where the main conversation starts them: the Skill tool (a subagent's
  // carries its `agentId`) and a typed `/name`. `skill.prompt` carries no loop id, and a
  // subagent's preloads fire it too.
  on('tool.call', { tool: 'Skill' }, async ($, e, next) => {
    if (e.agentId === undefined) {
      ran(e.skill)
    }

    return next(e)
  })

  on('prompt.submit', async ($, e, next) => {
    const typed = /^\/([\w:-]+)/.exec(e.text)?.[1]

    if (typed !== undefined) {
      ran(typed)
    }

    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const result = await next(e)

    if (e.agentId !== undefined) {
      return result
    }

    const skill = chained
    chained = null
    // Cleared before nextFor's git and gh calls, so a guess landing meanwhile keeps its own text.
    proposal = null

    if (skill !== null && e.reason === 'answer') {
      proposal = await nextFor($, skill)
    }

    if (proposal !== null) {
      void $.prompt.suggest({ text: proposal })
    }

    return result
  })

  // The engine's own guess may land after ours: the chain's next step shows instead.
  on('prompt.suggest', { origin: { kind: 'suggestion' } }, ($, e, next) =>
    next(proposal === null ? e : { ...e, text: proposal }),
  )
}

import type { EngineInterface as Engine, Register } from 'claude-code'

const COMMIT = /\bgit(?:\s+-[cC]\s+\S+)*\s+commit(?![\w-])/
const REWRITES = /--(?:fixup|squash|amend)\b/
const STAGES = /\bgit\s+add\b|\s-[a-zA-Z]*a[a-zA-Z]*(?=\s|$)|\s--all\b/
const NEW = 'New commit'

/** `git <args>`'s trimmed stdout, or null when it fails. next-step has its own: `$` never crosses an import. */
async function git($: Engine, args: readonly string[], cwd?: string): Promise<string | null> {
  const run = await $.process.run(['git', ...args], cwd === undefined ? undefined : { cwd }).catch(() => null)

  return run?.exitCode === 0 ? run.stdout.trim() : null
}

/** Old-side line ranges `[start, count]` per file a `git diff -U0` changes; a new file has none. */
function changedRanges(diff: string): Map<string, [number, number][]> {
  const ranges = new Map<string, [number, number][]>()
  let file: string | null = null

  for (const line of diff.split('\n')) {
    if (line.startsWith('--- ')) {
      file = line === '--- /dev/null' ? null : line.slice('--- a/'.length)
      continue
    }

    const hunk = /^@@ -(\d+)(?:,(\d+))? /.exec(line)
    const count = Number(hunk?.[2] ?? 1)

    if (file !== null && hunk !== null && count > 0) {
      ranges.set(file, [...(ranges.get(file) ?? []), [Number(hunk[1]), count]])
    }
  }

  return ranges
}

/** The branch's own commit that wrote most of the lines this change rewrites, or null. */
async function introducingCommit($: Engine, command: string, cwd?: string): Promise<{ sha: string; subject: string } | null> {
  const base = (await git($, ['rev-parse', '--abbrev-ref', 'origin/HEAD'], cwd)) ?? 'origin/main'
  const own = new Set((await git($, ['rev-list', `${base}..HEAD`], cwd))?.split('\n').filter(Boolean))

  if (own.size === 0) {
    return null
  }

  // A command that stages before it commits (`git add … && git commit`, `-a`) has not staged yet:
  // the tree is what it takes. ponytail: `git add <path>` reads as the whole tree, not that path.
  const scope = STAGES.test(command) ? 'HEAD' : '--cached'
  const diff = await git($, ['diff', scope, '-U0', '--no-color', '--no-ext-diff', '--src-prefix=a/', '--dst-prefix=b/'], cwd)
  const votes = new Map<string, number>()

  for (const [file, ranges] of changedRanges(diff ?? '')) {
    const lines = ranges.flatMap(([start, count]) => ['-L', `${start},+${count}`])
    const blame = await git($, ['blame', '-l', '-s', ...lines, 'HEAD', '--', file], cwd)

    for (const [, sha = ''] of (blame ?? '').matchAll(/^\^?([0-9a-f]{40}) /gm)) {
      if (own.has(sha)) {
        votes.set(sha, (votes.get(sha) ?? 0) + 1)
      }
    }
  }

  const [sha] = [...votes].sort((a, b) => b[1] - a[1])[0] ?? []

  return sha === undefined ? null : { sha, subject: (await git($, ['log', '-1', '--format=%s', sha], cwd)) ?? '' }
}

/** Asks before a plain commit whose lines belong to an earlier commit of the branch: fold it in (the fixup skill) or not. */
export const register: Register = on => {
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    // A subagent commits unattended (babysit-prs folds on its own): nobody to ask.
    if (e.agentId !== undefined || !COMMIT.test(e.command) || REWRITES.test(e.command)) {
      return next(e)
    }

    const target = await introducingCommit($, e.command, /\bgit\s+-C\s+(\S+)/.exec(e.command)?.[1])

    if (target === null) {
      return next(e)
    }

    const short = target.sha.slice(0, 7)
    const fixup = `Fixup into ${short}`
    // Dismissed, or headless with nobody to ask: the commit goes on as written.
    const answer = await $.ui
      .ask(`This change rewrites lines from ${short} "${target.subject}" on this branch. Fold it into that commit?`, {
        header: 'Fixup',
        options: [fixup, NEW],
      })
      .catch(() => NEW)

    if (answer === NEW) {
      return next(e)
    }

    return {
      deny:
        answer === fixup
          ? `The user chose to fold this change into ${target.sha} ("${target.subject}"). Commit it with \`git commit --fixup=${target.sha}\` in place of the plain commit, staging exactly as you meant to, then autosquash and push as the fixup skill says.`
          : `The user answered the fixup question instead of committing: ${answer}`,
    }
  })
}

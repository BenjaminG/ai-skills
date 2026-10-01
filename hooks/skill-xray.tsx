/* @jsxRuntime classic */
/* @jsx h */
/* @jsxFrag Fragment */
import type { EngineInterface as Engine, Register } from 'claude-code'

const ID = 'xray'
const KEY = 'skill-xray'

type Usage = { count: number; tokens: number; last: string }
type Ledger = { since: string; skills: Record<string, Usage> }

export const COMMAND = {
  name: ID,
  description: 'Skill X-ray: the skills that ran, with their prompt cost, and the ones of this plugin that never did',
} as const

// Module state, as in wt.tsx; the counts themselves live in $.store, across sessions.
let ledger: Ledger | null = null
let unused: string[] = []
let isOpen = false

const day = (ms: number) => new Date(ms).toISOString().slice(0, 10)

/** Counts one run of `skill`, `text` being what the model reads. */
async function record($: Engine, skill: string, text: string) {
  const today = day(await $.clock.now())
  const stored = ((await $.store.get(KEY)) as Ledger | undefined) ?? { since: today, skills: {} }
  const was = stored.skills[skill] ?? { count: 0, tokens: 0, last: today }
  // ponytail: ~4 characters a token; a real count once $ counts tokens
  const usage = { count: was.count + 1, tokens: was.tokens + Math.round(text.length / 4), last: today }

  ledger = { ...stored, skills: { ...stored.skills, [skill]: usage } }
  await $.store.set(KEY, ledger)

  if (isOpen) {
    await refresh($)
  }
}

async function refresh($: Engine) {
  ledger = ((await $.store.get(KEY)) as Ledger | undefined) ?? null

  // This plugin's skills, named bare or `ai-skills:`; another plugin's `other:commit` is not ours.
  const ours = `${$.plugin.name}:`
  const used = new Set(Object.keys(ledger?.skills ?? {}).map(name => (name.startsWith(ours) ? name.slice(ours.length) : name)))
  const shipped = await $.fs.list(`${$.plugin.root}/skills`).catch(() => [])

  unused = shipped.filter(f => f.kind === 'dir' && !used.has(f.name)).map(f => f.name)
  $.ui.invalidate('ui.render')
}

/** The pane's hooks; `session.start` registers COMMAND once for every pane, in register.ts. */
export const register: Register = on => {
  on('skill.prompt', async ($, e, next) => {
    const result = await next(e)

    await record($, e.skill, result.text)

    return result
  })

  on('command.run', { command: ID }, async $ => {
    if (isOpen) {
      await $.ui.close({ id: ID })

      return { text: 'Skill X-ray panel hidden' }
    }

    isOpen = true
    await $.ui.open({ id: ID, title: 'Skill X-ray' })
    void refresh($)

    return { text: 'Skill X-ray panel shown' }
  })

  on('ui.close', { id: ID }, async ($, e, next) => {
    const result = await next(e)

    if (result.deny === undefined) {
      isOpen = false
    }

    return result
  })

  on('ui.render', { component: 'Pane', requestId: ID }, async ($, e, next) => {
    if (e.surface === 'mobile') {
      return next(e)
    }

    const { Box, Text } = await $.ui.resolve(e)
    const rows = Object.entries(ledger?.skills ?? {}).sort(([, a], [, b]) => b.count - a.count)
    const width = Math.max(0, ...rows.map(([name]) => name.length))

    return (
      <Box flexDirection="column" paddingX={1}>
        <Text bold>{`Skills · ${rows.length} used since ${ledger?.since ?? '…'}`}</Text>
        {rows.map(([name, u]) => (
          <Text key={name} wrap="truncate-end">
            {`${name.padEnd(width)}  ×${u.count}  ~${Math.round(u.tokens / u.count)} tok/run  ~${u.tokens} total  ${u.last}`}
          </Text>
        ))}
        {unused.length > 0 ? <Text dimColor>{`Never used: ${unused.join(', ')}`}</Text> : null}
        <Text dimColor>/xray to close</Text>
      </Box>
    )
  })
}

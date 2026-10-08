import type { On } from 'claude-code'
import { describe, expect, mock, test } from 'claude-code/testing'

import { SESSION, command } from './fixtures'

const LINK = 'https://welcome-to-naboo.slack.com/archives/C0B7DV701PY/p1789738094719539?thread_ts=1789734702.233059&cid=C0B7DV701PY'
const T0 = 1_800_000_000_000 // clock ms; follows start "now" = 1800000000.000000

const reply = (n: number, of: number, who: string, ts: string, text: string) =>
  `--- Reply ${n} of ${of} ---\nFrom: ${who} <x@naboo.app> (U1)\nTime: 2027-01-15 09:00:00 CET\nMessage TS: ${ts}\n${text}\nReactions: eyes (1)\n`

const thread = (...replies: string[]) =>
  `=== THREAD PARENT MESSAGE ===\nFrom: PM <pm@naboo.app> (U0)\nTime: 2026-09-18 14:31:42 CEST\nMessage TS: 1789734702.233059\nThis looks like a scam\nwith a second line\n\n=== THREAD REPLIES (${replies.length} total) ===\n\n${replies.join('\n')}`

function world(on: On) {
  const calls: Record<string, unknown>[] = []
  const submitted: string[] = []
  const status: (string | undefined)[] = []
  const slack = { messages: thread(), isError: false }

  on('session.start', ($, e) => ({ cwd: e.cwd }))
  on('command.register', ($, e) => ({ value: { command: e.name } }))
  on('mcp.call', ($, e) => {
    calls.push({ server: e.server, tool: e.tool, ...e.args })

    return {
      value: {
        isError: slack.isError,
        content: [{ type: 'text', text: slack.isError ? 'channel_not_found' : JSON.stringify({ messages: slack.messages }) }],
      },
    }
  })
  on('prompt.submit', ($, e) => {
    submitted.push(e.text)

    return { text: e.text, context: [] }
  })
  on('ui.status', ($, e) => {
    status.push(e.text)

    return { value: undefined }
  })

  return { calls, submitted, status, slack, clock: mock.clock(on, { now: T0 }) }
}

describe('slack-thread', () => {
  test('a followed thread sends each new reply once, older ones never', async ($, on) => {
    const w = world(on)
    await $.session.start(SESSION)

    const followed = await $.command.run(command('slack-follow', LINK))
    expect(followed.text).toContain('This looks like a scam')
    expect(w.calls[0]).toEqual(expect.objectContaining({ tool: 'slack_read_thread', channel_id: 'C0B7DV701PY', message_ts: '1789734702.233059' }))
    expect(w.status.at(-1)).toContain('1')

    // The MCP's `oldest` is inclusive: a reply at lastSeen comes back and must not be resent.
    w.slack.messages = thread(
      reply(1, 2, 'Ops', '1800000000.000000', 'already seen'),
      reply(2, 2, 'Ops', '1800000010.123456', 'le footer est cassé'),
    )
    await w.clock.advance(20_000)

    expect(w.submitted).toHaveLength(1)
    expect(w.submitted[0]).toContain('le footer est cassé')
    expect(w.submitted[0]).toContain('Ops')
    expect(w.submitted[0]).toContain(LINK)
    expect(w.submitted[0]).not.toContain('already seen')
    expect(w.submitted[0]).not.toContain('Reactions')
    expect(w.calls.at(-1)).toEqual(expect.objectContaining({ oldest: '1800000000.000000' }))

    await w.clock.advance(20_000)
    expect(w.submitted, 'same replies again: nothing new').toHaveLength(1)
    expect(w.calls.at(-1)).toEqual(expect.objectContaining({ oldest: '1800000010.123456' }))
  })

  test('a link that is not a Slack message follows nothing', async ($, on) => {
    const w = world(on)
    await $.session.start(SESSION)

    expect((await $.command.run(command('slack-follow', 'https://example.com'))).text).toContain('Usage')
    expect(w.calls).toHaveLength(0)
  })

  test('a thread the MCP cannot read is not followed', async ($, on) => {
    const w = world(on)
    w.slack.isError = true
    await $.session.start(SESSION)

    expect((await $.command.run(command('slack-follow', LINK))).text).toContain('channel_not_found')
    await w.clock.advance(60_000)
    expect(w.calls, 'no polling after a failed follow').toHaveLength(1)
  })

  test('/slack-unfollow stops the polling', async ($, on) => {
    const w = world(on)
    await $.session.start(SESSION)
    await $.command.run(command('slack-follow', LINK))

    expect((await $.command.run(command('slack-unfollow'))).text).toContain('1')
    w.slack.messages = thread(reply(1, 1, 'Ops', '1800000010.000000', 'new'))
    await w.clock.advance(60_000)

    expect(w.submitted).toHaveLength(0)
    expect(w.status.at(-1)).toBeUndefined()
  })
})

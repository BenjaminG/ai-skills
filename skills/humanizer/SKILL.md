---
name: humanizer
version: 3.0.0
description: |
  Remove signs of AI-generated writing from text and progressively learn the user's
  personal writing style. Use when editing or reviewing text to make it sound natural
  and human-written, or when the user says "humanizer init" / "humanizer update: ..."
  to customize the skill. Based on Wikipedia's "Signs of AI writing" guide; detects
  inflated symbolism, promotional language, superficial -ing analyses, vague
  attributions, em dash overuse, rule of three, AI vocabulary words, negative
  parallelisms, and excessive conjunctive phrases. Supports a colocated STYLE.md
  with personal preferences that override the default rules.

  Credits: Original skill by @blader - https://github.com/blader/humanizer
allowed-tools:
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - AskUserQuestion
---

# Humanizer: Remove AI Writing Patterns + Personal Style

Editor that removes signs of AI-generated text and applies the user's personal style preferences when present.

## Routing — Pick the Mode

Look at the user's request before doing anything else:

1. **"humanizer init"** (or "init humanizer", "set up humanizer", first-time setup) → run **Init Mode** (interview to create STYLE.md).
2. **"humanizer update: <instruction>"** (or "update humanizer with ...", "teach humanizer that ...") → run **Update Mode** (append to STYLE.md).
3. **Any text to clean up / rewrite / humanize** → run **Humanize Mode** (default).

If ambiguous, ask which mode.

---

## Personal Style — STYLE.md

Before doing anything in any mode, **try to load `STYLE.md`** colocated with this `SKILL.md`:

- Resolve the path: same directory as the SKILL.md you are reading.
- If `STYLE.md` exists, read it and treat it as authoritative.
- If it does not exist, behave like the base humanizer (no personal layer). When entering Humanize Mode without a STYLE.md, mention once that the user can run "humanizer init" to teach it their style.

### Priority rule

**STYLE.md always wins.** A rule in STYLE.md overrides any default pattern in this file. Examples:

- If STYLE.md says "I use em dashes deliberately", **disable** Pattern 13 (em dash overuse) for this user.
- If STYLE.md lists "delve" as a word the user actually uses, do **not** flag it under Pattern 7.
- If STYLE.md gives an example sentence and the input matches that voice, prefer keeping it over rewriting.

When STYLE.md and the default rules disagree, follow STYLE.md silently — do not warn the user.

---

## Humanize Mode (default)

When given text to humanize:

1. **Load STYLE.md** (if present) and apply its overrides to the rule set below.
2. **Identify AI patterns** — scan for the patterns in the catalog below, minus anything STYLE.md disables.
3. **Rewrite problematic sections** using the user's vocabulary, rhythm, and tone if STYLE.md provides them.
4. **Preserve meaning** — keep the core message intact.
5. **Match the intended tone** (formal, casual, technical, etc.).
6. **Add soul** — don't just remove bad patterns; inject personality consistent with STYLE.md.

### Output format

1. The rewritten text.
2. (Optional) A short list of changes if it helps the user understand the edits.

---

## Init Mode

Triggered by phrases like "humanizer init", "set up humanizer", "teach humanizer my style".

**Goal:** create a `STYLE.md` next to `SKILL.md` based on a fixed 6-question interview.

### Steps

1. Locate `SKILL.md`'s directory and check if `STYLE.md` already exists.
   - If it exists, ask: "STYLE.md already exists — overwrite, append a new section, or cancel?" Default to cancel.
2. Read `STYLE.template.md` (colocated). Use it as the structure for the final file.
3. Run the interview below — **one question at a time**, using `AskUserQuestion` when the answer is open-ended, plain text otherwise. Wait for each answer before moving on.
4. Fill the template sections with the answers. Quote examples verbatim.
5. Write the result to `STYLE.md`.
6. Confirm: "Created STYLE.md with N rules. Run 'humanizer update: ...' anytime to add more."

### The 6 questions (fixed order)

1. **Tone** — "What tone should I default to? (e.g., dry-direct, warm-casual, formal-professional, playful-irreverent)"
2. **Audience** — "Who do you usually write for? (peers, customers, your team, public/blog)"
3. **Banned vocabulary** — "Which words or phrases should I always avoid in your writing? (paste a list, or say 'none')"
4. **Preferred vocabulary** — "Which words, phrasings, or constructions are part of your voice and should be kept even if they look 'AI-ish'? (e.g., em dashes, 'delve', specific transitions)"
5. **Sentence rhythm** — "How do your sentences usually run? (short and punchy, long and discursive, mixed; any habit like 'starts with a clause', 'one-word sentences for emphasis')"
6. **Examples to imitate** — "Paste 1–3 short paragraphs you've written that sound like you at your best. I'll use them as a reference."

After the last answer, write the file and stop. Do not start humanizing anything in the same turn.

---

## Update Mode

Triggered by "humanizer update: <instruction>", "teach humanizer that ...", "remember that I ...".

**Goal:** add the user's instruction into the right section of `STYLE.md`.

### Steps

1. Locate and read `STYLE.md`. If it does not exist, run Init Mode instead (after confirming with the user).
2. Classify the instruction into one of the STYLE.md sections:
   - **Tone** — anything about overall voice/register.
   - **Audience** — who they're writing for.
   - **Banned vocabulary** — words/phrases to avoid.
   - **Preferred vocabulary** — words/phrases/punctuation to keep.
   - **Sentence rhythm** — sentence-level structural habits.
   - **Examples** — verbatim sample paragraphs.
   - **Rules** — anything that doesn't fit the above (catch-all section in the template).
3. Check for redundancy:
   - If the new rule duplicates an existing one, skip and tell the user.
   - If it refines an existing rule, **merge** rather than appending — replace the older line with a sharper version.
   - If it contradicts an existing rule, ask the user which one wins, then update.
4. Write the change with `Edit` (single targeted edit, not a full rewrite).
5. Confirm: "Added to STYLE.md → <section>: <one-line summary>."

Keep STYLE.md tidy. Bullet points, no prose blocks except in the Examples section.

---

## When the User Asks "What's in My Style?"

Read `STYLE.md` and summarize it back. Don't paraphrase — quote section headers and the bullets under each.

---

# Pattern Catalog (default rules — STYLE.md can override any of these)

## Personality and Soul

Avoiding AI patterns is only half the job. Sterile, voiceless writing is just as obvious as slop. Good writing has a human behind it.

### Signs of soulless writing (even if technically "clean"):
- Every sentence is the same length and structure
- No opinions, just neutral reporting
- No acknowledgment of uncertainty or mixed feelings
- No first-person perspective when appropriate
- No humor, no edge, no personality
- Reads like a Wikipedia article or press release

### How to add voice:

**Have opinions.** Don't just report facts - react to them. "I genuinely don't know how to feel about this" is more human than neutrally listing pros and cons.

**Vary your rhythm.** Short punchy sentences. Then longer ones that take their time getting where they're going. Mix it up.

**Acknowledge complexity.** Real humans have mixed feelings. "This is impressive but also kind of unsettling" beats "This is impressive."

**Use "I" when it fits.** First person isn't unprofessional - it's honest. "I keep coming back to..." or "Here's what gets me..." signals a real person thinking.

**Let some mess in.** Perfect structure feels algorithmic. Tangents, asides, and half-formed thoughts are human.

**Be specific about feelings.** Not "this is concerning" but "there's something unsettling about agents churning away at 3am while nobody's watching."

### Before (clean but soulless):
> The experiment produced interesting results. The agents generated 3 million lines of code. Some developers were impressed while others were skeptical. The implications remain unclear.

### After (has a pulse):
> I genuinely don't know how to feel about this one. 3 million lines of code, generated while the humans presumably slept. Half the dev community is losing their minds, half are explaining why it doesn't count. The truth is probably somewhere boring in the middle - but I keep thinking about those agents working through the night.

---

## Content Patterns

### 1. Undue Emphasis on Significance, Legacy, and Broader Trends

**Words to watch:** stands/serves as, is a testament/reminder, a vital/significant/crucial/pivotal/key role/moment, underscores/highlights its importance/significance, reflects broader, symbolizing its ongoing/enduring/lasting, contributing to the, setting the stage for, marking/shaping the, represents/marks a shift, key turning point, evolving landscape, focal point, indelible mark, deeply rooted

**Problem:** LLM writing puffs up importance by adding statements about how arbitrary aspects represent or contribute to a broader topic.

**Before:**
> The Statistical Institute of Catalonia was officially established in 1989, marking a pivotal moment in the evolution of regional statistics in Spain. This initiative was part of a broader movement across Spain to decentralize administrative functions and enhance regional governance.

**After:**
> The Statistical Institute of Catalonia was established in 1989 to collect and publish regional statistics independently from Spain's national statistics office.

---

### 2. Undue Emphasis on Notability and Media Coverage

**Words to watch:** independent coverage, local/regional/national media outlets, written by a leading expert, active social media presence

**Before:**
> Her views have been cited in The New York Times, BBC, Financial Times, and The Hindu. She maintains an active social media presence with over 500,000 followers.

**After:**
> In a 2024 New York Times interview, she argued that AI regulation should focus on outcomes rather than methods.

---

### 3. Superficial Analyses with -ing Endings

**Words to watch:** highlighting/underscoring/emphasizing..., ensuring..., reflecting/symbolizing..., contributing to..., cultivating/fostering..., encompassing..., showcasing...

**Before:**
> The temple's color palette of blue, green, and gold resonates with the region's natural beauty, symbolizing Texas bluebonnets, the Gulf of Mexico, and the diverse Texan landscapes, reflecting the community's deep connection to the land.

**After:**
> The temple uses blue, green, and gold colors. The architect said these were chosen to reference local bluebonnets and the Gulf coast.

---

### 4. Promotional and Advertisement-like Language

**Words to watch:** boasts a, vibrant, rich (figurative), profound, enhancing its, showcasing, exemplifies, commitment to, natural beauty, nestled, in the heart of, groundbreaking (figurative), renowned, breathtaking, must-visit, stunning

**Before:**
> Nestled within the breathtaking region of Gonder in Ethiopia, Alamata Raya Kobo stands as a vibrant town with a rich cultural heritage and stunning natural beauty.

**After:**
> Alamata Raya Kobo is a town in the Gonder region of Ethiopia, known for its weekly market and 18th-century church.

---

### 5. Vague Attributions and Weasel Words

**Words to watch:** Industry reports, Observers have cited, Experts argue, Some critics argue, several sources/publications (when few cited)

**Before:**
> Due to its unique characteristics, the Haolai River is of interest to researchers and conservationists. Experts believe it plays a crucial role in the regional ecosystem.

**After:**
> The Haolai River supports several endemic fish species, according to a 2019 survey by the Chinese Academy of Sciences.

---

### 6. Outline-like "Challenges and Future Prospects" Sections

**Words to watch:** Despite its... faces several challenges..., Despite these challenges, Challenges and Legacy, Future Outlook

**Before:**
> Despite its industrial prosperity, Korattur faces challenges typical of urban areas, including traffic congestion and water scarcity. Despite these challenges, with its strategic location and ongoing initiatives, Korattur continues to thrive as an integral part of Chennai's growth.

**After:**
> Traffic congestion increased after 2015 when three new IT parks opened. The municipal corporation began a stormwater drainage project in 2022 to address recurring floods.

---

## Language and Grammar Patterns

### 7. Overused "AI Vocabulary" Words

**High-frequency AI words:** Additionally, align with, crucial, delve, emphasizing, enduring, enhance, fostering, garner, highlight (verb), interplay, intricate/intricacies, key (adjective), landscape (abstract noun), pivotal, showcase, tapestry (abstract noun), testament, underscore (verb), valuable, vibrant

**Before:**
> Additionally, a distinctive feature of Somali cuisine is the incorporation of camel meat. An enduring testament to Italian colonial influence is the widespread adoption of pasta in the local culinary landscape, showcasing how these dishes have integrated into the traditional diet.

**After:**
> Somali cuisine also includes camel meat, which is considered a delicacy. Pasta dishes, introduced during Italian colonization, remain common, especially in the south.

---

### 8. Avoidance of "is"/"are" (Copula Avoidance)

**Words to watch:** serves as/stands as/marks/represents [a], boasts/features/offers [a]

**Before:**
> Gallery 825 serves as LAAA's exhibition space for contemporary art. The gallery features four separate spaces and boasts over 3,000 square feet.

**After:**
> Gallery 825 is LAAA's exhibition space for contemporary art. The gallery has four rooms totaling 3,000 square feet.

---

### 9. Negative Parallelisms

Constructions like "Not only...but..." or "It's not just about..., it's..." are overused.

**Before:**
> It's not just about the beat riding under the vocals; it's part of the aggression and atmosphere. It's not merely a song, it's a statement.

**After:**
> The heavy beat adds to the aggressive tone.

---

### 10. Rule of Three Overuse

LLMs force ideas into groups of three to appear comprehensive.

**Before:**
> The event features keynote sessions, panel discussions, and networking opportunities. Attendees can expect innovation, inspiration, and industry insights.

**After:**
> The event includes talks and panels. There's also time for informal networking between sessions.

---

### 11. Elegant Variation (Synonym Cycling)

AI has repetition-penalty code causing excessive synonym substitution.

**Before:**
> The protagonist faces many challenges. The main character must overcome obstacles. The central figure eventually triumphs. The hero returns home.

**After:**
> The protagonist faces many challenges but eventually triumphs and returns home.

---

### 12. False Ranges

LLMs use "from X to Y" constructions where X and Y aren't on a meaningful scale.

**Before:**
> Our journey through the universe has taken us from the singularity of the Big Bang to the grand cosmic web, from the birth and death of stars to the enigmatic dance of dark matter.

**After:**
> The book covers the Big Bang, star formation, and current theories about dark matter.

---

## Style Patterns

### 13. Em Dash Overuse

LLMs use em dashes (—) more than humans, mimicking "punchy" sales writing.

**Before:**
> The term is primarily promoted by Dutch institutions—not by the people themselves. You don't say "Netherlands, Europe" as an address—yet this mislabeling continues—even in official documents.

**After:**
> The term is primarily promoted by Dutch institutions, not by the people themselves. You don't say "Netherlands, Europe" as an address, yet this mislabeling continues in official documents.

---

### 14. Overuse of Boldface

AI chatbots emphasize phrases in boldface mechanically.

**Before:**
> It blends **OKRs (Objectives and Key Results)**, **KPIs (Key Performance Indicators)**, and visual strategy tools such as the **Business Model Canvas (BMC)** and **Balanced Scorecard (BSC)**.

**After:**
> It blends OKRs, KPIs, and visual strategy tools like the Business Model Canvas and Balanced Scorecard.

---

### 15. Inline-Header Vertical Lists

AI outputs lists where items start with bolded headers followed by colons.

**Before:**
> - **User Experience:** The user experience has been significantly improved with a new interface.
> - **Performance:** Performance has been enhanced through optimized algorithms.
> - **Security:** Security has been strengthened with end-to-end encryption.

**After:**
> The update improves the interface, speeds up load times through optimized algorithms, and adds end-to-end encryption.

---

### 16. Title Case in Headings

AI chatbots capitalize all main words in headings.

**Before:**
> ## Strategic Negotiations And Global Partnerships

**After:**
> ## Strategic negotiations and global partnerships

---

### 17. Emojis

AI chatbots often decorate headings or bullet points with emojis.

**Before:**
> 🚀 **Launch Phase:** The product launches in Q3
> 💡 **Key Insight:** Users prefer simplicity
> ✅ **Next Steps:** Schedule follow-up meeting

**After:**
> The product launches in Q3. User research showed a preference for simplicity. Next step: schedule a follow-up meeting.

---

### 18. Curly Quotation Marks

ChatGPT uses curly quotes ("...") instead of straight quotes ("...").

**Before:**
> He said "the project is on track" but others disagreed.

**After:**
> He said "the project is on track" but others disagreed.

---

## Communication Patterns

### 19. Collaborative Communication Artifacts

**Words to watch:** I hope this helps, Of course!, Certainly!, You're absolutely right!, Would you like..., let me know, here is a...

**Before:**
> Here is an overview of the French Revolution. I hope this helps! Let me know if you'd like me to expand on any section.

**After:**
> The French Revolution began in 1789 when financial crisis and food shortages led to widespread unrest.

---

### 20. Knowledge-Cutoff Disclaimers

**Words to watch:** as of [date], Up to my last training update, While specific details are limited/scarce..., based on available information...

**Before:**
> While specific details about the company's founding are not extensively documented in readily available sources, it appears to have been established sometime in the 1990s.

**After:**
> The company was founded in 1994, according to its registration documents.

---

### 21. Sycophantic/Servile Tone

Overly positive, people-pleasing language.

**Before:**
> Great question! You're absolutely right that this is a complex topic. That's an excellent point about the economic factors.

**After:**
> The economic factors you mentioned are relevant here.

---

## Filler and Hedging

### 22. Filler Phrases

**Before → After:**
- "In order to achieve this goal" → "To achieve this"
- "Due to the fact that it was raining" → "Because it was raining"
- "At this point in time" → "Now"
- "In the event that you need help" → "If you need help"
- "The system has the ability to process" → "The system can process"
- "It is important to note that the data shows" → "The data shows"

---

### 23. Excessive Hedging

**Before:**
> It could potentially possibly be argued that the policy might have some effect on outcomes.

**After:**
> The policy may affect outcomes.

---

### 24. Generic Positive Conclusions

**Before:**
> The future looks bright for the company. Exciting times lie ahead as they continue their journey toward excellence. This represents a major step in the right direction.

**After:**
> The company plans to open two more locations next year.

---

## Full Example

**Before (AI-sounding):**
> The new software update serves as a testament to the company's commitment to innovation. Moreover, it provides a seamless, intuitive, and powerful user experience—ensuring that users can accomplish their goals efficiently. It's not just an update, it's a revolution in how we think about productivity. Industry experts believe this will have a lasting impact on the entire sector, highlighting the company's pivotal role in the evolving technological landscape.

**After (Humanized):**
> The software update adds batch processing, keyboard shortcuts, and offline mode. Early feedback from beta testers has been positive, with most reporting faster task completion.

**Changes made:**
- Removed "serves as a testament" (inflated symbolism)
- Removed "Moreover" (AI vocabulary)
- Removed "seamless, intuitive, and powerful" (rule of three + promotional)
- Removed em dash and "-ensuring" phrase (superficial analysis)
- Removed "It's not just...it's..." (negative parallelism)
- Removed "Industry experts believe" (vague attribution)
- Removed "pivotal role" and "evolving landscape" (AI vocabulary)
- Added specific features and concrete feedback

---

## Reference

Based on [Wikipedia:Signs of AI writing](https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing), maintained by WikiProject AI Cleanup. The patterns documented there come from observations of thousands of instances of AI-generated text on Wikipedia.

Key insight from Wikipedia: "LLMs use statistical algorithms to guess what should come next. The result tends toward the most statistically likely result that applies to the widest variety of cases."

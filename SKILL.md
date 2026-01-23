---
name: last30days
description: Research a topic from the last 30 days on Reddit + X; judge/summarize into best practices, a prompt pack, and a reusable context snippet.
argument-hint: "[topic]"
context: fork
agent: Explore
disable-model-invocation: true
allowed-tools: Bash, Read, Write
---

# last30days: 30-Day Research Synthesis

Research a topic across Reddit and X from the last 30 days, then synthesize findings into actionable best practices, prompts, and reusable context.

## Setup Check

First, verify API key configuration exists:

```bash
if [ ! -f ~/.config/last30days/.env ]; then
  echo "SETUP_NEEDED"
else
  echo "CONFIGURED"
fi
```

### If SETUP_NEEDED

Run the NUX flow to configure API keys. Use the AskUserQuestion tool to collect:

1. **OpenAI API Key** (optional but recommended for Reddit research)
2. **xAI API Key** (optional but recommended for X research)
3. **Model policies** (optional, defaults are usually fine)

Then create the config:

```bash
mkdir -p ~/.config/last30days
cat > ~/.config/last30days/.env << 'ENVEOF'
# last30days API Configuration
# At least one key is required

OPENAI_API_KEY=
XAI_API_KEY=

# Model selection (optional)
# OPENAI_MODEL_POLICY=auto|pinned (default: auto)
# OPENAI_MODEL_PIN=gpt-5.2 (only if pinned)
# XAI_MODEL_POLICY=latest|stable|pinned (default: latest)
# XAI_MODEL_PIN=grok-4 (only if pinned)
ENVEOF

chmod 600 ~/.config/last30days/.env
echo "Config created at ~/.config/last30days/.env"
echo "Please edit it to add your API keys, then run the skill again."
```

After creating the file, instruct the user to edit `~/.config/last30days/.env` and add their keys.

**STOP HERE if setup was needed. Do not proceed until keys are configured.**

---

## Research Execution

If configured, run the research orchestrator:

```bash
python3 ~/.claude/skills/last30days/scripts/last30days.py "$ARGUMENTS" --emit=compact 2>&1
```

The script will:
- Auto-detect which keys are available
- Auto-select the best models (or use pinned versions)
- Search Reddit via OpenAI Responses API (if OpenAI key present)
- Search X via xAI Responses API (if xAI key present)
- Enrich Reddit threads with real engagement metrics
- Score, rank, and dedupe results
- Output files to `~/.local/share/last30days/out/`

---

## RESEARCH DATA

The output above contains the research data. Now synthesize it.

---

## Your Role: Judge and Synthesizer

You are now the expert judge. Using the research data above, produce:

### A) Best Practices (Grouped & Actionable)

Group findings into 3-7 thematic categories. For each best practice:
- State the practice clearly and actionably
- Cite supporting item IDs (e.g., "supported by R3, R7, X2")
- Note if it's **strongly supported** (multiple high-score sources) or **niche** (single source or low engagement)

### B) Prompt Pack (3-7 Copy/Paste Prompts)

Create ready-to-use prompts tailored to the topic. Each prompt should:
- Be immediately usable (copy/paste ready)
- Target a specific use case discovered in the research
- Include any relevant context or constraints from the findings

### C) Reusable Context Snippet

Create a compact (~200-400 words) context block that other skills/tools can import. Include:
- Core concepts and terminology
- Key techniques or patterns
- Common pitfalls to avoid
- Brief source attribution

### D) Sources Appendix

List all source URLs organized by platform:
- **Reddit**: Title, subreddit, URL, score
- **X**: Author, text excerpt, URL, engagement

### E) Confidence Assessment

Explicitly state:
- **Strongly Supported**: Practices backed by multiple high-engagement sources
- **Emerging/Niche**: Practices from single sources or low engagement (still valuable but use with awareness)
- **Gaps**: What the research didn't cover well

---

## Final Output

After completing your synthesis:

1. Display the full report to the user
2. Confirm the files were written:
   - `~/.local/share/last30days/out/report.md`
   - `~/.local/share/last30days/out/report.json`
   - `~/.local/share/last30days/out/last30days.context.md`

3. Show the header summary:
   ```
   Models used: OpenAI={model} xAI={model}
   Mode: {reddit-only|x-only|both}
   Coverage: {note about triangulation if single-source}
   ```

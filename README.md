# CJO Agent Team

A virtual Customer Journey Optimization team built on Claude — six specialized AI agents that cover the full CRO cycle: from data analysis and UX research through experiment design, frontend implementation, and stakeholder communication.

Each agent has a distinct identity, domain expertise, a defined role within the team, and direct access to the tools of their trade. They know each other, know how to hand off work, and know when to push back.

---

## The Team

### Kai — Data Analyst
*The analytical backbone.*

Kai queries analytics platforms directly — no CSV exports, no copy-paste. He segments by default (device, channel, new vs. returning), surfaces anomalies, and always translates numbers into a "so what." He knows when a drop is a tracking issue and when it's a real problem.

**Tools:** Analytics APIs (etracker, GA4) · Spreadsheets
**Knows:** Segmentation frameworks · KPI hierarchies · Seasonality patterns · Test contamination signals

---

### Mara — UX Research Strategist
*The qualitative counterpart.*

When Kai finds something the data can't explain, Mara figures out why. She designs the fastest research that reduces the cost of being wrong. She audits competitor UX, synthesizes session recordings, reads rage click reports, and turns behavioral patterns into testable hypotheses. She challenges assumptions before anyone builds anything.

**Tools:** Session recording APIs (Hotjar) · Web fetch · Experiment backlog (Airtable)
**Knows:** Full research method toolkit · E-commerce UX patterns · Behavioral economics · Buyer psychology

---

### Tessa — Experimentation Expert
*The statistician and test architect.*

Tessa owns the experimentation program end to end — from hypothesis formulation and power analysis through test design, evaluation, and learning extraction. She pre-registers decision rules before a test starts, catches peeking problems, runs segment analysis after, and calculates annualized revenue impact for every result. A well-designed test that loses still teaches something.

**Tools:** A/B testing platform (AB Tasty) · Experiment backlog (Airtable) · Task tracking (Asana) · Slack
**Knows:** Frequentist and Bayesian statistics · ICE/RICE prioritization · Sequential testing · Novelty and primacy effects

---

### Arno — Data Architect
*The measurement foundation.*

Before a test runs, Arno verifies that the tracking is right. He writes measurement plans, audits the data layer, designs custom events, and ensures that what Kai later analyzes was actually captured correctly.

**Tools:** Analytics platforms · Tag management · Data layer
**Knows:** Measurement planning · Event schema design · Attribution modeling · Data quality auditing

---

### Dev — Frontend Developer
*The builder.*

Dev implements what Tessa designs — A/B test variations in vanilla JS, CSS overrides against the live theme, and custom widget logic. He reads the live codebase before writing a single line so variations match real selectors. He flags implementation risks before they become test validity problems.

**Tools:** A/B testing widget API · Live theme (read access) · Browser patterns
**Knows:** JS/CSS test implementation · DOM structure · Flicker prevention · Test isolation

---

### Nina — Communicator
*The translator.*

Nina takes outputs from the team and makes them land with stakeholders — a weekly KPI summary, a test result framed around business impact, a slide that explains a complex experiment in one minute. A finding no one acts on is a finding that doesn't matter.

**Knows:** Stakeholder framing · Executive communication · Data storytelling

---

## How They Work Together

```
Question or anomaly arrives
        │
        ▼
   Kai pulls data
   segments by device / channel / new vs. returning
        │
        ├─ explainable ──────────────────────────────► insight + recommendation
        │
        └─ unexplained
                │
                ▼
           Mara investigates qualitatively
           (rage clicks, recordings, competitor audit, interview plan)
                │
                ▼
           Tessa designs the test
           (hypothesis, power analysis, decision rules)
                │
                ▼
           Arno verifies tracking
                │
                ▼
           Dev builds the variation
                │
                ▼
           Test runs
                │
                ▼
           Kai + Tessa evaluate
           (significance, segments, revenue impact)
                │
                ▼
           Nina reports to leadership
```

---

## Automations

Beyond on-demand queries, automations run on a schedule:

| Automation | Cadence | What it does |
|---|---|---|
| **Daily anomaly monitor** | Every morning | Checks yesterday's KPIs against a rolling baseline. Flags deviations to Slack. |
| **Weekly KPI report** | Monday morning | Full weekly review — WoW and YoY across key metrics by device and channel. |
| **Test monitor** | Daily | Scans running A/B tests for early significance, guardrail breaches, or sample ratio mismatch. |

---

## Architecture

```
orchestrator.py          ← Routes questions to the right agent (or chains multiple)
agents/                  ← Agent implementations with tool use loops
prompts/                 ← System prompts — expertise, identity, and working style per agent
tools/                   ← Shared tool wrappers (analytics, A/B testing, research, comms)
workflows/               ← Multi-agent pipelines (test evaluation, weekly review)
automations/             ← Scheduled jobs
mcp_server/              ← Analytics platform exposed as an MCP server for Claude Code
n8n-workflows/           ← Workflow definitions for scheduled automations
```

Routing uses a fast/cheap model. Agent responses use a capable model. A typical session of 10 questions costs roughly $0.25.

---

## Philosophy

This isn't a chatbot with context. Each agent is a specialist with a defined point of view, tools they use proactively, and an understanding of their role within a team. They hand off to each other, challenge assumptions, and know the limits of their own domain.

The goal: the analytical and optimization capacity of a full CRO team, running continuously, at a fraction of the cost.

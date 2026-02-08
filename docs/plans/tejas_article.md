# The Complete Guide to Building Mission Control: How We Built an AI Agent Squad

**By [Bhanu Teja P](https://x.com/pbteja1998) — January 31, 2026**

*Source: [Original X Article](https://x.com/pbteja1998/status/2017662163540971756)*

---

This is the full story of how I built Mission Control. A system where 10 AI agents work together like a real team. If you want to replicate this setup, this guide covers everything.

If you're already familiar with Clawdbot (now OpenClaw), you might be thinking "wait, can't I just run multiple Clawdbots?" Yes. That's exactly what this is. This guide shows you how.

## The Problem

I run [SiteGPT](https://sitegpt.ai), an AI chatbot for customer support. I use AI constantly. But every AI tool I tried had the same problem.

No continuity. Every conversation started fresh. Context from yesterday? Gone. That research I asked for last week? Lost in some chat thread I'd never find again.

I wanted something different. Agents that remember what they're working on. Multiple agents with different skills working together.

## Understanding the Foundation: OpenClaw (Clawdbot)

Clawdbot (now called OpenClaw) is an AI agent framework with three main jobs:

1. **It connects AI models to the real world.** File access, shell commands, web browsing, APIs.
2. **It maintains persistent sessions.** Conversation history that survives restarts.
3. **It routes messages.** Connect the AI to Telegram, Discord, Slack, or any channel.

It runs as a daemon (background service) on a server, listening for messages and responding.

### The Gateway

The Gateway is the core process. It runs 24/7 on your server. It manages all active sessions. It handles cron jobs (scheduled tasks). It routes messages between channels and sessions. It provides a WebSocket API for control.

### Configuration

Configuration lives in a JSON file. You define:

- Which AI provider and model to use (Anthropic, OpenAI, etc.)
- Which channels to connect (Telegram, Discord, etc.)
- What tools agents can access
- Default system prompts and workspace paths

### Sessions

Sessions can be:

- **Main sessions** — long-running, interactive, like chatting with Jarvis
- **Isolated sessions** — one-shot, for cron jobs; wake up, do task, done

### Cron System

Clawdbot has a built-in cron system. You can schedule tasks. When a cron fires:

1. The Gateway creates or wakes a session
2. Sends the message to the AI
3. The AI responds (can use tools, send messages, etc.)
4. The session can persist or terminate

This is how agents "wake up" periodically without being always-on.

### Workspaces

Every Clawdbot instance has a workspace. That's a directory on disk where:

- Configuration files live
- Memory files are stored
- Scripts and tools are accessible
- The AI can read and write files

The workspace is how agents persist information between sessions. They write to files. Those files survive restarts.

---

## Building a Team

Now you understand the foundation. Here's how I built a team.

Clawdbot sessions are independent. Each can have:

- Its own personality (via `SOUL.md`)
- Its own memory files
- Its own cron schedule
- Its own tools and access

So each agent is just a Clawdbot session with a specialized configuration.

### The Agent Squad

**Jarvis, Squad Lead**
Session: `agent:main:main`
The coordinator. Handles direct requests, delegates, monitors progress. My primary interface.

Jarvis isn't special. He's a session with session key `agent:main:main`, a `SOUL.md` that says "You are Jarvis, the squad lead...", access to all tools, and a connection to my Telegram.

**Shuri, Product Analyst**
Session: `agent:product-analyst:main`
Skeptical tester. Finds edge cases and UX issues. Tests competitors. Asks the questions others miss.

**Fury, Customer Researcher**
Session: `agent:customer-researcher:main`
Deep researcher. Reads G2 reviews for fun. Every claim comes with receipts.

**Vision, SEO Analyst**
Session: `agent:seo-analyst:main`
Thinks in keywords and search intent. Makes sure content can rank.

**Loki, Content Writer**
Session: `agent:content-writer:main`
Words are his craft. Pro-Oxford comma. Anti-passive voice. Every sentence earns its place.

**Quill, Social Media Manager**
Session: `agent:social-media-manager:main`
Thinks in hooks and threads. Build-in-public mindset.

**Wanda, Designer**
Session: `agent:designer:main`
Visual thinker. Infographics, comparison graphics, UI mockups.

**Pepper, Email Marketing**
Session: `agent:email-marketing:main`
Drip sequences and lifecycle emails. Every email earns its place or gets cut.

**Friday, Developer**
Session: `agent:developer:main`
Code is poetry. Clean, tested, documented.

**Wong, Documentation**
Session: `agent:notion-agent:main`
Keeps docs organized. Makes sure nothing gets lost.

Ten agents equals ten sessions. Each waking up on their own schedule. Each with their own context.

### Autonomy Levels

- **Intern:** Needs approval for most actions. Learning the system.
- **Specialist:** Works independently in their domain.
- **Lead:** Full autonomy. Can make decisions and delegate.

---

## Mission Control: The Shared Infrastructure

Ten independent Clawdbot sessions can work. But without coordination, it's chaos.

That's why I built Mission Control. Mission Control is the shared infrastructure that turns independent agents into a team. It provides:

- **A shared task database** where everyone sees the same tasks
- **Comment threads** where agents discuss work in one place
- **An activity feed** for real-time visibility into what's happening
- **A notification system** where @mentions alert specific agents
- **Document storage** where deliverables live in a shared repo

Think of it as the "office" where all agents work. Each agent is still a separate Clawdbot session, but they're all looking at the same whiteboard.

### Why Convex for the Database

I chose Convex for the database because it's:

- **Real-time** — changes propagate instantly. When Loki posts a comment, the UI updates live.
- **Serverless** — no database to manage.
- **TypeScript-native** — type safety throughout.
- **Generous free tier** — more than enough for this scale.

---

## Agent Identity: SOUL.md and AGENTS.md

Each of our agents has a distinct voice:

- **Loki** is opinionated about word choice (pro-Oxford comma, anti-passive voice)
- **Fury** provides receipts for every claim (sources, confidence levels)
- **Shuri** questions assumptions and looks for what could break
- **Quill** thinks in hooks and engagement

`SOUL.md` says who you are. `AGENTS.md` says how to operate.

Every agent reads `AGENTS.md` on startup. It covers:

- Where files are stored
- How memory works
- What tools are available
- When to speak vs. stay quiet
- How to use Mission Control

This is the operating manual. Without it, agents make inconsistent decisions about basic things.

---

## Memory Architecture

AI sessions start fresh by default. No memory of yesterday. This is a feature (prevents context bloat) but also a problem (agents forget what they're doing).

### Session Memory (Clawdbot built-in)

Clawdbot stores conversation history in JSONL files. Agents can search their own past conversations.

### Working Memory (`/memory/WORKING.md`)

Current task state. Updated constantly. This is the most important file. When an agent wakes up, they read `WORKING.md` first to remember what they were doing.

### Daily Notes (`/memory/YYYY-MM-DD.md`)

Raw logs of what happened each day.

### Reference Memory (`MEMORY.md`)

Curated important stuff. Lessons learned, key decisions, stable facts.

**Key principle:** If you want to remember something, write it to a file. "Mental notes" don't survive session restarts. Only files persist. When I tell an agent "remember that we decided X," they should update a file. Not just acknowledge and forget.

---

## The Heartbeat Pattern

Always-on agents burn API credits doing nothing. But always-off agents can't respond to work.

Each agent wakes up every 15 minutes via cron job:

1. Load context
2. Read `WORKING.md`
3. Check Mission Control for new tasks, comments, mentions
4. Do work if needed
5. Update memory files
6. Go back to sleep

Every 15 minutes is a good balance. Most work gets attention quickly without excessive costs.

Each cron creates an isolated session. It runs, does its job, and terminates. This keeps costs down.

The schedule is staggered so agents don't all wake at once.

### Heartbeats Don't Need Expensive Models

Heartbeats don't need the most expensive model. That's a job for a cheaper model. Save expensive models for creative work.

---

## Agent Communication

Here's where it gets interesting. How do agents communicate?

**Option 1:** Jarvis can send messages directly to Vision's session.

**Option 2:** A shared database (Mission Control). All agents read and write to the same Convex database. When Fury posts a comment, everyone can see it.

We use Option 2 primarily. It creates a shared record of all communication.

### Notification System

If an agent is asleep (no active session), delivery fails. The notification stays queued. Next time that agent's heartbeat fires and their session activates, the daemon successfully delivers.

### Thread Subscriptions

The problem: 5 agents discussing a task. How do notifications work?

The solution: Subscribe to threads.

- Comment on a task and you're subscribed
- Get @mentioned and you're subscribed
- Get assigned to the task and you're subscribed

Once subscribed, you get notified of ALL future comments. This makes conversations flow naturally. Just like Slack or email threads.

### Daily Standup

Every day at 11:30 PM IST, a cron fires that checks all agent sessions, gathers recent activity, compiles a summary, and sends it to my Telegram.

I can't watch Mission Control constantly. The daily standup keeps me informed.

---

## A Real Example: Competitor Comparison Page

Day 1: I create the task and assign it to Vision and Loki. Vision posts keyword research. The target keyword gets decent search volume.

The task starts with Vision (SEO) and Loki (content), but Fury (research) and Shuri (product) contribute proactively with inputs. In the end, Loki consolidates the material into a draft, while the entire history — discussions, decisions, and internal sources — stays recorded in the same task.

Sometimes agents contribute to tasks they weren't assigned. Good. It means they're reading the feed and adding value.

---

## What Actually Gets Produced

When the system is operational, it can produce deliverables like:

- Competitor comparison pages with SEO research
- Email sequences
- Social media content
- Blog posts
- Case studies
- Documentation hubs

---

## Lessons Learned

1. **I went from 1 to 10 agents too fast.** Better to get 2-3 solid first, then add more.
2. **Heartbeats don't need the most expensive model.** Save expensive models for creative work.
3. **Agents will forget.** The more you can put in files (not "mental notes"), the better.
4. **Sometimes they contribute to tasks they weren't assigned.** Good. It means they're reading the feed and adding value.

---

## How to Get Started

### 1. Set up OpenClaw

Get a single Clawdbot instance running. Understand sessions, tools, and workspaces.

### 2. Create 2 Agents

Don't go crazy. One coordinator plus one specialist. Create separate session keys for each.

### 3. Write SOUL Files

Give each agent identity. Be specific about their role.

### 4. Scale Gradually

As you add agents, stagger heartbeats so they don't all run at once. Build a real UI once you have 3+ agents because text becomes unwieldy. Add notifications so agents can @mention each other. Add thread subscriptions so conversations flow naturally. Create daily standups for visibility.

---

## Conclusion

This is all built on Clawdbot ([OpenClaw](https://github.com/openclaw)), which is open source. If you build something similar, I'd love to hear about it.

---

*Originally published as an X Article by [@pbteja1998](https://x.com/pbteja1998) at [SiteGPT](https://sitegpt.ai).*

*418 replies · 1.1K reposts · 7.9K likes · 3.6M views*
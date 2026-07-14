# Bifrost — Design Specification

> The bridge between OpenCode and the agent experience from Claude Code.
> **Date:** 2026-07-10 | **Status:** Under review

## 1. Problem
OpenCode users migrating from Claude Code lose: persistent memory across sessions, rich skill engine, mature permissions, context injection. Bifrost bridges these gaps.

## 2. Architecture
Three components: (1) JS/TS plugin hooking OpenCode lifecycle events, (2) Python FastMCP companion wrapping nano-claude-code's memory+skill modules, (3) 5-line opencode.json config snippet. Plugin ↔ Companion communicate via stdio MCP.

## 3. Components

### Memory (4 types, 2 scopes)
Types: decision, pattern, fact, feedback. Scopes: user (~/.bifrost/memory/user/) and project (~/.bifrost/memory/<hash>/). AI-ranked search. Auto-save on session end. JSON file-per-entry store. v2: overnight consolidation.

### Skill Bridge
76 existing skills work unchanged. Adds: argument substitution ($0, !`cmd`), fork/inline dispatch, model routing (sonnet→flash, opus→pro), allowed-tools enforcement via MCP scope.

### Permission Bridge
ConfigMigrate reads .claude/settings.json → OpenCode rules. Path-scoped .claude/rules/ injected at edit time.

### Context Injection
session.start loads AGENTS.md + CLAUDE.md + rules/ + top-N memories into system prompt.

## 4. v1/v2 Scope
v1: memory CRUD, AI search, AGENTS.md/rules loading, skill bridge, permission migration.
v2: memory consolidation, agent orchestration, worktree isolation.

## 5. Non-Goals: Not a Claude Code clone, not standalone, not IDE plugin.

## 6. Risks: nano-claude-code drift (pin commit), MCP reliability (stdio restart), OpenCode API changes (pin oh-my-openagent version), file corruption (append-only + index rebuild).

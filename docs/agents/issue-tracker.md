# Issue Tracker Documentation

## Overview

Issues live in GitHub Issues (joeytomoyama/max-planck-project).

This document tracks which issues are:
- Implemented
- In progress
- Blocked by other tickets

## Ticket Status

### [01] Project Scaffolding & Docker ✓ COMPLETE

**Status**: Implemented
**Files Created**:
- `docker-compose.yml` - Multi-service orchestration
- `.env.example` - Environment variables template
- All backend/frontend directory structures
- Basic CI scripts

**Dependencies**: Blocks tickets 04, 05, 06, 07, 08

### [04] React Waiting Room (Lobby) ⏳ BLOCKED

**Status**: Blocked by #01
**Description**: Lobby component for waiting room

### [05] Experiment Room (Rounds & Voting) ⏳ BLOCKED

**Status**: Blocked by #01
**Description**: Main experiment interface with rounds and voting

### [06] Configuration File (config.yml) ✓ PARTIAL

**Status**: In progress (#01 includes basic config structure)
**Note**: Full AI agent behavior prompts documented in `ai_prompts.md`

### [07] AI Agent Behavior & Prompts ⏳ BLOCKED

**Status**: Blocked by #01
**Description**: LLM integration for AI participant responses

### [08] Documentation & Testing ✓ COMPLETE

**Files Created** (by #01):
- `ARCHITECTURE.md` - Design decisions and trade-offs
- `TESTING.md` - Manual verification checklist
- `ai_prompts.md` - All AI prompts used
- `README.md` - Project overview
- `.github/AI-USAGE-LOG.md` - AI usage transparency

## Issue Links

Full issue list: https://github.com/joeytomoyama/max-planck-project/issues

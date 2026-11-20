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

### [02] Database Schema & Seed Data ✓ COMPLETE

**Status**: Implemented (see commit `8217eb1`)
**Description**: sessions / participants / rounds / votes tables, migration
scripts, and a 3-participant demo seed.

**Dependencies**: Blocked by #01; blocks #03

### [03] Backend API with WebSocket Support ✓ COMPLETE

**Status**: Implemented
**Description**: REST session lifecycle + JSON-frame WebSocket chat/voting.

**Acceptance criteria covered**:
- `POST /api/sessions` creates a waiting session
- `GET /api/sessions/{id}` returns session details, participants, and current round
- `POST /api/sessions/{id}/start` transitions waiting → active (409 when closed)
- `WebSocket /ws/{session_id}` handles chat and vote events as JSON frames
- `POST /api/sessions/{id}/votes` records votes with a blind acknowledgement
- Closed/expired sessions are rejected over both HTTP and WebSocket

**Notes**:
- Legacy `GET .../start` and `POST .../vote` routes were replaced.
- Vote events give the voter a private ack and peers an anonymous notice; the
  vote target is never broadcast. The current frontend still sends text frames
  and needs ticket #04 to adopt the JSON protocol.
- Closed sessions return **409 Conflict** (not the decision ticket's suggested
  405, which is for unsupported HTTP methods); WebSocket connects are refused
  with close code 4001. This was kept deliberately — change it if the 405
  wording is required.
- Round progression and the final results reveal are ticket #05's scope; #03
  only exposes the current round number and keeps individual votes blind.

**Dependencies**: Blocked by #01, #02; blocks #04, #05, #08

### [04] React Waiting Room (Lobby) ⏳ READY

**Status**: Unblocked (#01 and #03 complete); must adopt the JSON WS protocol
**Description**: Lobby component for waiting room

### [05] Experiment Room (Rounds & Voting) ⏳ READY

**Status**: Unblocked (#01 and #03 complete); owns round progression and result reveal
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

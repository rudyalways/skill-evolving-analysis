# TaiChu P0 — Skill Invocation Memory & Compaction Survival

> L3 设计 spec。借 Claude Code Rev `invoked_skills` + Hermes review 接缝。  
> 证据：[l3-comprehensive-skill-analysis.md](l3-comprehensive-skill-analysis.md) §4-5

---

## Problem

`load_skill` returns `ToolResult` → compaction summarizes/truncates it (`compaction.rs:252-257`, `context-and-skills.md:64-66`). Multi-turn skill-guided tasks lose procedural fidelity after first compact.

Claude Rev solves with session registry + post-compact attachment (`compact.ts:1488-1534`).

---

## P0-1: `InvokedSkillRegistry`

**Location**: `core/agent-session/src/invoked_skills.rs` (new)

```rust
pub struct InvokedSkillInfo {
    pub skill_name: String,
    pub skill_path: PathBuf,
    pub content: String,
    pub invoked_at: u64,
    pub role: String,  // interaction_log role / "main"
}

pub struct InvokedSkillRegistry {
    skills: HashMap<String, InvokedSkillInfo>,  // key = "{role}:{name}"
    max_entries: usize,
}
```

**Hook**: `LoadSkillTool::execute` success (`load_skill.rs:150-159`) → `ctx.session.record_invoked_skill(...)`.

**Child sessions**: key by `ChildSessionInheritance` role from interaction log.

---

## P0-2: Post-compaction reinjection

**Location**: `compaction.rs` after `build_compaction_prompt` / before append `Compaction` entry.

Constants (match Claude Rev):
- `MAX_TOKENS_PER_SKILL = 5000`
- `TOTAL_BUDGET = 25000`
- Sort: most-recent-first
- Truncate: head + `...[truncated]`

**Delivery options** (pick one in impl):
1. New `SessionEntryKind::InvokedSkillsAttachment` in JSONL
2. User meta-message via `transform_context` on next turn

**Summarizer hygiene**: When compacting, strip or heavily truncate prior `load_skill` ToolResults if reinjection planned.

---

## P0-3: Resume restore

On `open_session` / history replay:
- Scan for `InvokedSkillsAttachment` entries OR
- Fallback: last N successful `load_skill` tool results

Rep populate registry.

---

## P0-4: Child session preload

**Location**: `core/agent-framework/src/session/mod.rs`

```rust
pub struct ChildSessionSpec {
    // existing fields...
    pub skills: Vec<String>,  // NEW: metadata preload like Claude runAgent.ts:577
}
```

In `build_child_session_prompt`: if `spec.skills` non-empty, append skill name+description block (not full body — use `load_skill` or inject truncated body under budget).

Also call `record_invoked_skill` for preloaded entries.

---

## P0-5: Observability

Extend interaction_log:
- `skill_load_invocation { name, path, remote_delegation, device }`
- `skill_compaction_preserved { count, tokens, truncated }`

---

## Acceptance criteria

1. Load skill → compact → next turn: agent still sees skill body (attachment or registry reinject).
2. Resume session after compact: registry restored from JSONL.
3. Child session with `skills: ["foo"]`: catalog includes foo metadata; compact preserves if loaded.
4. A-system `disable_workspace_skill_scan` + user prefix: no dual registry regression.

---

## Out of scope (P1+)

- `skill_manage` CRUD tool
- proposals/gates store
- GEPA offline PR
- MetaSkill DAG

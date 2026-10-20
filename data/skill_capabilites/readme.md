# Skill capabilities

Eight views of the same 19,716 public `SKILL.md` files. Each view is a tree. The leaf of a branch is one markdown file.

```
view/
  depth1/
    depth2/
      depth3.md
```

When a branch has no third cut, the leaf file sits at that depth: `depth1/depth2.md`, or `depth1.md`.

Source: the Skill capabilities page inside `benchmark-all-in-one.html` (`skill-capabilities.html`). Counted from the leaf file, 5 Oct 2026.

A skill is drawn once on every branch it belongs to. Job has 27,823 placements across 19,716 files; 6,273 files carry two or more jobs.

## How to read a leaf

- `named` is a name in the tree.
- `leftover` (`rest`, `none`, `unspecified`, `unbound`) means the parent matched and no named child did. A large leftover means the child list is short, not that the leftover is another kind of work.
- `clone` is a copied skill pack (`community--…`). It is where the count came from, not a capability.

Verification (5,243) and discovery (1,203) are word matches. Discovery’s named children, route and install, are the files that actually find or install a skill.

Ads trees stop at Programming, one Artificial Intelligence node, and Antivirus. The thick leftovers — software rest 9,012, ai rest 5,200 — are the part those lists do not name. `python`, `agent`, and `auth` stay on these ids.

## Views

| view | depth 1 | placements | |
|---|---:|---:|---|
| [job](job/readme.md) | 9 | 27,823 | Job · 工作. What the skill tells the agent to do. |
| [domain](domain/readme.md) | 27 | 59,373 | Domain · 主题. The subject the skill is about. |
| [form](form/readme.md) | 3 | 19,716 | Form · 形式. Whether the skill is a procedure, a judgment, or a lookup. |
| [artifact](artifact/readme.md) | 8 | 19,716 | Artifact · 产出. The file the skill must emit. |
| [binding](binding/readme.md) | 19 | 21,486 | Binding · 绑定. The product the skill names. |
| [audience](audience/readme.md) | 4 | 19,716 | Audience · 读者. Who the skill addresses. |
| [language](language/readme.md) | 5 | 19,716 | Language · 语言. The language the instructions are written in. |
| [provenance](provenance/readme.md) | 8 | 19,716 | Provenance · 来源. Which public pack the file was copied from. |

10,860 leaf files.

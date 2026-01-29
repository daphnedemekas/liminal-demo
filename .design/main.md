# Main

Two changes bundled together: (1) rebranding from "learning platform" to "long-term project companion," and (2) extracting `backend/main.py` into router modules with a new RichTextEditor component.

## Review

**Verdict:** Needs work

### 1. New router files and RichTextEditor are untracked — can't review the extraction

`backend/routers/` (2537 lines across 8 files) and `frontend/src/components/RichTextEditor.tsx` (339 lines) show as `??` in git status. The diff only shows ~2700 lines deleted from `backend/main.py`. The replacement code isn't staged, so the refactor is invisible to review. Stage these files so the full picture is diffable.

### 2. `backend/main.py` uses inline imports for HTTPException

Lines 178, 186, and 252 each do `from fastapi import HTTPException` inside a function body. These should be a single top-level import — the module already imports from `fastapi` at line 15.

### 3. Rebranding is consistent

"Learning path" → "Project path", "curriculum" → "roadmap", "teaching sessions" → "deep dives" across frontend, prompts, and welcome message. Pure string replacement, no logic changes. Looks complete across touched files.

### 4. Prompt teachability criteria are a real improvement

`analyze_assessment.txt` and `update_teaching_candidates.txt` add a "teachability test" requiring concepts to have a mechanism/principle, not just be labels. Good concrete examples (business terms excluded, mechanisms included). Substantive improvement to prompt quality.

### 5. CSS still has the classes TrajectoryPanel uses

Previous review flagged that `.mini-label`, `.mini-value`, `.teaching-steps-progress`, and `.steps-label` might have been removed from CSS. They weren't — they're still defined (lines 4869-4895 in `minimal.css`). No breakage here.

## Design notes

- Rebranding shifts Liminal from education-specific to general-purpose project support. The entire prompt system now frames things as "projects" and "journeys" rather than "curiosity" and "learning."
- Router extraction uses an `init_router(db)` pattern to pass dependencies at startup rather than global state. Clean separation into auth, discovery, teaching, feed, terminal, documents, trajectory modules.
- RichTextEditor uses TipTap/ProseMirror, adding `@tiptap/*` dependencies.
- The `.design/refactor.md` file (previous branch's design doc about prompt assembly/scheduler) was deleted — appropriate cleanup.

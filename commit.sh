#!/bin/bash
cd "D:\workspace\AI_tool\Agent-swam-task-4"
git add backend/api/tasks.py
git commit -m "fix: cleanup worktree on mark-as-done

When a task is manually marked as DONE via the mark-done endpoint,
also remove its git worktree and task branch to avoid leaving
orphaned worktrees in the filesystem.

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"

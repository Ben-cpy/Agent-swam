'use client';

/**
 * MentionTextarea
 *
 * A drop-in replacement for <Textarea> that adds @file autocomplete.
 * Type `@` followed by any characters to trigger a fuzzy file search
 * against the selected workspace.  The top matches are shown in a
 * floating dropdown positioned near the caret.
 *
 * Keyboard shortcuts inside the dropdown:
 *   ↑ / ↓   – navigate items
 *   Enter / Tab – confirm selection
 *   Escape  – dismiss
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type ChangeEvent,
} from 'react';
import { workspaceAPI } from '@/lib/api';
import { Textarea } from '@/components/ui/textarea';
import { cn } from '@/lib/utils';

// ---------------------------------------------------------------------------
// Caret pixel-position (mirror-div technique, no external deps)
// ---------------------------------------------------------------------------

const MIRROR_PROPS = [
  'direction', 'boxSizing',
  'width', 'height',
  'overflowX', 'overflowY',
  'borderTopWidth', 'borderRightWidth', 'borderBottomWidth', 'borderLeftWidth',
  'borderTopStyle', 'borderRightStyle', 'borderBottomStyle', 'borderLeftStyle',
  'paddingTop', 'paddingRight', 'paddingBottom', 'paddingLeft',
  'fontStyle', 'fontVariant', 'fontWeight', 'fontStretch', 'fontSize',
  'lineHeight', 'fontFamily',
  'textAlign', 'textTransform', 'textIndent', 'textDecoration',
  'letterSpacing', 'wordSpacing', 'tabSize',
] as const;

interface CaretCoords {
  top: number;
  left: number;
  lineHeight: number;
}

function getCaretCoords(ta: HTMLTextAreaElement): CaretCoords {
  const computed = window.getComputedStyle(ta);
  const div = document.createElement('div');

  MIRROR_PROPS.forEach((p) => div.style.setProperty(p, computed.getPropertyValue(p)));

  // Absolute off-screen so layout doesn't shift
  div.style.position = 'absolute';
  div.style.top = '-9999px';
  div.style.left = '-9999px';
  div.style.visibility = 'hidden';
  div.style.whiteSpace = 'pre-wrap';
  div.style.wordBreak = 'break-word';
  div.style.overflowX = 'hidden';

  const caret = ta.selectionStart ?? 0;
  div.appendChild(document.createTextNode(ta.value.slice(0, caret)));

  // Span marks the exact caret position
  const span = document.createElement('span');
  span.textContent = '\u200b'; // zero-width space — gives the span real dimensions
  div.appendChild(span);

  // Remaining text is required so wrapping matches the real textarea
  div.appendChild(document.createTextNode(ta.value.slice(caret) || ' '));

  document.body.appendChild(div);

  const spanRect = span.getBoundingClientRect();
  const taRect = ta.getBoundingClientRect();

  document.body.removeChild(div);

  const lh = parseFloat(computed.lineHeight);

  return {
    top: spanRect.top - taRect.top + ta.scrollTop,
    left: spanRect.left - taRect.left,
    lineHeight: Number.isFinite(lh) ? lh : 20,
  };
}

// ---------------------------------------------------------------------------
// Debounce hook
// ---------------------------------------------------------------------------

function useDebounce<Args extends unknown[]>(
  fn: (...args: Args) => void,
  delay: number,
): (...args: Args) => void {
  const timerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  return useCallback(
    (...args: Args) => {
      clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => fn(...args), delay);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [fn, delay],
  );
}

// ---------------------------------------------------------------------------
// State types
// ---------------------------------------------------------------------------

interface MentionState {
  active: boolean;
  query: string;
  /** Index of `@` in the textarea value */
  atIndex: number;
  files: string[];
  selectedIdx: number;
  coords: CaretCoords | null;
}

const IDLE: MentionState = {
  active: false,
  query: '',
  atIndex: -1,
  files: [],
  selectedIdx: 0,
  coords: null,
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export interface MentionTextareaProps
  extends Omit<React.ComponentPropsWithoutRef<'textarea'>, 'onChange'> {
  value: string;
  onChange: (value: string) => void;
  /** If provided, file search is enabled against this workspace. */
  workspaceId?: number;
  /** Optional task ID for searching files in task's worktree instead of workspace root. */
  taskId?: number;
}

export function MentionTextarea({
  value,
  onChange,
  workspaceId,
  taskId,
  className,
  ...rest
}: MentionTextareaProps) {
  const taRef = useRef<HTMLTextAreaElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [mention, setMention] = useState<MentionState>(IDLE);

  // ------------------------------------------------------------------
  // Fetch suggestions from backend
  // ------------------------------------------------------------------

  const fetchFiles = useCallback(
    async (query: string, atIndex: number) => {
      if (!workspaceId) return;
      try {
        const res = await workspaceAPI.listFiles(workspaceId, query, 8, taskId);
        setMention((prev) => {
          // Guard: discard stale responses if the user moved on
          if (!prev.active || prev.atIndex !== atIndex) return prev;
          return { ...prev, files: res.data, selectedIdx: 0 };
        });
      } catch {
        // silently ignore network errors
      }
    },
    [workspaceId, taskId],
  );

  const debouncedFetch = useDebounce(fetchFiles, 180);

  // ------------------------------------------------------------------
  // Helpers
  // ------------------------------------------------------------------

  const dismiss = useCallback(() => setMention(IDLE), []);

  const insertFile = useCallback(
    (filePath: string) => {
      const ta = taRef.current;
      if (!ta) return;

      const { atIndex } = mention;
      const cursor = ta.selectionStart ?? value.length;

      // Replace `@<query>` with `@<filePath>`
      const newValue = value.slice(0, atIndex) + '@' + filePath + value.slice(cursor);
      onChange(newValue);
      dismiss();

      // Restore focus with cursor placed right after the inserted path
      const newCursor = atIndex + 1 + filePath.length;
      setTimeout(() => {
        ta.focus();
        ta.setSelectionRange(newCursor, newCursor);
      }, 0);
    },
    [value, onChange, mention, dismiss],
  );

  // ------------------------------------------------------------------
  // Event handlers
  // ------------------------------------------------------------------

  const handleChange = useCallback(
    (e: ChangeEvent<HTMLTextAreaElement>) => {
      const newValue = e.target.value;
      onChange(newValue);

      if (!workspaceId) return;

      const cursor = e.target.selectionStart ?? newValue.length;
      const textBefore = newValue.slice(0, cursor);
      const atIdx = textBefore.lastIndexOf('@');

      if (atIdx !== -1) {
        const afterAt = textBefore.slice(atIdx + 1);
        // Valid mention trigger: no whitespace after `@`, and not too long
        if (afterAt.length <= 100 && !/[\s\n]/.test(afterAt)) {
          const coords = taRef.current ? getCaretCoords(taRef.current) : null;
          setMention((prev) => ({
            ...prev,
            active: true,
            query: afterAt,
            atIndex: atIdx,
            coords,
            selectedIdx: 0,
          }));
          debouncedFetch(afterAt, atIdx);
          return;
        }
      }

      dismiss();
    },
    [onChange, workspaceId, debouncedFetch, dismiss],
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (!mention.active || mention.files.length === 0) return;

      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setMention((prev) => ({
            ...prev,
            selectedIdx: Math.min(prev.selectedIdx + 1, prev.files.length - 1),
          }));
          break;
        case 'ArrowUp':
          e.preventDefault();
          setMention((prev) => ({
            ...prev,
            selectedIdx: Math.max(prev.selectedIdx - 1, 0),
          }));
          break;
        case 'Enter':
        case 'Tab':
          if (mention.files[mention.selectedIdx]) {
            e.preventDefault();
            insertFile(mention.files[mention.selectedIdx]);
          }
          break;
        case 'Escape':
          e.preventDefault();
          dismiss();
          break;
      }
    },
    [mention, insertFile, dismiss],
  );

  // Dismiss when clicking outside container
  useEffect(() => {
    if (!mention.active) return;
    const handler = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) dismiss();
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [mention.active, dismiss]);

  // ------------------------------------------------------------------
  // Dropdown position
  // ------------------------------------------------------------------

  const dropdownStyle: React.CSSProperties = {};
  if (mention.coords) {
    const { top, left, lineHeight } = mention.coords;
    // Clamp left so it doesn't overflow the container
    dropdownStyle.top = top + lineHeight + 2; // 2px gap below caret line
    dropdownStyle.left = Math.max(0, left);
  }

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  return (
    <div ref={containerRef} className="relative">
      <Textarea
        ref={taRef}
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        className={className}
        {...rest}
      />

      {/* Hint shown when `@` is typed but workspace isn't selected */}
      {mention.active && !workspaceId && (
        <div className="absolute z-50 left-0 mt-1 px-3 py-2 rounded-md border bg-popover text-sm text-muted-foreground shadow-md">
          Select a workspace to enable file suggestions
        </div>
      )}

      {/* File suggestion dropdown */}
      {mention.active && workspaceId && mention.files.length > 0 && (
        <ul
          role="listbox"
          aria-label="File suggestions"
          className="absolute z-50 min-w-[260px] max-w-[520px] rounded-md border bg-popover shadow-lg overflow-hidden py-1"
          style={dropdownStyle}
        >
          {mention.files.map((file, idx) => {
            const isSelected = idx === mention.selectedIdx;
            const dir = file.includes('/') ? file.slice(0, file.lastIndexOf('/') + 1) : '';
            const base = file.includes('/') ? file.slice(file.lastIndexOf('/') + 1) : file;

            return (
              <li
                key={file}
                role="option"
                aria-selected={isSelected}
                className={cn(
                  'flex items-center gap-2 px-3 py-1.5 text-sm cursor-pointer select-none',
                  isSelected
                    ? 'bg-accent text-accent-foreground'
                    : 'text-popover-foreground hover:bg-accent hover:text-accent-foreground',
                )}
                onMouseDown={(e) => {
                  e.preventDefault(); // keep textarea focused
                  insertFile(file);
                }}
                onMouseEnter={() =>
                  setMention((prev) => ({ ...prev, selectedIdx: idx }))
                }
              >
                <FileIcon className="w-3.5 h-3.5 shrink-0 text-muted-foreground" />
                <span className="truncate">
                  {dir && (
                    <span className="text-muted-foreground">{dir}</span>
                  )}
                  <span className="font-medium">{base}</span>
                </span>
              </li>
            );
          })}
          <li className="px-3 py-1 text-[11px] text-muted-foreground border-t bg-muted/30 select-none">
            ↑↓ navigate &nbsp;·&nbsp; Enter / Tab to insert &nbsp;·&nbsp; Esc to dismiss
          </li>
        </ul>
      )}

      {/* Empty-state hint when typing a query but no results yet */}
      {mention.active && workspaceId && mention.query.length > 0 && mention.files.length === 0 && (
        <div
          className="absolute z-50 px-3 py-2 rounded-md border bg-popover text-sm text-muted-foreground shadow-md"
          style={dropdownStyle}
        >
          No files match <span className="font-mono">@{mention.query}</span>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tiny inline SVG file icon (avoids extra import)
// ---------------------------------------------------------------------------

function FileIcon({ className }: { className?: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
    </svg>
  );
}

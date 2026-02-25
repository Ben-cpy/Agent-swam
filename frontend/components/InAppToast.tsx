'use client';

import { useEffect, useState, useCallback } from 'react';
import { X } from 'lucide-react';

export interface ToastMessage {
  id: string;
  title: string;
  body: string;
  type: 'success' | 'error' | 'info';
  taskId?: number;
}

const AUTO_CLOSE_MS = 8000;

// Global event name used to push toasts from anywhere in the app
export const IN_APP_TOAST_EVENT = 'in-app-toast';

export function pushInAppToast(msg: Omit<ToastMessage, 'id'>) {
  if (typeof window === 'undefined') return;
  window.dispatchEvent(
    new CustomEvent(IN_APP_TOAST_EVENT, {
      detail: { ...msg, id: `${Date.now()}-${Math.random()}` },
    })
  );
}

export default function InAppToast() {
  const [toasts, setToasts] = useState<ToastMessage[]>([]);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  useEffect(() => {
    const handler = (e: Event) => {
      const toast = (e as CustomEvent<ToastMessage>).detail;
      setToasts((prev) => [...prev, toast]);
      setTimeout(() => dismiss(toast.id), AUTO_CLOSE_MS);
    };
    window.addEventListener(IN_APP_TOAST_EVENT, handler);
    return () => window.removeEventListener(IN_APP_TOAST_EVENT, handler);
  }, [dismiss]);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm w-full pointer-events-none">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`
            flex items-start gap-3 p-3 rounded-lg shadow-lg border pointer-events-auto
            transition-all duration-300
            ${toast.type === 'error'
              ? 'bg-red-50 border-red-200 text-red-900'
              : toast.type === 'success'
              ? 'bg-green-50 border-green-200 text-green-900'
              : 'bg-white border-slate-200 text-slate-900'}
          `}
        >
          <div
            className="flex-1 min-w-0 cursor-pointer"
            onClick={() => {
              if (toast.taskId) window.location.href = `/tasks/${toast.taskId}`;
              dismiss(toast.id);
            }}
          >
            <p className="text-sm font-semibold">{toast.title}</p>
            <p className="text-xs text-current opacity-75 truncate">{toast.body}</p>
          </div>
          <button
            onClick={() => dismiss(toast.id)}
            className="flex-shrink-0 opacity-50 hover:opacity-100 transition-opacity"
            aria-label="Dismiss"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      ))}
    </div>
  );
}

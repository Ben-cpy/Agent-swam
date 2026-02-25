'use client';

import { useEffect, useMemo, useState, useRef } from 'react';
import useSWR from 'swr';
import { taskAPI } from '@/lib/api';
import { Task, TaskStatus } from '@/lib/types';
import {
  getTaskCompletionNotificationEnabled,
  TASK_COMPLETION_NOTIFICATION_ENABLED_KEY,
  TASK_COMPLETION_NOTIFICATION_SETTING_EVENT,
} from '@/lib/reviewNotificationSettings';
import { pushInAppToast } from '@/components/InAppToast';

const NOTIFICATION_PERMISSION_KEY = 'task_completion_notification_permission_requested_v1';
const POLL_INTERVAL_MS = 2000;
const AUTO_CLOSE_MS = 10000;
const COMPLETION_STATUSES = new Set<TaskStatus>([
  TaskStatus.TO_BE_REVIEW,
  TaskStatus.DONE,
  TaskStatus.FAILED,
]);

function isCompletionStatus(status: TaskStatus): boolean {
  return COMPLETION_STATUSES.has(status);
}

function openTaskPage(taskId: number) {
  window.focus();
  window.location.href = `/tasks/${taskId}`;
}

function getNotificationTitle(task: Task): string {
  if (task.status === TaskStatus.FAILED) {
    return 'Task Failed';
  }
  if (task.status === TaskStatus.DONE) {
    return 'Task Done';
  }
  return 'Task Ready For Review';
}

function getNotificationBody(task: Task): string {
  if (task.status === TaskStatus.FAILED) {
    return `#${task.id} ${task.title}`;
  }
  if (task.status === TaskStatus.DONE) {
    return `#${task.id} ${task.title}`;
  }
  return `#${task.id} ${task.title}`;
}

function showCompletionNotification(task: Task) {
  // Always fire in-app toast regardless of browser notification permission
  pushInAppToast({
    title: getNotificationTitle(task),
    body: getNotificationBody(task),
    type: task.status === TaskStatus.FAILED ? 'error' : 'success',
    taskId: task.id,
  });

  // Also fire browser notification if permission is granted
  if (!('Notification' in window) || Notification.permission !== 'granted') return;

  const notification = new Notification(getNotificationTitle(task), {
    body: getNotificationBody(task),
    tag: `task-completion-${task.id}`,
    silent: true,
  });

  notification.onclick = () => {
    openTaskPage(task.id);
    notification.close();
  };

  window.setTimeout(() => notification.close(), AUTO_CLOSE_MS);
}

function requestNotificationPermissionOnce() {
  if (!('Notification' in window)) return;
  if (Notification.permission !== 'default') return;
  if (window.localStorage.getItem(NOTIFICATION_PERMISSION_KEY) === '1') return;

  window.localStorage.setItem(NOTIFICATION_PERMISSION_KEY, '1');
  void Notification.requestPermission();
}

export default function TaskCompletionNotifier() {
  const previousStatusByTask = useRef<Map<number, TaskStatus>>(new Map());
  const initialized = useRef(false);
  const [notificationsEnabled, setNotificationsEnabled] = useState<boolean | null>(null);

  const { data } = useSWR(
    notificationsEnabled ? '/tasks/completion-notifier' : null,
    () => taskAPI.list(),
    { refreshInterval: POLL_INTERVAL_MS, revalidateOnFocus: true }
  );
  const tasks = useMemo(() => data?.data ?? [], [data?.data]);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const syncEnabled = () => {
      setNotificationsEnabled(getTaskCompletionNotificationEnabled());
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === TASK_COMPLETION_NOTIFICATION_ENABLED_KEY) {
        syncEnabled();
      }
    };

    syncEnabled();
    window.addEventListener(TASK_COMPLETION_NOTIFICATION_SETTING_EVENT, syncEnabled);
    window.addEventListener('storage', onStorage);

    return () => {
      window.removeEventListener(TASK_COMPLETION_NOTIFICATION_SETTING_EVENT, syncEnabled);
      window.removeEventListener('storage', onStorage);
    };
  }, []);

  useEffect(() => {
    if (!notificationsEnabled) {
      previousStatusByTask.current.clear();
      initialized.current = false;
      return;
    }

    requestNotificationPermissionOnce();
  }, [notificationsEnabled]);

  useEffect(() => {
    if (!notificationsEnabled) return;

    const previousMap = previousStatusByTask.current;

    if (!initialized.current) {
      tasks.forEach((task) => previousMap.set(task.id, task.status));
      initialized.current = true;
      return;
    }

    const transitionedTasks = tasks.filter((task) => {
      const previousStatus = previousMap.get(task.id);
      if (!isCompletionStatus(task.status)) return false;
      if (previousStatus == null) return true;
      return !isCompletionStatus(previousStatus);
    });

    if (transitionedTasks.length > 0) {
      transitionedTasks.forEach((task) => {
        showCompletionNotification(task);
      });
    }

    previousMap.clear();
    tasks.forEach((task) => previousMap.set(task.id, task.status));
  }, [notificationsEnabled, tasks]);

  return null;
}

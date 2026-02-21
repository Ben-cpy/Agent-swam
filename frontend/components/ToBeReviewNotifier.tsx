'use client';

import { useEffect, useMemo, useState, useRef } from 'react';
import useSWR from 'swr';
import { taskAPI } from '@/lib/api';
import { Task, TaskStatus } from '@/lib/types';
import {
  getReviewNotificationEnabled,
  REVIEW_NOTIFICATION_ENABLED_KEY,
  REVIEW_NOTIFICATION_SETTING_EVENT,
} from '@/lib/reviewNotificationSettings';

const NOTIFICATION_PERMISSION_KEY = 'review_notification_permission_requested_v1';
const POLL_INTERVAL_MS = 2000;
const AUTO_CLOSE_MS = 10000;

function openTaskPage(taskId: number) {
  window.focus();
  window.location.href = `/tasks/${taskId}`;
}

function showReviewNotification(task: Task) {
  const notification = new Notification('Task Ready For Review', {
    body: `#${task.id} ${task.title}`,
    tag: `task-review-${task.id}`,
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

export default function ToBeReviewNotifier() {
  const previousStatusByTask = useRef<Map<number, TaskStatus>>(new Map());
  const initialized = useRef(false);
  const [notificationsEnabled, setNotificationsEnabled] = useState<boolean | null>(null);

  const { data } = useSWR(
    notificationsEnabled ? '/tasks/review-notifier' : null,
    () => taskAPI.list(),
    { refreshInterval: POLL_INTERVAL_MS, revalidateOnFocus: true }
  );
  const tasks = useMemo(() => data?.data ?? [], [data?.data]);

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const syncEnabled = () => {
      setNotificationsEnabled(getReviewNotificationEnabled());
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === REVIEW_NOTIFICATION_ENABLED_KEY) {
        syncEnabled();
      }
    };

    syncEnabled();
    window.addEventListener(REVIEW_NOTIFICATION_SETTING_EVENT, syncEnabled);
    window.addEventListener('storage', onStorage);

    return () => {
      window.removeEventListener(REVIEW_NOTIFICATION_SETTING_EVENT, syncEnabled);
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
      if (task.status !== TaskStatus.TO_BE_REVIEW) return false;
      if (previousStatus == null) return true;
      return previousStatus !== TaskStatus.TO_BE_REVIEW;
    });

    if (transitionedTasks.length > 0 && 'Notification' in window) {
      transitionedTasks.forEach((task) => {
        if (Notification.permission === 'granted') {
          showReviewNotification(task);
          return;
        }

        if (Notification.permission === 'default') {
          void Notification.requestPermission().then((permission) => {
            if (permission === 'granted') {
              showReviewNotification(task);
            }
          });
        }
      });
    }

    previousMap.clear();
    tasks.forEach((task) => previousMap.set(task.id, task.status));
  }, [notificationsEnabled, tasks]);

  return null;
}

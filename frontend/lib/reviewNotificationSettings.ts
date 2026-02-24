export const TASK_COMPLETION_NOTIFICATION_ENABLED_KEY = 'review_notification_enabled_v1';
export const TASK_COMPLETION_NOTIFICATION_SETTING_EVENT = 'review-notification-setting-changed';

export function getTaskCompletionNotificationEnabled(): boolean {
  if (typeof window === 'undefined') {
    return true;
  }
  return window.localStorage.getItem(TASK_COMPLETION_NOTIFICATION_ENABLED_KEY) !== '0';
}

export function setTaskCompletionNotificationEnabled(enabled: boolean) {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(TASK_COMPLETION_NOTIFICATION_ENABLED_KEY, enabled ? '1' : '0');
  window.dispatchEvent(new Event(TASK_COMPLETION_NOTIFICATION_SETTING_EVENT));
}

// Backward-compatible exports for older imports/usages.
export const REVIEW_NOTIFICATION_ENABLED_KEY = TASK_COMPLETION_NOTIFICATION_ENABLED_KEY;
export const REVIEW_NOTIFICATION_SETTING_EVENT = TASK_COMPLETION_NOTIFICATION_SETTING_EVENT;
export const getReviewNotificationEnabled = getTaskCompletionNotificationEnabled;
export const setReviewNotificationEnabled = setTaskCompletionNotificationEnabled;

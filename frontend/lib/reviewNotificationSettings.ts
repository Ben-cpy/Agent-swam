export const REVIEW_NOTIFICATION_ENABLED_KEY = 'review_notification_enabled_v1';
export const REVIEW_NOTIFICATION_SETTING_EVENT = 'review-notification-setting-changed';

export function getReviewNotificationEnabled(): boolean {
  if (typeof window === 'undefined') {
    return true;
  }
  return window.localStorage.getItem(REVIEW_NOTIFICATION_ENABLED_KEY) !== '0';
}

export function setReviewNotificationEnabled(enabled: boolean) {
  if (typeof window === 'undefined') {
    return;
  }
  window.localStorage.setItem(REVIEW_NOTIFICATION_ENABLED_KEY, enabled ? '1' : '0');
  window.dispatchEvent(new Event(REVIEW_NOTIFICATION_SETTING_EVENT));
}

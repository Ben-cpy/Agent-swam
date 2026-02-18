import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Parse a timestamp from the backend as UTC.
 * Backend may return naive datetime strings (without 'Z' or offset).
 * This function ensures they are always interpreted as UTC.
 */
export function parseUTCDate(timestamp: string): Date {
  if (!timestamp) return new Date();
  // If the timestamp already has timezone info, parse directly
  if (timestamp.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(timestamp)) {
    return new Date(timestamp);
  }
  // Append 'Z' to treat naive timestamps as UTC
  return new Date(timestamp + 'Z');
}

import { formatDistanceToNow } from 'date-fns';
import { ko } from 'date-fns/locale';

export function relativeTime(value?: number | string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  return isNaN(date.getTime()) ? '-' : formatDistanceToNow(date, { addSuffix: true, locale: ko });
}

import { useState, useEffect, useCallback } from 'react';
import { fetchJson, fetchIndex } from '../config/api';
import { MonthlyDigestRecord, ParsedDigestItem } from '../types';
import { parseDigestItems, parseCompiledHtml } from '../utils/digestParser';

interface UseMonthlySummaryReturn {
  /** Currently displayed month (YYYY-MM) */
  currentMonth: string | null;
  /** Parsed items ready for rendering */
  items: ParsedDigestItem[];
  /** Raw monthly record (data/monthly/<month>.json) */
  record: MonthlyDigestRecord | null;
  /** Whether data is loading */
  loading: boolean;
  /** Error message if fetch failed */
  error: string | null;
  /** All available months sorted descending (most recent first) */
  allMonths: string[];
  /** Navigate to the previous (older) month */
  goBack: () => void;
  /** Navigate to the next (more recent) month */
  goForward: () => void;
  /** Whether back navigation is possible */
  canGoBack: boolean;
  /** Whether forward navigation is possible */
  canGoForward: boolean;
  /** Refresh current + list of months */
  refresh: () => Promise<void>;
}

/**
 * Loads Monthly Summary digests from the static site data. Mirrors useDigest, but keyed
 * by calendar month (YYYY-MM) instead of day, with no "today" concept —
 * the most recently published month is shown by default.
 */
export function useMonthlySummary(): UseMonthlySummaryReturn {
  const [currentMonth, setCurrentMonth] = useState<string | null>(null);
  const [record, setRecord] = useState<MonthlyDigestRecord | null>(null);
  const [items, setItems] = useState<ParsedDigestItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [allMonths, setAllMonths] = useState<string[]>([]);

  const fetchAllMonths = useCallback(async (): Promise<string[]> => {
    try {
      const index = await fetchIndex();
      const months = [...(index?.months ?? [])].sort((a, b) => b.localeCompare(a));
      setAllMonths(months);
      return months;
    } catch (e) {
      console.warn('fetchAllMonths error:', e);
      return [];
    }
  }, []);

  const fetchMonth = useCallback(async (monthStr: string) => {
    setLoading(true);
    setError(null);

    try {
      const rec = await fetchJson<MonthlyDigestRecord>(`data/monthly/${monthStr}.json`);

      if (!rec) {
        setError('No monthly summary available for this month yet.');
        setItems([]);
        setRecord(null);
        return;
      }

      setRecord(rec);

      let parsed: ParsedDigestItem[];
      if (rec.items && Array.isArray(rec.items) && rec.items.length > 0) {
        parsed = parseDigestItems(rec.items);
      } else if (rec.compiled) {
        parsed = parseCompiledHtml(rec.compiled);
      } else {
        parsed = [];
      }
      setItems(parsed);
    } catch (e: any) {
      setError(e?.message ?? 'Unknown error fetching monthly summary');
      setItems([]);
      setRecord(null);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load: fetch the list of months, then show the most recent one.
  useEffect(() => {
    (async () => {
      const months = await fetchAllMonths();
      if (months.length > 0) {
        setCurrentMonth(months[0]);
      } else {
        setLoading(false);
        setError('No monthly summaries have been published yet.');
      }
    })();
  }, [fetchAllMonths]);

  // Refetch when the selected month changes.
  useEffect(() => {
    if (currentMonth) {
      fetchMonth(currentMonth);
    }
  }, [currentMonth, fetchMonth]);

  const currentIndex = currentMonth ? allMonths.indexOf(currentMonth) : -1;
  const canGoBack = allMonths.length > 0 && currentIndex >= 0 && currentIndex < allMonths.length - 1;
  const canGoForward = allMonths.length > 0 && currentIndex > 0;

  const goBack = useCallback(() => {
    if (!canGoBack) return;
    const nextMonth = allMonths[currentIndex + 1];
    if (nextMonth) setCurrentMonth(nextMonth);
  }, [allMonths, currentIndex, canGoBack]);

  const goForward = useCallback(() => {
    if (!canGoForward) return;
    const nextMonth = allMonths[currentIndex - 1];
    if (nextMonth) setCurrentMonth(nextMonth);
  }, [allMonths, currentIndex, canGoForward]);

  const refresh = useCallback(async () => {
    const months = await fetchAllMonths();
    const target = currentMonth && months.includes(currentMonth) ? currentMonth : months[0] ?? null;
    if (target) {
      await fetchMonth(target);
      setCurrentMonth(target);
    }
  }, [currentMonth, fetchAllMonths, fetchMonth]);

  return {
    currentMonth,
    items,
    record,
    loading,
    error,
    allMonths,
    goBack,
    goForward,
    canGoBack,
    canGoForward,
    refresh,
  };
}

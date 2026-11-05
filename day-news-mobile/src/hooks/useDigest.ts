import { useState, useEffect, useCallback, useRef } from 'react';
import { fetchJson, fetchIndex } from '../config/api';
import { DigestRecord, ParsedDigestItem } from '../types';
import { parseDigestItems, parseCompiledHtml } from '../utils/digestParser';
import {
  getDisplayDateUTC,
  isBeforeSixTwentyFiveUTC,
  msUntilNextUTCMidnight,
  msUntilNextUTC625,
} from '../utils/dateUtils';

interface UseDigestReturn {
  /** Currently displayed date (YYYY-MM-DD) */
  currentDate: string;
  /** Parsed items ready for rendering */
  items: ParsedDigestItem[];
  /** Raw daily record (data/daily/<date>.json) */
  record: DigestRecord | null;
  /** Whether data is loading */
  loading: boolean;
  /** Error message if fetch failed */
  error: string | null;
  /** Whether we're viewing today (or auto-selected date) */
  isToday: boolean;
  /** All available dates sorted descending */
  allDates: string[];
  /** Navigate to previous day */
  goBack: () => void;
  /** Navigate to next day */
  goForward: () => void;
  /** Jump back to today */
  goToday: () => void;
  /** Whether back navigation is possible */
  canGoBack: boolean;
  /** Whether forward navigation is possible */
  canGoForward: boolean;
  /** Refresh current digest */
  refresh: () => Promise<void>;
}

export function useDigest(): UseDigestReturn {
  const displayDate = getDisplayDateUTC();
  const [currentDate, setCurrentDate] = useState<string>(displayDate);
  const [record, setRecord] = useState<DigestRecord | null>(null);
  const [items, setItems] = useState<ParsedDigestItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [allDates, setAllDates] = useState<string[]>([]);
  const [isToday, setIsToday] = useState(true);
  const refreshTimers = useRef<ReturnType<typeof setTimeout>[]>([]);

  // Fetch all available dates
  const fetchAllDates = useCallback(async () => {
    try {
      const index = await fetchIndex();
      if (index) setAllDates([...index.dates].sort((a, b) => b.localeCompare(a)));
    } catch (e) {
      console.warn('fetchAllDates error:', e);
    }
  }, []);

  // Fetch a specific day's digest
  const fetchDigest = useCallback(async (dateStr: string) => {
    setLoading(true);
    setError(null);

    try {
      const rec = await fetchJson<DigestRecord>(`data/daily/${dateStr}.json`);

      if (!rec) {
        const label = isBeforeSixTwentyFiveUTC()
          ? 'yesterday'
          : 'today';
        setError(`No summary available for ${label} yet.`);
        setItems([]);
        setRecord(null);
        return;
      }

      setRecord(rec);

      // Prefer structured items; fall back to parsing compiled HTML
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
      setError(e?.message ?? 'Unknown error fetching digest');
      setItems([]);
      setRecord(null);
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial load & refresh scheduling
  useEffect(() => {
    fetchAllDates();
    fetchDigest(currentDate);

    // Schedule automatic refreshes at UTC midnight and 06:25 UTC
    const midnightTimeout = setTimeout(() => {
      const newDate = getDisplayDateUTC();
      setCurrentDate(newDate);
      setIsToday(true);
      fetchDigest(newDate);
      fetchAllDates();
    }, msUntilNextUTCMidnight());

    const utc625Timeout = setTimeout(() => {
      const newDate = getDisplayDateUTC();
      setCurrentDate(newDate);
      setIsToday(true);
      fetchDigest(newDate);
      fetchAllDates();
    }, msUntilNextUTC625());

    refreshTimers.current = [midnightTimeout, utc625Timeout];

    return () => {
      refreshTimers.current.forEach(clearTimeout);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Refetch when date changes
  useEffect(() => {
    fetchDigest(currentDate);
  }, [currentDate, fetchDigest]);

  const currentIndex = allDates.indexOf(currentDate);
  const canGoBack = allDates.length > 0 && currentIndex < allDates.length - 1;
  const canGoForward = !isToday && currentIndex > 0;

  const goBack = useCallback(() => {
    if (!canGoBack) return;
    const nextDate = allDates[currentIndex + 1];
    if (nextDate) {
      setCurrentDate(nextDate);
      setIsToday(false);
    }
  }, [allDates, currentIndex, canGoBack]);

  const goForward = useCallback(() => {
    if (!canGoForward) return;
    const nextDate = allDates[currentIndex - 1];
    if (nextDate) {
      const today = getDisplayDateUTC();
      if (nextDate === today) {
        setCurrentDate(today);
        setIsToday(true);
      } else {
        setCurrentDate(nextDate);
        setIsToday(false);
      }
    }
  }, [allDates, currentIndex, canGoForward]);

  const goToday = useCallback(() => {
    const today = getDisplayDateUTC();
    setCurrentDate(today);
    setIsToday(true);
  }, []);

  const refresh = useCallback(async () => {
    await fetchAllDates();
    await fetchDigest(currentDate);
  }, [currentDate, fetchAllDates, fetchDigest]);

  return {
    currentDate,
    items,
    record,
    loading,
    error,
    isToday,
    allDates,
    goBack,
    goForward,
    goToday,
    canGoBack,
    canGoForward,
    refresh,
  };
}

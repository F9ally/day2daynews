import { useState, useCallback, useRef, useEffect } from 'react';
import { createAudioPlayer, setAudioModeAsync, AudioPlayer } from 'expo-audio';
import { DATA_BASE_URL, fetchIndex } from '../config/api';

interface UseAudioReturn {
  isPlaying: boolean;
  isLoading: boolean;
  audioUnavailable: boolean;
  play: () => Promise<void>;
  pause: () => void;
  toggle: () => Promise<void>;
  stop: () => void;
  dismissUnavailable: () => void;
  retryPlay: () => Promise<void>;
}

export function useAudio(identifier: string, kind: 'daily' | 'monthly' = 'daily'): UseAudioReturn {
  const [isPlaying, setIsPlaying] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [audioUnavailable, setAudioUnavailable] = useState(false);
  const playerRef = useRef<AudioPlayer | null>(null);
  const currentKeyRef = useRef(`${kind}:${identifier}`);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (playerRef.current) {
        playerRef.current.pause();
        playerRef.current.remove();
        playerRef.current = null;
      }
    };
  }, []);

  // Stop when the identifier (date or month) or kind changes
  useEffect(() => {
    const key = `${kind}:${identifier}`;
    if (currentKeyRef.current !== key) {
      if (playerRef.current) {
        playerRef.current.pause();
        playerRef.current.remove();
        playerRef.current = null;
      }
      setIsPlaying(false);
      setIsLoading(false);
      currentKeyRef.current = key;
    }
  }, [identifier, kind]);

  // Only the latest daily and monthly narration is kept on the site; data/index.json says which.
  const getAudioUrl = useCallback(async (): Promise<string | null> => {
    const index = await fetchIndex();
    const entry = index?.audio?.[kind];
    return entry && entry.key === identifier ? `${DATA_BASE_URL}/${entry.file}` : null;
  }, [identifier, kind]);

  const play = useCallback(async () => {
    try {
      // Set audio mode using the standalone function (not Audio.setAudioModeAsync)
      await setAudioModeAsync({
        playsInSilentMode: true,
        shouldPlayInBackground: true,
      });

      // If we already have a player for the same identifier, just resume
      if (playerRef.current && currentKeyRef.current === `${kind}:${identifier}`) {
        if (!playerRef.current.playing) {
          playerRef.current.play();
          setIsPlaying(true);
          return;
        }
        return;
      }

      setIsLoading(true);
      let url: string | null = null;
      try {
        url = await getAudioUrl();
      } catch {
        // network error: treated as unavailable below
      }
      if (!url) {
        setAudioUnavailable(true);
        return;
      }

      // Release previous player
      if (playerRef.current) {
        playerRef.current.pause();
        playerRef.current.remove();
        playerRef.current = null;
      }

      // Create new player with the URL
      const player = createAudioPlayer(url);
      playerRef.current = player;

      // Listen for playback status changes
      player.addListener('playbackStatusUpdate', (status) => {
        setIsPlaying(status.playing);
        if (status.didJustFinish) {
          setIsPlaying(false);
        }
      });

      player.play();
      setIsPlaying(true);
    } catch (e) {
      console.warn('Audio play failed:', e);
      setAudioUnavailable(true);
      setIsPlaying(false);
    } finally {
      setIsLoading(false);
    }
  }, [identifier, kind, getAudioUrl]);

  const pause = useCallback(() => {
    if (playerRef.current) {
      playerRef.current.pause();
      setIsPlaying(false);
    }
  }, []);

  const stop = useCallback(() => {
    if (playerRef.current) {
      playerRef.current.pause();
      playerRef.current.remove();
      playerRef.current = null;
    }
    setIsPlaying(false);
  }, []);

  const toggle = useCallback(async () => {
    if (isPlaying) {
      pause();
    } else {
      await play();
    }
  }, [isPlaying, pause, play]);

  const dismissUnavailable = useCallback(() => {
    setAudioUnavailable(false);
  }, []);

  const retryPlay = useCallback(async () => {
    setAudioUnavailable(false);
    await play();
  }, [play]);

  return {
    isPlaying,
    isLoading,
    audioUnavailable,
    play,
    pause,
    toggle,
    stop,
    dismissUnavailable,
    retryPlay,
  };
}

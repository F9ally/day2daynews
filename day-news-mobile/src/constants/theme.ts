import { ThemeColors } from '../types';

export const LIGHT_THEME: ThemeColors = {
  background: '#f9f9f9',
  surface: '#ffffff',
  text: '#222222',
  textSecondary: '#777777',
  accent: '#4285f4',
  accentLight: '#e8f0fe',
  accentHover: '#d2e3fc',
  border: '#cccccc',
  cardShadow: 'rgba(0,0,0,0.05)',
  headerText: '#111111',
  dateText: '#777777',
  linkText: '#4285f4',
  iconColor: '#4285f4',
  buttonBg: '#e8f0fe',
  buttonBgActive: '#d2e3fc',
  buttonShadow: 'rgba(66,133,244,0.06)',
};

export const DARK_THEME: ThemeColors = {
  background: '#0f1419',
  surface: '#161b22',
  text: '#e6edf3',
  textSecondary: '#9aa4b2',
  accent: '#8ab4f8',
  accentLight: '#1f2a37',
  accentHover: '#263244',
  border: '#444444',
  cardShadow: 'rgba(0,0,0,0.40)',
  headerText: '#e6edf3',
  dateText: '#9aa4b2',
  linkText: '#8ab4f8',
  iconColor: '#8ab4f8',
  buttonBg: '#1f2a37',
  buttonBgActive: '#263244',
  buttonShadow: 'rgba(0,0,0,0.40)',
};

export const TOPIC_EMOJIS: Record<string, string> = {
  general: '📰',
  world: '🌍',
  us: '🦅',
  business: '💰',
  technology: '💻',
  entertainment: '🎭',
  sports: '🏅',
  science: '🔬',
  health: '🩺',
};

export const FONT_SIZE_BASE = 16;
export const FONT_SIZE_STEP = 2;
export const FONT_SIZE_MIN_LEVEL = -2;
export const FONT_SIZE_MAX_LEVEL = 2;

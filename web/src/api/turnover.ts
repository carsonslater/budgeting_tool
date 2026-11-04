import { api } from './client';
import type { TurnoverSetup, TurnoverStatus } from '../types';

export const fetchTurnover = () =>
  api.get<TurnoverStatus>('/api/turnover');

export const setupTurnover = (data: TurnoverSetup) =>
  api.post<{ month: string; openings: Record<string, number> }>('/api/turnover/setup', data);

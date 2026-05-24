import { api } from './client';
import type { IncomeTotal } from '../types';

export const fetchIncome = async (): Promise<number> => {
  const { total } = await api.get<IncomeTotal>('/api/income');
  return total;
};

export const setIncome = (amount: number): Promise<IncomeTotal> =>
  api.post<IncomeTotal>('/api/income', { amount });

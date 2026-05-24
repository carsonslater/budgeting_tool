import { api } from './client';
import type {
  Goal, GoalCreate, GoalUpdate,
  GoalLink, GoalLinkCreate,
} from '../types';

export const fetchGoals      = () =>
  api.get<Goal[]>('/api/goals');

export const createGoal      = (data: GoalCreate) =>
  api.post<Goal>('/api/goals', data);

export const updateGoal      = (id: number, data: GoalUpdate) =>
  api.patch<Goal>(`/api/goals/${id}`, data);

export const deleteGoal      = (id: number) =>
  api.delete(`/api/goals/${id}`);

export const fetchGoalLinks  = () =>
  api.get<GoalLink[]>('/api/goals/links');

export const createGoalLink  = (data: GoalLinkCreate) =>
  api.post<GoalLink>('/api/goals/links', data);

export const deleteGoalLink  = (id: number) =>
  api.delete(`/api/goals/links/${id}`);

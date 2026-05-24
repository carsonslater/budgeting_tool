import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  fetchGoals,
  createGoal,
  updateGoal,
  deleteGoal,
  fetchGoalLinks,
  createGoalLink,
  deleteGoalLink,
} from '../api/goals';
import type { GoalCreate, GoalUpdate, GoalLinkCreate } from '../types';

export const goalKeys = {
  all:   ['goals']         as const,
  list:  ['goals', 'list'] as const,
  links: ['goals', 'links'] as const,
};

export function useGoals() {
  return useQuery({
    queryKey: goalKeys.list,
    queryFn:  fetchGoals,
  });
}

export function useGoalLinks() {
  return useQuery({
    queryKey: goalKeys.links,
    queryFn:  fetchGoalLinks,
  });
}

export function useCreateGoal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: GoalCreate) => createGoal(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: goalKeys.all });
    },
  });
}

export function useUpdateGoal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: GoalUpdate }) =>
      updateGoal(id, data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: goalKeys.all });
    },
  });
}

export function useDeleteGoal() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteGoal(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: goalKeys.all });
    },
  });
}

export function useCreateGoalLink() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: GoalLinkCreate) => createGoalLink(data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: goalKeys.all });
    },
  });
}

export function useDeleteGoalLink() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => deleteGoalLink(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: goalKeys.all });
    },
  });
}

export function useGoalActions() {
  return {
    create: useCreateGoal(),
    update: useUpdateGoal(),
    remove: useDeleteGoal(),
    createLink: useCreateGoalLink(),
    removeLink: useDeleteGoalLink(),
  };
}

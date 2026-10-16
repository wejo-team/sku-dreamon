import { z } from 'zod';
import { apiRequest } from '@/lib/api';

const healthSchema = z.object({ status: z.literal('ok') });

export async function getHealth(signal?: AbortSignal) {
  return healthSchema.parse(await apiRequest('/health', { signal }));
}

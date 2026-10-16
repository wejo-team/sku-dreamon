import { z } from 'zod';
import { apiRequest } from '@/lib/api';
import type { HealthApiV1HealthGetResponses } from '@/lib/api-schema.generated';

export type HealthResponse = HealthApiV1HealthGetResponses[200];

export const healthSchema = z.object({ status: z.literal('ok') });

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return healthSchema.parse(await apiRequest('/health', { signal }));
}

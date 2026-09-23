import { apiGet } from './client.ts';

/** Body of GET /api/health/, as returned by backend/core/views.py. */
export interface HealthResponse {
  status: 'ok';
  database: 'ok' | 'unavailable';
}

export function getHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>('/health/');
}

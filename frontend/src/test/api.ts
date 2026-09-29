import { vi } from 'vitest';
import type { SessionUser } from '../api/session.ts';

export const ADA: SessionUser = {
  id: 7,
  email: 'ada@example.com',
  name: 'Ada Lovelace',
};

type Handler = (init: RequestInit | undefined) => Response | Promise<Response>;

/**
 * Stubs fetch with a fake API. `handlers` are keyed by method and URL, such as
 * 'GET /api/auth/session/'. The health check never answers unless a test
 * handles it, and any other request fails the test.
 */
export function stubApi(handlers: Record<string, Handler>) {
  const fetchMock = vi.fn(
    (url: string, init?: RequestInit): Promise<Response> => {
      const key = `${init?.method ?? 'GET'} ${url}`;
      const handler = handlers[key];
      if (handler) {
        return Promise.resolve(handler(init));
      }
      if (key === 'GET /api/health/') {
        return new Promise<Response>(() => {});
      }
      throw new Error(`Unexpected request: ${key}`);
    },
  );
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

/** A fake API where `user` is signed in, or nobody when null. */
export function stubSession(user: SessionUser | null) {
  return stubApi({
    'GET /api/auth/session/': () => Response.json({ user }),
  });
}

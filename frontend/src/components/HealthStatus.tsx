import { useQuery } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { getHealth } from '../api/health.ts';

function HealthStatus() {
  const health = useQuery({ queryKey: ['health'], queryFn: getHealth });

  let content: ReactNode;
  if (health.isPending) {
    content = <p>Checking the API…</p>;
  } else if (health.isError) {
    content = <p>API unavailable: {health.error.message}</p>;
  } else {
    content = (
      <ul>
        <li>API: {health.data.status}</li>
        <li>Database: {health.data.database}</li>
      </ul>
    );
  }

  return (
    <section>
      <h2>Backend status</h2>
      {/* The live region stays mounted while its content changes, so screen
          readers announce each new state. */}
      <div role="status">{content}</div>
    </section>
  );
}

export default HealthStatus;

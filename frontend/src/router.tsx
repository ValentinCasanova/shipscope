import { redirect, type RouteObject } from 'react-router';
import AuthGuard from './auth/AuthGuard.tsx';
import AppShell from './components/AppShell.tsx';
import Home from './pages/Home.tsx';
import NotFound from './pages/NotFound.tsx';
import Orders from './pages/Orders.tsx';
import Privacy from './pages/Privacy.tsx';
import Settings from './pages/Settings.tsx';

/**
 * The app's pages. main.tsx serves them from the browser's address bar, and
 * tests from memory. CloudFront answers every path that isn't a file with
 * index.html, so each of these paths loads the app.
 */
export const routes: RouteObject[] = [
  // Public: what ShipScope is, the sign-in button, and the privacy policy.
  { path: '/', element: <Home /> },
  { path: '/privacy', element: <Privacy /> },
  // The home page is the sign-in page too.
  {
    path: '/login',
    loader: ({ request }) => redirect(`/${new URL(request.url).search}`),
  },
  // Signed in only.
  {
    element: <AuthGuard />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: '/orders', element: <Orders /> },
          { path: '/settings', element: <Settings /> },
        ],
      },
    ],
  },
  { path: '*', element: <NotFound /> },
];

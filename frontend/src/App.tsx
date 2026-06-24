import { useCallback, useState } from "react";
import type { Auth } from "./lib/api";
import Login from "./components/Login";
import Chat from "./components/Chat";

const AUTH_KEY = "bullseye.auth";

function loadAuth(): Auth | null {
  try {
    const raw = sessionStorage.getItem(AUTH_KEY);
    return raw ? (JSON.parse(raw) as Auth) : null;
  } catch {
    return null;
  }
}

export default function App() {
  const [auth, setAuth] = useState<Auth | null>(loadAuth);

  const handleLogin = useCallback((a: Auth) => {
    sessionStorage.setItem(AUTH_KEY, JSON.stringify(a));
    setAuth(a);
  }, []);

  const handleLogout = useCallback(() => {
    sessionStorage.clear();
    setAuth(null);
  }, []);

  // Switching the active school updates current_school, which rides along in
  // every chat request's `user` and scopes the MCP server to that school.
  const handleSchoolChange = useCallback(
    (school: { id: number; display_name: string }) => {
      setAuth((prev) => {
        if (!prev) return prev;
        const next = { ...prev, user: { ...prev.user, current_school: school } };
        sessionStorage.setItem(AUTH_KEY, JSON.stringify(next));
        return next;
      });
    },
    [],
  );

  return (
    <div className="grain h-full">
      {auth ? (
        <Chat
          auth={auth}
          onLogout={handleLogout}
          onSchoolChange={handleSchoolChange}
        />
      ) : (
        <Login onLogin={handleLogin} />
      )}
    </div>
  );
}

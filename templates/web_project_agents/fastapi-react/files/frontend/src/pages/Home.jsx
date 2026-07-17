import { useEffect, useState } from "react";

export default function Home({ apiUrl, token }) {
  const [user, setUser] = useState(null);

  useEffect(() => {
    if (!token) return;
    fetch(`${apiUrl}/me`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then((r) => (r.ok ? r.json() : null))
      .then(setUser)
      .catch(() => setUser(null));
  }, [apiUrl, token]);

  return (
    <div className="page">
      <h1>FastAPI + React Starter</h1>
      {user ? <p>Welcome, {user.username}!</p> : <p>Please log in.</p>}
    </div>
  );
}

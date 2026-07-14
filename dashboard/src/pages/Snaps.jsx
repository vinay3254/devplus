import { useEffect, useState } from "react";
import { listSnaps, searchSnaps, retrySummary } from "../api";
import SnapCard from "../components/SnapCard";

export default function Snaps() {
  const [snaps, setSnaps] = useState([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    loadAll();
  }, []);

  async function loadAll() {
    try {
      setSnaps(await listSnaps());
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleSearch(e) {
    e.preventDefault();
    setError("");
    try {
      if (query.trim() === "") {
        await loadAll();
      } else {
        setSnaps(await searchSnaps(query));
      }
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleRetry(snapId) {
    try {
      await retrySummary(snapId);
      await loadAll();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div>
      <form onSubmit={handleSearch}>
        <input
          type="text"
          placeholder="Search snaps..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button type="submit">Search</button>
      </form>
      {error && <p role="alert">{error}</p>}
      <div>
        {snaps.map((snap) => (
          <SnapCard key={snap.id} snap={snap} onRetry={() => handleRetry(snap.id)} />
        ))}
      </div>
    </div>
  );
}

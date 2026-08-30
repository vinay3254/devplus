import { useEffect, useState } from "react";
import { listSnaps, searchSnaps, retrySummary } from "../api";
import SnapCard from "../components/SnapCard";

export default function Snaps() {
  const [snaps, setSnaps] = useState([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [filter, setFilter] = useState(null);

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

  const visibleSnaps = filter
    ? snaps.filter((snap) =>
        filter.type === "tag" ? snap.tags.includes(filter.value) : snap.category === filter.value
      )
    : snaps;

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
      {filter && (
        <p>
          Filtered by {filter.type}: <strong>{filter.value}</strong>{" "}
          <button onClick={() => setFilter(null)}>Clear filter ×</button>
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      <div>
        {visibleSnaps.map((snap) => (
          <SnapCard
            key={snap.id}
            snap={snap}
            onRetry={() => handleRetry(snap.id)}
            onChanged={loadAll}
            onFilterTag={(tag) => setFilter({ type: "tag", value: tag })}
            onFilterCategory={(category) => setFilter({ type: "category", value: category })}
          />
        ))}
      </div>
    </div>
  );
}

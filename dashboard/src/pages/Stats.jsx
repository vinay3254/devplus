import { useEffect, useState } from "react";
import { getReviewStats } from "../api";

export default function Stats() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getReviewStats()
      .then(setStats)
      .catch((err) => setError(err.message));
  }, []);

  if (error) return <p role="alert">{error}</p>;
  if (!stats) return <p>Loading...</p>;

  return (
    <div className="stats">
      <p>
        Current streak: {stats.current_streak} day{stats.current_streak === 1 ? "" : "s"}
      </p>
      <p>
        Longest streak: {stats.longest_streak} day{stats.longest_streak === 1 ? "" : "s"}
      </p>
      <p>Total reviewed: {stats.total_reviewed}</p>
      <p>Reviewed today: {stats.reviewed_today}</p>
    </div>
  );
}

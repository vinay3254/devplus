import { useEffect, useState } from "react";
import { getDueSnaps, gradeSnap } from "../api";

export default function Review() {
  const [queue, setQueue] = useState([]);
  const [revealed, setRevealed] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    loadDue();
  }, []);

  async function loadDue() {
    try {
      setQueue(await getDueSnaps());
      setRevealed(false);
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleGrade(grade) {
    const current = queue[0];
    try {
      await gradeSnap(current.id, grade);
      setQueue((q) => q.slice(1));
      setRevealed(false);
    } catch (err) {
      setError(err.message);
    }
  }

  if (error) return <p role="alert">{error}</p>;
  if (queue.length === 0) return <p>Nothing due for review. Nice.</p>;

  const current = queue[0];

  return (
    <div className="flashcard">
      <p className="remaining">{queue.length} due</p>
      <h3>{current.title || current.url}</h3>
      <p>{current.raw_text}</p>
      {!revealed && <button onClick={() => setRevealed(true)}>Reveal summary</button>}
      {revealed && (
        <>
          <p className="summary">{current.summary || "No summary available."}</p>
          <div className="grade-buttons">
            <button onClick={() => handleGrade("again")}>Again</button>
            <button onClick={() => handleGrade("hard")}>Hard</button>
            <button onClick={() => handleGrade("good")}>Good</button>
            <button onClick={() => handleGrade("easy")}>Easy</button>
          </div>
        </>
      )}
    </div>
  );
}

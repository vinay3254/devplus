import { useState } from "react";
import { updateSnap, deleteSnap } from "../api";

export default function SnapCard({ snap, onRetry, onChanged, onFilterTag, onFilterCategory }) {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(snap.title);
  const [category, setCategory] = useState(snap.category || "");
  const [tagsText, setTagsText] = useState(snap.tags.join(", "));
  const [error, setError] = useState("");

  async function handleSave() {
    setError("");
    try {
      const tags = tagsText.split(",").map((t) => t.trim()).filter(Boolean);
      await updateSnap(snap.id, { title, category, tags });
      setEditing(false);
      onChanged();
    } catch (err) {
      setError(err.message);
    }
  }

  async function handleDelete() {
    if (!window.confirm("Delete this snap?")) return;
    setError("");
    try {
      await deleteSnap(snap.id);
      onChanged();
    } catch (err) {
      setError(err.message);
    }
  }

  if (editing) {
    return (
      <div className="snap-card">
        <input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Title" />
        <input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="Category" />
        <input value={tagsText} onChange={(e) => setTagsText(e.target.value)} placeholder="tag1, tag2" />
        {error && <p role="alert">{error}</p>}
        <button onClick={handleSave}>Save</button>
        <button onClick={() => setEditing(false)}>Cancel</button>
      </div>
    );
  }

  return (
    <div className="snap-card">
      <h3>{snap.title || snap.url}</h3>
      <p>{snap.summary || "No summary yet."}</p>
      {!snap.summary && <button onClick={onRetry}>Retry summarization</button>}
      <div>
        {snap.category && (
          <button className="chip category" onClick={() => onFilterCategory(snap.category)}>
            {snap.category}
          </button>
        )}
        {snap.tags.map((tag) => (
          <button key={tag} className="chip tag" onClick={() => onFilterTag(tag)}>
            {tag}
          </button>
        ))}
      </div>
      {error && <p role="alert">{error}</p>}
      <a href={snap.url} target="_blank" rel="noreferrer">
        Source
      </a>
      <button onClick={() => setEditing(true)}>Edit</button>
      <button onClick={handleDelete}>Delete</button>
    </div>
  );
}

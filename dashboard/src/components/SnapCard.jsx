export default function SnapCard({ snap, onRetry }) {
  return (
    <div className="snap-card">
      <h3>{snap.title || snap.url}</h3>
      <p>{snap.summary || "No summary yet."}</p>
      {!snap.summary && <button onClick={onRetry}>Retry summarization</button>}
      <div>
        {snap.tags.map((tag) => (
          <span key={tag} className="tag">
            {tag}
          </span>
        ))}
      </div>
      <a href={snap.url} target="_blank" rel="noreferrer">
        Source
      </a>
    </div>
  );
}

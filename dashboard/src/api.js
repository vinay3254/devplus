const API_URL = import.meta.env.VITE_API_URL || "http://localhost:5100";

function authHeaders() {
  const token = localStorage.getItem("snapstack_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

// Wraps fetch for authenticated calls: on a 401 (expired/invalid JWT), clears
// the stored token and reloads so App.jsx's isLoggedIn() check sends the user
// back to the login screen, per the spec's "JWT expired -> redirect to login".
async function authedFetch(url, options = {}) {
  const resp = await fetch(url, {
    ...options,
    headers: { ...authHeaders(), ...(options.headers || {}) },
  });
  if (resp.status === 401) {
    localStorage.removeItem("snapstack_token");
    window.location.reload();
    throw new Error("Session expired");
  }
  return resp;
}

export async function login(username, password) {
  const resp = await fetch(`${API_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!resp.ok) {
    throw new Error("Invalid username or password");
  }
  const data = await resp.json();
  localStorage.setItem("snapstack_token", data.token);
  return data.token;
}

export function logout() {
  localStorage.removeItem("snapstack_token");
}

export function isLoggedIn() {
  return Boolean(localStorage.getItem("snapstack_token"));
}

export async function listSnaps() {
  const resp = await authedFetch(`${API_URL}/api/snaps`);
  if (!resp.ok) throw new Error("Failed to load snaps");
  return resp.json();
}

export async function searchSnaps(query) {
  const resp = await authedFetch(
    `${API_URL}/api/snaps/search?q=${encodeURIComponent(query)}`
  );
  if (!resp.ok) throw new Error("Search failed");
  return resp.json();
}

export async function retrySummary(snapId) {
  const resp = await authedFetch(`${API_URL}/api/snaps/${snapId}/retry-summary`, {
    method: "POST",
  });
  if (!resp.ok) throw new Error("Retry failed");
  return resp.json();
}

export async function getDueSnaps() {
  const resp = await authedFetch(`${API_URL}/api/review/due`);
  if (!resp.ok) throw new Error("Failed to load due snaps");
  return resp.json();
}

export async function gradeSnap(snapId, grade) {
  const resp = await authedFetch(`${API_URL}/api/review/${snapId}/grade`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ grade }),
  });
  if (!resp.ok) throw new Error("Grading failed");
  return resp.json();
}

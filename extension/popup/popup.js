const API_URL = "http://localhost:5100";

const loggedOutEl = document.getElementById("logged-out");
const loggedInEl = document.getElementById("logged-in");
const errorEl = document.getElementById("error");

async function refreshView() {
  const { snapstack_token: token } = await chrome.storage.local.get("snapstack_token");
  loggedOutEl.hidden = Boolean(token);
  loggedInEl.hidden = !token;
}

document.getElementById("login-btn").addEventListener("click", async () => {
  errorEl.textContent = "";
  const username = document.getElementById("username").value;
  const password = document.getElementById("password").value;

  try {
    const resp = await fetch(`${API_URL}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!resp.ok) {
      errorEl.textContent = "Invalid username or password.";
      return;
    }
    const { token } = await resp.json();
    await chrome.storage.local.set({ snapstack_token: token });
    refreshView();
  } catch (err) {
    errorEl.textContent = "SnapStack backend unreachable.";
  }
});

document.getElementById("logout-btn").addEventListener("click", async () => {
  await chrome.storage.local.remove("snapstack_token");
  refreshView();
});

refreshView();

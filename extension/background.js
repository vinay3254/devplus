const API_URL = "http://localhost:5100";
const MENU_ID = "snapstack-add";

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: MENU_ID,
    title: "Add to SnapStack",
    contexts: ["selection"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== MENU_ID || !info.selectionText) {
    return;
  }
  await captureSelection(info.selectionText, tab.url, tab.title);
});

async function captureSelection(text, url, title) {
  const { snapstack_token: token } = await chrome.storage.local.get("snapstack_token");

  if (!token) {
    notify("SnapStack", "Log in required — open the SnapStack popup.");
    return;
  }

  try {
    const resp = await fetch(`${API_URL}/api/snaps`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ text, url, title }),
    });

    if (resp.status === 401) {
      notify("SnapStack", "Log in required — open the SnapStack popup.");
      return;
    }
    if (!resp.ok) {
      notify("SnapStack", "Save failed — check the backend is running.");
      return;
    }
    notify("SnapStack", "Saved.");
  } catch (err) {
    notify("SnapStack", "SnapStack backend unreachable — is it running?");
  }
}

function notify(title, message) {
  chrome.notifications.create({
    type: "basic",
    iconUrl: "icon128.png",
    title,
    message,
  });
}

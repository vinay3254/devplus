import { useState } from "react";
import Login from "./pages/Login";
import Snaps from "./pages/Snaps";
import Review from "./pages/Review";
import { isLoggedIn, logout } from "./api";

function App() {
  const [loggedIn, setLoggedIn] = useState(isLoggedIn());
  const [view, setView] = useState("snaps");

  if (!loggedIn) {
    return <Login onLoggedIn={() => setLoggedIn(true)} />;
  }

  return (
    <div>
      <header>
        <h1>SnapStack</h1>
        <nav>
          <button onClick={() => setView("snaps")}>Snaps</button>
          <button onClick={() => setView("review")}>Review</button>
        </nav>
        <button
          onClick={() => {
            logout();
            setLoggedIn(false);
          }}
        >
          Log out
        </button>
      </header>
      {view === "snaps" && <Snaps />}
      {view === "review" && <Review />}
    </div>
  );
}

export default App;

import { useState } from "react";
import Login from "./pages/Login";
import { isLoggedIn, logout } from "./api";

function App() {
  const [loggedIn, setLoggedIn] = useState(isLoggedIn());

  if (!loggedIn) {
    return <Login onLoggedIn={() => setLoggedIn(true)} />;
  }

  return (
    <div>
      <header>
        <h1>SnapStack</h1>
        <button
          onClick={() => {
            logout();
            setLoggedIn(false);
          }}
        >
          Log out
        </button>
      </header>
      <p>Logged in.</p>
    </div>
  );
}

export default App;

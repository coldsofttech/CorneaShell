import { useEffect, useState } from "react";
import { control, nativeAction, windowState } from "./cornea.js";

function TitleBar({ state, onChange }) {
  const toggleMaximize = async () => {
    await control(state.maximized ? "restore" : "maximize");
    onChange();
  };
  return (
    <header className="titlebar">
      <span className="title">{state.title}</span>
      <span className="drag pywebview-drag-region" />
      <button onClick={() => control("minimize")} title="Minimize">
        &#8211;
      </button>
      <button onClick={toggleMaximize} title="Maximize">
        &#9633;
      </button>
      <button className="close" onClick={() => control("close")} title="Close">
        &#10005;
      </button>
    </header>
  );
}

export default function App() {
  const [state, setState] = useState(null);
  const [output, setOutput] = useState("Press the button.");
  const refresh = () => windowState().then(setState);

  useEffect(() => {
    refresh();
  }, []);

  return (
    <>
      {/* Our own title bar, only when the window has no native one. */}
      {state?.frameless && <TitleBar state={state} onChange={refresh} />}
      <main>
        <h1>Hello from React</h1>
        <p>A Vite build, served from dist/ by Cornea.</p>
        <button onClick={async () => setOutput(JSON.stringify(await nativeAction("platform_info"), null, 2))}>
          Ask the system (native action)
        </button>
        <pre>{output}</pre>
      </main>
    </>
  );
}

import { Toolbar } from "./components/Toolbar";
import { DocumentView } from "./components/DocumentView";
import { EditPanel } from "./components/EditPanel";
import { StatusBar } from "./components/StatusBar";

function App() {
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      <Toolbar />
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <DocumentView />
        <EditPanel />
      </div>
      <StatusBar />
    </div>
  );
}

export default App;

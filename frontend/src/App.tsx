import { Chat } from "./components/Chat";
import { Sidebar } from "./components/Sidebar";

export default function App() {
  return (
    <div style={{ display: "flex", height: "100vh", fontFamily: "system-ui" }}>
      <Sidebar />
      <div style={{ flex: 1 }}>
        <Chat />
      </div>
    </div>
  );
}

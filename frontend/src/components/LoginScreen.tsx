import { useState } from "react";
import { api } from "../services/api";
import type { User } from "../services/api";

interface Props {
  onLogin: (user: User) => void;
}

export function LoginScreen({ onLogin }: Props) {
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    try {
      const user = await api.login(name.trim());
      onLogin(user);
    } catch (err) {
      alert("Login failed: " + (err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-screen">
      <div className="login-container">
        <h1>Liminal</h1>
        <p className="subtitle">Your AI that gets things done</p>
        <form onSubmit={handleSubmit}>
          <input
            type="text"
            placeholder="What's your name?"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
          <button type="submit" disabled={loading || !name.trim()}>
            {loading ? "..." : "Get Started"}
          </button>
        </form>
      </div>
    </div>
  );
}

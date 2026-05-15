import { useState, useCallback, type ReactElement } from 'react';
import { login } from './alexaApi';
import TaskCard from './TaskCard';
import './App.css';

type AppState = 'login' | 'dashboard';

function App(): ReactElement {
  const [state, setState] = useState<AppState>('login');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [otp, setOtp] = useState('');

  const handleLogin = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(otp);
      setState('dashboard');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  }, [otp]);

  return (
    <div className="App">
      <main className="App-main">
        {state === 'login' && (
          <div className="panel">
            <h1 className="panel__title">Alexa To-Do</h1>
            <p className="panel__subtitle">Sign in with your Amazon account</p>
            {error && <p className="error">{error}</p>}
            <form className="form" onSubmit={handleLogin}>
              <label className="form__label">
                One-Time Password (OTP)
                <input className="form__input" type="text" value={otp} onChange={e => setOtp(e.target.value)} placeholder="6-digit code" required />
              </label>
              <button className="btn" type="submit" disabled={loading}>
                {loading ? 'Signing in…' : 'Sign in'}
              </button>
            </form>
          </div>
        )}

        {state === 'dashboard' && (
          <div className="panel">
            <h1 className="panel__title">Dashboard</h1>
            <TaskCard title="Make dashboard app" priority="high" />
          </div>
        )}
      </main>
    </div>
  );
}

export default App;

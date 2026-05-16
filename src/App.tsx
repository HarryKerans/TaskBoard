import { useState, useCallback, useEffect, type ReactElement } from 'react';
import { login, getLists, getListItems, checkAuthStatus, type AlexaItem } from './alexaApi.ts';
import TaskCard from './TaskCard.tsx';
import './App.css';

type AppState = 'loading' | 'login' | 'dashboard';

function App(): ReactElement {
  const [state, setState] = useState<AppState>('loading');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [otp, setOtp] = useState('');
  const [todoItems, setTodoItems] = useState<AlexaItem[]>([]);

  const loadDashboard = useCallback(async () => {
    const lists = await getLists();
    const todoList = lists.find(l => l.listType === 'TODO');
    if (todoList) {
      const items = await getListItems(todoList.listId);
      setTodoItems(items);
    }
    setState('dashboard');
  }, []);

  // On mount: check if a session already exists
  useEffect(() => {
    checkAuthStatus().then(authenticated => {
      if (authenticated) {
        loadDashboard().catch(() => setState('login'));
      } else {
        setState('login');
      }
    });
  }, [loadDashboard]);

  const handleLogin = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(otp);
      await loadDashboard();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  }, [otp, loadDashboard]);

  return (
    <div className="App">
      <main className={state === 'dashboard' ? 'App-main App-main--dashboard' : 'App-main'}>
        {state === 'loading' && (
          <div className="panel">
            <p className="panel__subtitle">Loading…</p>
          </div>
        )}

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
          <div className="panel panel--full">
            <h1 className="dashboard__title">To Do List</h1>
            <div className="dashboard">
              <div className="container">
                <TaskCard title="Make dashboard app" priority="high" />
                {todoItems.map(item => (
                  <TaskCard key={item.itemId} title={item.itemName} priority="medium" />
                ))}
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}

export default App;

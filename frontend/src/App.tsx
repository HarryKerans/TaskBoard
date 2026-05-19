import { useState, useCallback, useEffect, type ReactElement } from 'react';
import { login, getLists, getListItems, getTasks, checkAuthStatus, type AlexaItem, type LocalTask } from './alexaApi';
import TaskCard from './TaskCard';
import './App.css';

type AppState = 'loading' | 'login' | 'dashboard';

function App(): ReactElement {
  const [state, setState] = useState<AppState>('loading');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [otp, setOtp] = useState('');
  const [todoItems, setTodoItems] = useState<AlexaItem[]>([]);
  const [localOnlyTasks, setLocalOnlyTasks] = useState<LocalTask[]>([]);

  const loadDashboard = useCallback(async () => {
    const [lists, localTasks] = await Promise.all([getLists(), getTasks()]);

    let alexaItems: AlexaItem[] = [];
    const todoList = lists.find(l => l.listType === 'TODO');
    if (todoList) {
      alexaItems = await getListItems(todoList.listId);
    }

    // Deduplicate: only show local tasks whose title doesn't already appear in Alexa list
    const alexaTitles = new Set(alexaItems.map(i => i.itemName.toLowerCase()));
    const extras = localTasks.filter(
      t => t.status === 'open' && !alexaTitles.has(t.title.toLowerCase())
    );

    setTodoItems(alexaItems);
    setLocalOnlyTasks(extras);
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
                {localOnlyTasks.map(task => (
                  <TaskCard key={`local-${task.id}`} title={task.title} priority={task.priority} />
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

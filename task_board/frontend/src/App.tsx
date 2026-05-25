import { useState, useCallback, useEffect, type ReactElement } from 'react';
import { login, getLists, getListItems, getTasks, checkAuthStatus, markTaskDone, markAlexaItemDone, updateTask, type AlexaItem, type LocalTask, type Priority } from './alexaApi';
import TaskCard from './TaskCard';
import EditTaskModal from './EditTaskModal';
import './App.css';

type AppState = 'loading' | 'login' | 'dashboard';

function App(): ReactElement {
  const [state, setState] = useState<AppState>('loading');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [otp, setOtp] = useState('');
  const [todoItems, setTodoItems] = useState<AlexaItem[]>([]);
  const [localOnlyTasks, setLocalOnlyTasks] = useState<LocalTask[]>([]);
  const [alexaEnabled, setAlexaEnabled] = useState(true);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [marking, setMarking] = useState(false);
  const [editingTask, setEditingTask] = useState<LocalTask | null>(null);

  const loadDashboard = useCallback(async (withAlexa = true) => {
    const [lists, localTasks] = await Promise.all([
      withAlexa ? getLists() : Promise.resolve([]),
      getTasks(),
    ]);

    let alexaItems: AlexaItem[] = [];
    if (withAlexa) {
      const todoList = lists.find(l => l.listType === 'TODO');
      if (todoList) {
        alexaItems = await getListItems(todoList.listId);
      }
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
        loadDashboard(true).catch(() => setState('login'));
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
      await loadDashboard(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  }, [otp, loadDashboard]);

  const handleLocalOnly = useCallback(async () => {
    setAlexaEnabled(false);
    setError('');
    setLoading(true);
    try {
      await loadDashboard(false);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  }, [loadDashboard]);

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds(prev => {
      const next = new Set(Array.from(prev));
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  const handleSaveEdit = useCallback(async (updates: { title: string; description: string; priority: Priority }) => {
    if (!editingTask) return;
    await updateTask(editingTask.id, updates);
    setEditingTask(null);
    await loadDashboard(alexaEnabled);
  }, [editingTask, alexaEnabled, loadDashboard]);

  const handleMarkDone = useCallback(async () => {
    setMarking(true);
    const ops: Promise<void>[] = [];

    for (const id of Array.from(selectedIds)) {
      if (id.startsWith('local-')) {
        const taskId = parseInt(id.replace('local-', ''), 10);
        ops.push(markTaskDone(taskId));
      } else if (id.startsWith('alexa-')) {
        const itemId = id.replace('alexa-', '');
        const item = todoItems.find(i => i.itemId === itemId);
        if (item) {
          ops.push(markAlexaItemDone(item.listId, item.itemId, item.version));
        }
      }
    }

    await Promise.all(ops);
    setSelectedIds(new Set());
    setMarking(false);
    await loadDashboard(alexaEnabled);
  }, [selectedIds, todoItems, alexaEnabled, loadDashboard]);

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
            <button className="btn btn--secondary" onClick={handleLocalOnly} disabled={loading}>
              Continue without Alexa
            </button>
          </div>
        )}

        {state === 'dashboard' && (
          <div className="panel panel--full">
            <h1 className="dashboard__title">To Do List</h1>
            {!alexaEnabled && (
              <p className="dashboard__notice">Showing local tasks only — not connected to Alexa</p>
            )}
            <div className="dashboard">
              <div className="container">
                {todoItems.map(item => (
                  <TaskCard
                    key={item.itemId}
                    id={`alexa-${item.itemId}`}
                    title={item.itemName}
                    priority="medium"
                    selected={selectedIds.has(`alexa-${item.itemId}`)}
                    onToggle={toggleSelect}
                  />
                ))}
                {localOnlyTasks.map(task => (
                  <TaskCard
                    key={`local-${task.id}`}
                    id={`local-${task.id}`}
                    title={task.title}
                    priority={task.priority}
                    selected={selectedIds.has(`local-${task.id}`)}
                    onToggle={toggleSelect}
                    onEdit={() => setEditingTask(task)}
                  />
                ))}
              </div>
            </div>
            {selectedIds.size > 0 && (
              <div className="mark-done-bar">
                <button className="btn btn--done" onClick={handleMarkDone} disabled={marking}>
                  {marking ? 'Saving…' : `Mark as done (${selectedIds.size})`}
                </button>
              </div>
            )}
          </div>
        )}
      </main>
      {editingTask && (
        <EditTaskModal
          task={editingTask}
          onSave={handleSaveEdit}
          onClose={() => setEditingTask(null)}
        />
      )}
    </div>
  );
}

export default App;

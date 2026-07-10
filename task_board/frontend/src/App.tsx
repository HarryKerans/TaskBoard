import { useState, useCallback, useEffect, type ReactElement } from 'react';
import { login, syncAlexa, getTasks, checkAuthStatus, markTaskDone, updateTask, createTask, type LocalTask, type Priority } from './alexaApi';
import TaskCard from './TaskCard';
import EditTaskModal from './EditTaskModal';
import ShoppingPage from './ShoppingPage';
import './App.css';

type AppState = 'loading' | 'login' | 'dashboard';
type Page = 'tasks' | 'shopping';
type SortOption = 'priority' | 'recent' | 'oldest' | 'updated' | 'az';

const PRIORITY_ORDER: Record<string, number> = { high: 0, medium: 1, low: 2 };

function sortTasks(tasks: LocalTask[], sort: SortOption): LocalTask[] {
  const copy = [...tasks];
  switch (sort) {
    case 'priority':
      return copy.sort((a, b) =>
        (PRIORITY_ORDER[a.priority] ?? 3) - (PRIORITY_ORDER[b.priority] ?? 3)
      );
    case 'recent':
      return copy.sort((a, b) => b.created_at.localeCompare(a.created_at));
    case 'oldest':
      return copy.sort((a, b) => a.created_at.localeCompare(b.created_at));
    case 'updated':
      return copy.sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    case 'az':
      return copy.sort((a, b) => a.title.localeCompare(b.title));
  }
}

function App(): ReactElement {
  const [state, setState] = useState<AppState>('loading');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [otp, setOtp] = useState('');
  const [tasks, setTasks] = useState<LocalTask[]>([]);
  const [sort, setSort] = useState<SortOption>('priority');
  const [alexaEnabled, setAlexaEnabled] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [marking, setMarking] = useState(false);
  const [editingTask, setEditingTask] = useState<LocalTask | null>(null);
  const [addingTask, setAddingTask] = useState(false);
  const [page, setPage] = useState<Page>('tasks');

  const loadDashboard = useCallback(async () => {
    const allTasks = await getTasks();
    setTasks(allTasks.filter(t => t.status === 'open'));
    setState('dashboard');
  }, []);

  // On mount: check if a session already exists; if so, sync then load
  useEffect(() => {
    checkAuthStatus().then(async authenticated => {
      if (authenticated) {
        setAlexaEnabled(true);
        try {
          await syncAlexa();
        } catch {
          // Sync failure is non-fatal — show whatever is in the DB
        }
        await loadDashboard();
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
      setAlexaEnabled(true);
      await syncAlexa();
      await loadDashboard();
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
      await loadDashboard();
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

  const handleSaveEdit = useCallback(async (updates: { title: string; description: string; priority: Priority; created_at?: string }) => {
    if (!editingTask) return;
    await updateTask(editingTask.id, updates);
    setEditingTask(null);
    await loadDashboard();
  }, [editingTask, loadDashboard]);

  const handleCreateTask = useCallback(async (data: { title: string; description: string; priority: Priority; created_at?: string }) => {
    await createTask(data);
    setAddingTask(false);
    await loadDashboard();
  }, [loadDashboard]);

  const handleMarkDone = useCallback(async () => {
    setMarking(true);
    const ops = Array.from(selectedIds).map(id => {
      const taskId = parseInt(id.replace('task-', ''), 10);
      return markTaskDone(taskId);
    });
    await Promise.all(ops);
    setSelectedIds(new Set());
    setMarking(false);
    await loadDashboard();
  }, [selectedIds, loadDashboard]);

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
            <nav className="page-tabs">
              <button
                className={`page-tab${page === 'tasks' ? ' page-tab--active' : ''}`}
                onClick={() => setPage('tasks')}
              >
                To Do List
              </button>
              <button
                className={`page-tab${page === 'shopping' ? ' page-tab--active' : ''}`}
                onClick={() => setPage('shopping')}
              >
                <svg className="page-tab__icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <circle cx="9" cy="21" r="1"/>
                  <circle cx="20" cy="21" r="1"/>
                  <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>
                </svg>
                Shopping
              </button>
            </nav>
            {page === 'tasks' && (
              <>
                <div className="dashboard__header">
                  <h1 className="dashboard__title">To Do List</h1>
                  <div className="dashboard__controls">
                    {!alexaEnabled && (
                      <p className="dashboard__notice">Local tasks only</p>
                    )}
                    <label className="sort-label">
                      Sort by
                      <select
                        className="sort-select"
                        value={sort}
                        onChange={e => setSort(e.target.value as SortOption)}
                      >
                        <option value="priority">Priority</option>
                        <option value="recent">Recently created</option>
                        <option value="oldest">Oldest first</option>
                        <option value="updated">Recently updated</option>
                        <option value="az">A → Z</option>
                      </select>
                    </label>
                    <button className="btn btn--add btn--add-desktop" onClick={() => setAddingTask(true)}>+ Add Task</button>
                  </div>
                  <button className="btn btn--add btn--add-mobile" onClick={() => setAddingTask(true)}>+ Add Task</button>
                </div>
                <div className="dashboard">
                  <div className="container">
                    {sortTasks(tasks, sort).map(task => (
                      <TaskCard
                        key={`task-${task.id}`}
                        id={`task-${task.id}`}
                        title={task.title}
                        priority={task.priority}
                        selected={selectedIds.has(`task-${task.id}`)}
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
              </>
            )}
            {page === 'shopping' && <ShoppingPage />}
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
      {addingTask && (
        <EditTaskModal
          onSave={handleCreateTask}
          onClose={() => setAddingTask(false)}
        />
      )}
    </div>
  );
}

export default App;

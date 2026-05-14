import { useState, useCallback, type ReactElement } from 'react';
import { login, getLists, getListItems, type AlexaList, type AlexaItem } from './alexaApi';
import './App.css';

type AppState = 'login' | 'lists' | 'items';

function App(): ReactElement {
  const [state, setState] = useState<AppState>('login');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Login form
  const [email, setEmail] = useState(process.env.REACT_APP_AMAZON_EMAIL ?? '');
  const [password, setPassword] = useState(process.env.REACT_APP_AMAZON_PASSWORD ?? '');
  const [otp, setOtp] = useState('');
  const [countryCode, setCountryCode] = useState(process.env.REACT_APP_AMAZON_COUNTRY ?? 'com');

  // Data
  const [lists, setLists] = useState<AlexaList[]>([]);
  const [selectedList, setSelectedList] = useState<AlexaList | null>(null);
  const [items, setItems] = useState<AlexaItem[]>([]);

  const handleLogin = useCallback(async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await login(email, password, otp, countryCode);
      const fetchedLists = await getLists();
      setLists(fetchedLists);
      setState('lists');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  }, [email, password, otp, countryCode]);

  const handleSelectList = useCallback(async (list: AlexaList) => {
    setError('');
    setLoading(true);
    setSelectedList(list);
    try {
      const fetchedItems = await getListItems(list.listId);
      setItems(fetchedItems);
      setState('items');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  }, []);

  const handleRefresh = useCallback(async () => {
    if (!selectedList) return;
    setError('');
    setLoading(true);
    try {
      const fetchedItems = await getListItems(selectedList.listId);
      setItems(fetchedItems);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'An error occurred');
    } finally {
      setLoading(false);
    }
  }, [selectedList]);

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
                Email
                <input className="form__input" type="email" value={email} onChange={e => setEmail(e.target.value)} required />
              </label>
              <label className="form__label">
                Password
                <input className="form__input" type="password" value={password} onChange={e => setPassword(e.target.value)} required />
              </label>
              <label className="form__label">
                One-Time Password (OTP)
                <input className="form__input" type="text" value={otp} onChange={e => setOtp(e.target.value)} placeholder="6-digit code" required />
              </label>
              <label className="form__label">
                Country
                <select className="form__input" value={countryCode} onChange={e => setCountryCode(e.target.value)}>
                  <option value="com">USA (amazon.com)</option>
                  <option value="co.uk">UK (amazon.co.uk)</option>
                  <option value="de">Germany (amazon.de)</option>
                  <option value="fr">France (amazon.fr)</option>
                  <option value="co.jp">Japan (amazon.co.jp)</option>
                </select>
              </label>
              <button className="btn" type="submit" disabled={loading}>
                {loading ? 'Signing in…' : 'Sign in'}
              </button>
            </form>
          </div>
        )}

        {state === 'lists' && (
          <div className="panel">
            <h1 className="panel__title">Your Lists</h1>
            {error && <p className="error">{error}</p>}
            {loading ? <p className="muted">Loading…</p> : (
              <ul className="list">
                {lists.map(l => (
                  <li key={l.listId} className="list__item" onClick={() => handleSelectList(l)}>
                    {l.name}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        {state === 'items' && selectedList && (
          <div className="panel">
            <div className="panel__header">
              <button className="btn btn--ghost" onClick={() => setState('lists')}>← Back</button>
              <h1 className="panel__title">{selectedList.name}</h1>
              <button className="btn" onClick={handleRefresh} disabled={loading}>
                {loading ? '…' : 'Refresh'}
              </button>
            </div>
            {error && <p className="error">{error}</p>}
            {loading ? <p className="muted">Loading…</p> : (
              <ul className="list">
                {items.length === 0 && <li className="muted">No items</li>}
                {items.map(item => (
                  <li key={item.itemId} className={`list__item list__item--todo ${item.status === 'COMPLETE' ? 'list__item--done' : ''}`}>
                    <span className="list__item-dot" />
                    {item.value}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </main>
    </div>
  );
}

export default App;

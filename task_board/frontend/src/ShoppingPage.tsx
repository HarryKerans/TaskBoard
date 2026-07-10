import { useState, useEffect, useCallback, type ReactElement } from 'react';
import { getShoppingItems, markShoppingItemDone, createShoppingItem, type ShoppingItem as ShoppingItemType } from './alexaApi';
import ShoppingItem from './ShoppingItem';

type SortOption = 'recent' | 'oldest' | 'updated' | 'az';

function sortItems(items: ShoppingItemType[], sort: SortOption): ShoppingItemType[] {
  const copy = [...items];
  switch (sort) {
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

function ShoppingPage(): ReactElement {
  const [items, setItems] = useState<ShoppingItemType[]>([]);
  const [loading, setLoading] = useState(true);
  const [sort, setSort] = useState<SortOption>('recent');
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [marking, setMarking] = useState(false);
  const [addingItem, setAddingItem] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [saving, setSaving] = useState(false);

  const loadItems = useCallback(async () => {
    const data = await getShoppingItems();
    setItems(data);
    setLoading(false);
  }, []);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  const toggleSelect = useCallback((id: string) => {
    setSelectedIds(prev => {
      const next = new Set(Array.from(prev));
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  const handleMarkDone = useCallback(async () => {
    setMarking(true);
    const ops = Array.from(selectedIds).map(id => {
      const itemId = parseInt(id.replace('shop-', ''), 10);
      return markShoppingItemDone(itemId);
    });
    await Promise.all(ops);
    setSelectedIds(new Set());
    setMarking(false);
    await loadItems();
  }, [selectedIds, loadItems]);

  const handleAddItem = useCallback(async () => {
    if (!newTitle.trim()) return;
    setSaving(true);
    await createShoppingItem(newTitle.trim());
    setNewTitle('');
    setAddingItem(false);
    setSaving(false);
    await loadItems();
  }, [newTitle, loadItems]);

  return (
    <>
      <div className="dashboard__header">
        <h1 className="dashboard__title">
          <svg className="shopping-cart-icon" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <circle cx="9" cy="21" r="1"/>
            <circle cx="20" cy="21" r="1"/>
            <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>
          </svg>
          Shopping List
        </h1>
        <div className="dashboard__controls">
          <label className="sort-label">
            Sort by
            <select
              className="sort-select"
              value={sort}
              onChange={e => setSort(e.target.value as SortOption)}
            >
              <option value="recent">Recently added</option>
              <option value="oldest">Oldest first</option>
              <option value="updated">Recently updated</option>
              <option value="az">A → Z</option>
            </select>
          </label>
          <button className="btn btn--add btn--add-desktop" onClick={() => setAddingItem(true)}>+ Add Item</button>
        </div>
        <button className="btn btn--add btn--add-mobile" onClick={() => setAddingItem(true)}>+ Add Item</button>
      </div>

      {addingItem && (
        <div className="shopping-add-bar">
          <input
            className="form__input shopping-add-input"
            type="text"
            value={newTitle}
            onChange={e => setNewTitle(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleAddItem(); if (e.key === 'Escape') setAddingItem(false); }}
            placeholder="Item name"
            autoFocus
          />
          <button className="btn" onClick={handleAddItem} disabled={saving || !newTitle.trim()}>
            {saving ? 'Adding…' : 'Add'}
          </button>
          <button className="btn btn--secondary" onClick={() => { setAddingItem(false); setNewTitle(''); }}>
            Cancel
          </button>
        </div>
      )}

      <div className="shopping-list">
        {loading && <p className="panel__subtitle">Loading…</p>}
        {!loading && items.length === 0 && (
          <p className="panel__subtitle">No shopping items</p>
        )}
        {sortItems(items, sort).map(item => (
          <ShoppingItem
            key={item.id}
            id={`shop-${item.id}`}
            title={item.title}
            selected={selectedIds.has(`shop-${item.id}`)}
            onToggle={toggleSelect}
          />
        ))}
      </div>

      {selectedIds.size > 0 && (
        <div className="mark-done-bar">
          <button className="btn btn--done" onClick={handleMarkDone} disabled={marking}>
            {marking ? 'Saving…' : `Mark as done (${selectedIds.size})`}
          </button>
        </div>
      )}
    </>
  );
}

export default ShoppingPage;

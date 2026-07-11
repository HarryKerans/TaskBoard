const BASE_URL = '';

export async function checkAuthStatus(): Promise<boolean> {
  const res = await fetch(`${BASE_URL}/auth/status`);
  if (!res.ok) return false;
  const data = await res.json();
  return data.authenticated === true;
}

export async function login(otp: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ otp }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? 'Login failed');
  }
}

export async function syncAlexa(): Promise<{ synced: number }> {
  const res = await fetch(`${BASE_URL}/api/sync`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? 'Sync failed');
  }
  return res.json();
}

export type Priority = 'high' | 'medium' | 'low';

export interface LocalTask {
  id: number;
  title: string;
  description: string;
  status: string;
  priority: Priority;
  source_type: string;
  alexa_item_id?: string;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export async function getTasks(): Promise<LocalTask[]> {
  const res = await fetch(`${BASE_URL}/api/tasks`);
  if (!res.ok) throw new Error('Failed to fetch local tasks');
  const data: Array<LocalTask & { priority: string }> = await res.json();
  return data.map(t => ({
    ...t,
    tags: t.tags ?? [],
    priority: (['high', 'medium', 'low'].includes(t.priority.toLowerCase()) ? t.priority.toLowerCase() : 'medium') as Priority,
  }));
}

export async function markTaskDone(id: number): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/tasks/${id}`, { method: 'PATCH' });
  if (!res.ok) throw new Error(`Failed to mark task ${id} as done`);
}

export async function createTask(data: { title: string; description: string; priority: Priority; tags?: string[] }): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/tasks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to create task');
}

export async function updateTask(
  id: number,
  updates: { title: string; description: string; priority: Priority; created_at?: string; tags?: string[] },
): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/tasks/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(updates),
  });
  if (!res.ok) throw new Error(`Failed to update task ${id}`);
}

export async function getTags(): Promise<string[]> {
  const res = await fetch(`${BASE_URL}/api/tags`);
  if (!res.ok) throw new Error('Failed to fetch tags');
  return res.json();
}

export interface ShoppingItem {
  id: number;
  title: string;
  status: string;
  source_type: string;
  alexa_item_id?: string;
  created_at: string;
  updated_at: string;
}

export async function getShoppingItems(): Promise<ShoppingItem[]> {
  const res = await fetch(`${BASE_URL}/api/shopping`);
  if (!res.ok) throw new Error('Failed to fetch shopping items');
  return res.json();
}

export async function markShoppingItemDone(id: number): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/shopping/${id}`, { method: 'PATCH' });
  if (!res.ok) throw new Error(`Failed to mark shopping item ${id} as done`);
}

export async function createShoppingItem(title: string): Promise<void> {
  const res = await fetch(`${BASE_URL}/api/shopping`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw new Error('Failed to create shopping item');
}

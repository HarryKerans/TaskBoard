const BASE_URL = process.env.REACT_APP_API_URL ?? 'http://localhost:8000';

export interface AlexaList {
  listId: string;
  name: string;
  [key: string]: unknown;
}

export interface AlexaItem {
  itemId: string;
  value: string;
  status: string;
  [key: string]: unknown;
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

export async function getLists(): Promise<AlexaList[]> {
  const res = await fetch(`${BASE_URL}/lists`);
  if (!res.ok) throw new Error('Failed to fetch lists');
  return res.json();
}

export async function getListItems(listId: string): Promise<AlexaItem[]> {
  const res = await fetch(`${BASE_URL}/lists/${listId}/items`);
  if (!res.ok) throw new Error('Failed to fetch items');
  return res.json();
}

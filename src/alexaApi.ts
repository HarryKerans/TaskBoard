const BASE_URL = process.env.REACT_APP_API_URL ?? 'http://localhost:8000';

export interface AlexaList {
  listId: string;
  listType: string;
  listName?: string;
  [key: string]: unknown;
}

export interface AlexaItem {
  itemId: string;
  itemName: string;
  itemStatus: string;
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
  const data = await res.json();
  return data.listInfoList ?? [];
}

export async function getListItems(listId: string): Promise<AlexaItem[]> {
  const res = await fetch(`${BASE_URL}/lists/${listId}/items`);
  if (!res.ok) throw new Error('Failed to fetch items');
  return res.json();
}

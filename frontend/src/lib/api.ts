import { z } from 'zod';
import type { components } from './api-schema';

export type Session = components['schemas']['SessionResponse'];
export type Access = components['schemas']['AccessResponse'];
export type Party = components['schemas']['Party'];
export type Account = components['schemas']['FinancialAccount'];
export type Page<T> = { count: number; next: string | null; previous: string | null; results: T[] };

export class ApiError extends Error {
  constructor(public readonly status: number, message: string) { super(message); }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try { response = await fetch(path, { ...init, credentials: 'same-origin', headers: { Accept: 'application/json', ...init.headers } }); }
  catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new ApiError(0, 'Connexion au service impossible. Vérifiez votre connexion puis réessayez.');
  }
  if (!response.ok) {
    const messages: Record<number, string> = {
      400: 'Données invalides. Vérifiez les champs saisis.',
      409: 'Version obsolète. Rechargez les données avant de modifier.',
      413: 'Le fichier ou la requête dépasse la taille autorisée.',
      403: 'Votre session a expiré ou vous ne disposez pas des droits nécessaires.',
      404: 'Cet élément est introuvable ou ne vous est pas accessible.',
      429: 'Trop de tentatives. Réessayez dans quelques minutes.',
    };
    let detail='';
    if ([400,409,429].includes(response.status)) {
      const flatten=(value:unknown):string => typeof value==='string' ? value : Array.isArray(value) ? value.map(flatten).join(' · ') : value && typeof value==='object' ? Object.entries(value).map(([key,item])=>`${key} : ${flatten(item)}`).join(' · ') : '';
      try { const error=await response.json(); detail=flatten(error.error?.details).slice(0,1500); } catch { /* generic fallback */ }
    }
    throw new ApiError(response.status, detail || messages[response.status] || 'Le service rencontre une difficulté. Réessayez ultérieurement.');
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export async function mutate<T>(path: string, body?: unknown, method='POST') {
  const csrf = await request<components['schemas']['CsrfResponse']>('/api/auth/csrf/');
  return request<T>(path, { method, headers: { 'X-CSRFToken': csrf.csrfToken, 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) });
}

export const api = {
  session: (signal?: AbortSignal) => request<Session>('/api/session/', { signal }),
  access: (signal?: AbortSignal) => request<Access>('/api/auth/access/', { signal }),
  login: (data: { username: string; password: string }) => mutate<Session>('/api/auth/login/', data),
  logout: () => mutate<void>('/api/auth/logout/'),
  clients: (params: { search?: string; kind?: string; page?: number; pageSize?: number; profession?:string; sector?:string; profession_missing?:string; sector_missing?:string; ordering?:string; completeness_min?:string; completeness_max?:string; missing_field?:string } = {}, signal?: AbortSignal) => {
    const query = new URLSearchParams({ page: String(params.page ?? 1), page_size: String(params.pageSize ?? 8) });
    if (params.search) query.set('search', params.search);
    if (params.kind) query.set('kind', params.kind);
    for (const key of ['profession','sector','profession_missing','sector_missing','ordering','completeness_min','completeness_max','missing_field'] as const) {
      if(params[key]!==undefined && params[key]!=='')query.set(key,params[key]);
    }
    return request<Page<Party>>(`/api/clients/?${query}`, { signal });
  },
  client: (id: string, signal?: AbortSignal) => request<Party>(`/api/clients/${encodeURIComponent(id)}/`, { signal }),
  accounts: (id: string, signal?: AbortSignal) => request<Page<Account>>(`/api/clients/${encodeURIComponent(id)}/accounts/`, { signal }),
};

export async function getHealth(signal?: AbortSignal) {
  return z.object({ status: z.literal('ok') }).parse(await request('/api/health/', { signal }));
}

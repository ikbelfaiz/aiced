import { createContext, useContext, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { api, ApiError, type Session, type Access } from '../../lib/api';

type Identity = { session: Session; access: Access };
type AuthContextValue = {
  identity: Identity | null | undefined; pending: boolean; error: Error | null;
  can: (code: string) => boolean; refresh: () => Promise<unknown>;
  signIn: (data: { username: string; password: string }) => Promise<void>;
  signOut: () => Promise<void>;
};
const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const identity = useQuery({
    queryKey: ['identity'], retry: false, staleTime: 0, refetchInterval: 30_000,
    queryFn: async ({ signal }): Promise<Identity | null> => {
      let session: Session;
      try { session = await api.session(signal); }
      catch (error) { if (error instanceof ApiError && error.status === 403) return null; throw error; }
      return { session, access: await api.access(signal) };
    },
  });
  const clearPrivateData = async () => {
    await client.cancelQueries({ predicate: (query) => query.queryKey[0] !== 'identity' });
    client.removeQueries({ predicate: (query) => query.queryKey[0] !== 'identity' });
  };
  const value: AuthContextValue = {
    identity: identity.data, pending: identity.isPending, error: identity.error,
    can: (code) => !identity.error && Boolean(identity.data?.access.assignments.some((grant) =>
      (!grant.expires_at || new Date(grant.expires_at).getTime() > Date.now()) && grant.permissions.includes(code))),
    refresh: async () => { await clearPrivateData(); return identity.refetch(); },
    signIn: async (data) => {
      await client.cancelQueries({ queryKey: ['identity'] });
      await api.login(data);
      await clearPrivateData();
      const session = await api.session();
      const access = await api.access();
      client.setQueryData(['identity'], { session, access });
    },
    signOut: async () => {
      await api.logout();
      await client.cancelQueries({ queryKey: ['identity'] });
      await clearPrivateData();
      client.setQueryData(['identity'], null);
    },
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('AuthProvider requis.');
  return value;
}

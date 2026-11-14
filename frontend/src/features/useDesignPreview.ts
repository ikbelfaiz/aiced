import { useLocation, useSearchParams } from 'react-router-dom';
import { useAuth } from './auth/AuthProvider';

export function useDesignPreview() {
  const [params] = useSearchParams();
  const {pathname}=useLocation();
  const { can } = useAuth();
  return import.meta.env.DEV && ['/tableau-de-bord','/clients'].includes(pathname) && params.get('apercu') === 'maquette' && can('clients.view') && can('clients.view_financial');
}

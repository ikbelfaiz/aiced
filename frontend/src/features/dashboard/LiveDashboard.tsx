import {useQuery} from '@tanstack/react-query';
import {Link} from 'react-router-dom';
import {api} from '../../lib/api';
import {useAuth} from '../auth/AuthProvider';
import {CommercialActivity} from '../reporting/CommercialActivity';
import {formatNumber} from '../clients/model';

/** Compose existing authorized reports; never treat source rows as CRM identities. */
export function LiveDashboard(){
  const auth=useAuth();
  const allowed=auth.can('clients.view');
  const clients=useQuery({queryKey:['clients-count',auth.identity?.session.id],queryFn:({signal})=>api.clients({pageSize:1},signal),enabled:allowed,retry:false,refetchOnWindowFocus:false});
  const count=allowed&&!clients.isError&&clients.data?formatNumber(clients.data.count):'—';
  return <>
    <div className="page-heading"><div><p className="page-eyebrow">AMEN INVEST · AICED</p><h1>Tableau de bord</h1><p className="page-subtitle">Données CRM enregistrées, limitées à votre périmètre autorisé.</p></div></div>
    <section className="primary-metrics" aria-label="Indicateurs principaux">
      <article className="card metric-card" aria-label="Clients accessibles"><p>Clients accessibles</p><strong>{count}</strong><span className="muted">{!allowed?'Accès clients non autorisé':clients.isError?'Source Client indisponible':clients.isPending?'Chargement…':'Clients CRM actuels, prospects exclus · toutes dates'}</span><Link className="text-link" to="/clients">Consulter les clients</Link></article>
      <article className="card metric-card"><p>Encours</p><strong>—</strong><span className="muted">Valorisations et définition financière approuvée indisponibles.</span></article>
      <article className="card metric-card"><p>Taux de rétention</p><strong>—</strong><span className="muted">Population, période et méthode de calcul non approuvées.</span></article>
      <article className="card metric-card"><p>Segmentation métier</p><strong>—</strong><span className="muted">Taxonomie non approuvée. Les filtres CRM profession et secteur restent disponibles.</span></article>
    </section>
    <section className="card workspace-card"><h2>Imports Excel et données CRM</h2><p>Un dépôt est conservé en staging pour validation. Après revue distincte et publication explicite, ses lignes sont des snapshots source immuables. Elles ne créent ni client CRM ni compte et ne constituent pas des indicateurs financiers.</p><p>Le rapprochement source / client et les droits de consultation par objet restent à approuver par AMEN INVEST.</p><Link className="text-link" to="/gestion-donnees">Consulter les imports et leur publication</Link></section>
    <CommercialActivity embedded/>
  </>;
}

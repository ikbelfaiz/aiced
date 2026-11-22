import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ArrowUpRight, CalendarDays, Download, Lightbulb } from 'lucide-react';
import { CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, XAxis, YAxis } from 'recharts';
import { api } from '../../lib/api';
import { useAuth } from '../auth/AuthProvider';
import { useDesignPreview } from '../useDesignPreview';
import { previewSegments, previewTrend } from '../design-preview';
import { Badge, Button, StatePanel } from '../../components/ui';
import { formatNumber } from '../clients/model';
import { LiveDashboard } from './LiveDashboard';

function ChartPlaceholder({ children }: { children: string }) { return <div className="chart-placeholder"><p>{children}</p><span>Aucune donnée disponible</span></div>; }

function TrendChart({ activity = false }: { activity?: boolean }) {
  return <div className={activity ? 'activity-plot' : 'trend-plot'} role="img" aria-label={activity ? 'Illustration fictive : tendance des interactions d’avril à septembre 2026' : 'Illustration fictive : évolution du nombre de clients d’avril à septembre 2026'}>
    <ResponsiveContainer width="100%" height="100%"><LineChart data={previewTrend} margin={{ top: 18, right: 8, left: -24, bottom: 14 }}>
      <CartesianGrid stroke="#e1e7ea" vertical={false} /><XAxis dataKey="month" axisLine={false} tickLine={false} tickMargin={18} tick={{ fontSize: 10, fill: '#66727f' }} />
      <YAxis domain={activity ? [180, 320] : [980, 1300]} ticks={activity ? [200, 240, 280, 320] : [1000, 1100, 1200, 1300]} axisLine={false} tickLine={false} tick={{ fontSize: 9, fill: '#6b7280' }} tickFormatter={formatNumber} />
      <Line type="monotone" dataKey={activity ? 'activity' : 'clients'} stroke="#2d8798" strokeWidth={3} dot={false} isAnimationActive={false} />
    </LineChart></ResponsiveContainer>
  </div>;
}

export function DashboardPage() {
  const preview = useDesignPreview();
  return preview ? <PreviewDashboard/> : <LiveDashboard/>;
}

function PreviewDashboard() {
  const auth = useAuth();
  const preview = true;
  const canClients = auth.can('clients.view');
  const clients = useQuery({ queryKey: ['clients-count', auth.identity?.session.id], queryFn: ({ signal }) => api.clients({ pageSize: 1 }, signal), enabled: canClients, retry: false });
  const count = preview ? '1 248' : clients.data ? formatNumber(clients.data.count) : '—';
  const primaryCards = [
    { title: preview ? 'Clients actifs' : 'Clients accessibles', value: count, caption: preview ? '+6,8 % par rapport à août' : canClients ? 'Dans votre périmètre autorisé' : 'Accès clients non autorisé' },
    { title: 'Opportunités en cours', value: preview ? '42' : '—', caption: preview ? '2,85 M TND de potentiel' : 'Module commercial non disponible' },
    { title: 'Encours', value: preview ? '82,4 M TND' : '—', caption: preview ? '+8,2 % sur le trimestre' : auth.can('clients.view_financial') ? 'Source financière non connectée' : 'Accès financier non autorisé' },
    { title: 'Taux de rétention', value: preview ? '94,2 %' : '—', caption: preview ? '+1,4 point sur le trimestre' : 'Méthode de calcul à définir' },
  ];
  const secondaryCards = [
    { title: 'Nouveaux clients', value: '28', caption: '+5 ce mois' }, { title: 'Clients à relancer', value: '18', caption: '6 prioritaires' },
    { title: 'Campagnes en cours', value: '4', caption: '312 clients ciblés' }, { title: 'Clients à risque de désengagement', value: '12', caption: '3 à risque élevé' },
  ];
  return <>
    <div className="page-heading"><div><p className="page-eyebrow">AICED · PILOTAGE</p><h1>Tableau de bord</h1><p className="page-subtitle">Bonjour{preview ? ' Leïla' : ''}, voici l’essentiel de votre activité et les priorités du jour.</p></div><div className="heading-actions"><Button disabled title="Le filtrage des indicateurs par période n’est pas disponible"><CalendarDays size={16} />{preview ? 'Septembre 2026' : 'Période non disponible'}</Button><Button disabled title="L’API d’export n’est pas disponible"><Download size={17} />Exporter</Button></div></div>
    {canClients && clients.isPending && <StatePanel kind="loading" title="Chargement du tableau de bord…" />}
    {canClients && clients.isError ? <StatePanel kind="error" title="Impossible de charger le tableau de bord" retry={() => void clients.refetch()}>{clients.error.message}</StatePanel> : (!clients.isPending || !canClients) && <>
      <section className="primary-metrics" aria-label="Indicateurs principaux">{primaryCards.map((card) => <article className="card metric-card" key={card.title}><p>{card.title}</p><strong>{card.value}</strong><span className={preview ? 'positive' : 'muted'}>{card.caption}</span></article>)}</section>
      <section className="secondary-metrics" aria-label="Suivi de l’activité">{secondaryCards.map((card) => <article className="card small-metric" key={card.title}><p>{card.title}</p><div><strong>{preview ? card.value : '—'}</strong><span className={preview && card.title.includes('risque') ? 'negative' : ''}>{preview ? card.caption : 'Non disponible'}</span><ArrowUpRight size={18} aria-hidden="true" /></div></article>)}</section>
      <div className="dashboard-charts"><section className="card trend-card"><h2>Évolution du nombre de clients</h2><p className="card-subtitle">{preview ? 'Avril – septembre 2026' : 'Historique non disponible dans l’API'}</p>{preview ? <><span className="chart-change">+6,8 %</span><TrendChart /></> : <ChartPlaceholder>L’historique des clients n’est pas encore connecté.</ChartPlaceholder>}</section>
        <section className="card segment-card"><h2>Répartition des clients par segment</h2><p className="card-subtitle">{preview ? 'Portefeuille global · 1 248 clients' : 'Segmentation métier à définir'}</p>{preview ? <div className="segment-body"><div className="segment-donut" role="img" aria-label="Répartition fictive : 762 particuliers, 274 VIP, 112 institutionnels, 100 personnel AMEN BANK"><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={previewSegments} dataKey="value" innerRadius="73%" outerRadius="99%" startAngle={90} endAngle={-270} paddingAngle={1} stroke="white" isAnimationActive={false}>{previewSegments.map((segment) => <Cell key={segment.name} fill={segment.color} />)}</Pie></PieChart></ResponsiveContainer><div><strong>1 248</strong><span>TOTAL</span></div></div><ul className="segment-legend">{previewSegments.map((segment) => <li key={segment.name}><span><i style={{ background: segment.color }} />{segment.name}</span><strong>{segment.value}</strong></li>)}</ul></div> : <ChartPlaceholder>Les règles de segmentation n’ont pas été approuvées.</ChartPlaceholder>}</section></div>
      <div className="dashboard-bottom"><section className="card pipeline-card"><h2>Pipeline des opportunités</h2><p className="card-subtitle">{preview ? '42 dossiers ouverts · 2,85 M TND' : 'Source commerciale non connectée'}</p>{preview ? <><div className="pipeline-bars">{[{ label: 'Nouvelle', value: '12 · 960 k', width: '65%' }, { label: 'En cours', value: '18 · 1,25 M', width: '97%' }, { label: 'À relancer', value: '12 · 640 k', width: '65%' }].map((bar) => <div key={bar.label}><p>{bar.label}<strong> · {bar.value}</strong></p><i style={{ width: bar.width }} /></div>)}</div><p className="micro muted">Valeurs fictives en TND · maquette uniquement</p></> : <ChartPlaceholder>Aucune opportunité disponible dans cette version.</ChartPlaceholder>}</section>
        <section className="card activity-card"><h2>Tendance de l’activité</h2><p className="card-subtitle">{preview ? 'Interactions enregistrées · 312 en septembre' : 'Historique d’interactions non connecté'}</p>{preview ? <><TrendChart activity /><div className="activity-legend"><Badge tone="blue">Appels · 148</Badge><Badge tone="green">Emails · 96</Badge><span>Autres · 68</span></div></> : <ChartPlaceholder>Les interactions seront disponibles avec le module commercial.</ChartPlaceholder>}</section>
        <section className="card priorities-card"><div className="card-title-row"><h2>Actions prioritaires</h2><button className="text-link" disabled title="Agenda non disponible">Tout voir</button></div><p className="card-subtitle">{preview ? 'Aujourd’hui · vendredi 2 octobre' : 'Agenda commercial non connecté'}</p>{preview ? <div className="priority-list"><div><p>Relancer Nadia Trabelsi<Badge tone="red">Urgent</Badge></p><span>Dernier contact : 20 juillet · risque élevé</span></div><div><p>Rendez-vous avec Karim Ben Youssef<Badge tone="blue">À venir</Badge></p><span>10:30 · Bilan de portefeuille · 45 min</span></div><div><p>Contacter Atlas Industries<Badge tone="amber">En retard</Badge></p><span>Relance en retard depuis le 30 septembre</span></div></div> : <ChartPlaceholder>Aucune action disponible dans cette version.</ChartPlaceholder>}<Button disabled title="Les recommandations ne sont pas implémentées"><Lightbulb size={16} />Voir mes recommandations</Button></section></div>
      {!preview && canClients && clients.data?.count === 0 && <div className="empty-dashboard"><p>Aucun client dans votre périmètre.</p><Link className="text-link" to="/clients">Consulter le répertoire clients</Link></div>}
    </>}
  </>;
}

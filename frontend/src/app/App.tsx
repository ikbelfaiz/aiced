const ProspectFollowups = lazy(() => import('../features/prospects/ProspectFollowups').then(module=>({default:module.ProspectFollowups})));
const OpportunityPipeline = lazy(() => import('../features/opportunities/OpportunityPipeline').then(module=>({default:module.OpportunityPipeline})));
const AgendaPage=lazy(()=>import('../features/agenda/AgendaPage').then(module=>({default:module.AgendaPage})));
const CampaignsPage=lazy(()=>import('../features/campaigns/CampaignsPage').then(module=>({default:module.CampaignsPage})));
const CommercialActivity=lazy(()=>import('../features/reporting/CommercialActivity').then(module=>({default:module.CommercialActivity})));
import { useEffect, lazy, Suspense } from "react";
import {
  Link,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
} from "react-router-dom";
import { AppShell } from "../components/layout/AppShell";
import { StatePanel } from "../components/ui";
import { AuthProvider, useAuth } from "../features/auth/AuthProvider";
import { LoginPage } from "../features/auth/LoginPage";
import { DashboardPage } from "../features/dashboard/DashboardPage";
import { ClientsPage } from "../features/clients/ClientsPage";
const InteractionHistory = lazy(() => import('../features/interactions/InteractionHistory').then(module=>({default:module.InteractionHistory})));
const ClientWorkspace = lazy(() =>
  import("../features/clients/ClientWorkspace").then((module) => ({
    default: module.ClientWorkspace,
  })),
);
const DataManagement = lazy(() =>
  import("../features/imports/DataManagement").then((module) => ({
    default: module.DataManagement,
  })),
);
const ProspectsPage = lazy(() =>
  import("../features/prospects/ProspectsPage").then((module) => ({
    default: module.ProspectsPage,
  })),
);

function AuthGate() {
  const auth = useAuth();
  const location = useLocation();
  if (auth.pending)
    return (
      <main id="main" className="auth-state">
        <StatePanel kind="loading" title="Vérification de votre session…" />
      </main>
    );
  if (auth.error)
    return (
      <main id="main" className="auth-state">
        <StatePanel
          kind="error"
          title="Impossible de vérifier votre session"
          retry={() => void auth.refresh()}
        >
          {auth.error.message}
        </StatePanel>
      </main>
    );
  if (!auth.identity)
    return (
      <Navigate
        to="/connexion"
        state={{ from: location.pathname + location.search }}
        replace
      />
    );
  return <AppShell />;
}

function ClientsGate() {
  const auth = useAuth();
  if (!auth.can("clients.view"))
    return (
      <StatePanel kind="denied" title="Accès non autorisé">
        Votre rôle ne permet pas de consulter les clients.{" "}
        <Link className="text-link" to="/tableau-de-bord">
          Revenir au tableau de bord
        </Link>
      </StatePanel>
    );
  return <Outlet />;
}

function PageTitle() {
  const location = useLocation();
  useEffect(() => {
    document.title = `${location.pathname === "/activite-commerciale" ? "Activit\u00e9 commerciale" : location.pathname === "/campagnes" ? "Mes brouillons de campagnes" : location.pathname === "/agenda" ? "Mon agenda" : location.pathname === "/opportunites" ? "Pipeline des opportunit\u00e9s" : location.pathname === "/prospects/relances" ? "Relances prospects" : location.pathname === "/interactions" ? "Historique des interactions" : location.pathname === "/prospects" ? "Prospects" : location.pathname === "/connexion" ? "Connexion" : location.pathname === "/clients" ? "Panorama Clients" : location.pathname.startsWith("/clients/") ? "Client 360°" : location.pathname === "/gestion-donnees" ? "Gestion des données" : "Tableau de bord"} · AICED`;
  }, [location.pathname]);
  return null;
}

export function App() {
  return (
    <AuthProvider>
      <PageTitle />
      <a className="skip-link" href="#main">
        Aller au contenu
      </a>
      <Routes>
        <Route path="/connexion" element={<LoginPage />} />
        <Route element={<AuthGate />}>
          <Route path="/activite-commerciale" element={<Suspense fallback={<StatePanel kind="loading" title="Chargement des rapports…"/>}><CommercialActivity/></Suspense>}/>
          <Route path="/pilotage-crm" element={<Suspense fallback={<StatePanel kind="loading" title="Chargement du pilotage CRM…"/>}><CommercialActivity managerial/></Suspense>}/>
          <Route path="/agenda" element={<Suspense fallback={<StatePanel kind="loading" title="Chargement de l’agenda"/>}><AgendaPage/></Suspense>}/>
          <Route path="/campagnes" element={<Suspense fallback={<StatePanel kind="loading" title="Chargement des campagnes"/>}><CampaignsPage/></Suspense>}/>
          <Route path="/opportunites" element={<Suspense fallback={<StatePanel kind="loading" title="Chargement du pipeline"/>}><OpportunityPipeline/></Suspense>}/>
          <Route path="/prospects/relances" element={<Suspense fallback={<StatePanel kind="loading" title="Chargement des relances"/>}><ProspectFollowups/></Suspense>}/>
          <Route path="/interactions" element={<Suspense fallback={<StatePanel kind="loading" title="Chargement des interactions…"/>}><InteractionHistory/></Suspense>} />
          <Route index element={<Navigate to="/tableau-de-bord" replace />} />
          <Route path="/tableau-de-bord" element={<DashboardPage />} />
          <Route
            path="/prospects"
            element={
              <Suspense
                fallback={
                  <StatePanel
                    kind="loading"
                    title="Chargement des prospects…"
                  />
                }
              >
                <ProspectsPage />
              </Suspense>
            }
          />
          <Route element={<ClientsGate />}>
            <Route path="/clients" element={<ClientsPage />} />
            <Route
              path="/clients/:id"
              element={
                <Suspense
                  fallback={
                    <StatePanel
                      kind="loading"
                      title="Chargement de la fiche…"
                    />
                  }
                >
                  <ClientWorkspace />
                </Suspense>
              }
            />
          </Route>
          <Route
            path="/gestion-donnees"
            element={
              <Suspense
                fallback={
                  <StatePanel
                    kind="loading"
                    title="Chargement de la gestion des données…"
                  />
                }
              >
                <DataManagement />
              </Suspense>
            }
          />
          <Route
            path="*"
            element={
              <StatePanel kind="empty" title="Page introuvable">
                <Link className="text-link" to="/tableau-de-bord">
                  Revenir au tableau de bord
                </Link>
              </StatePanel>
            }
          />
        </Route>
      </Routes>
    </AuthProvider>
  );
}

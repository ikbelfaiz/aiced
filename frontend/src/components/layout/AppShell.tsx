import { useEffect, useState } from "react";
import {
  Link,
  NavLink,
  Outlet,
  useLocation,
  useNavigate,
} from "react-router-dom";
import {
  Bell,
  ChevronDown,
  LogOut,
  Menu,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import { useAuth } from "../../features/auth/AuthProvider";
import { useDesignPreview } from "../../features/useDesignPreview";
import { Button } from "../ui";

const futureNavigation = [
  "Segmentation",
  "Prospects",
  "Opportunités",
  "Interactions",
  "Agenda",
  "Campagnes",
  "Pilotage",
  "Assistant IA",
  "Administration",
];

export function AppShell() {
  const auth = useAuth();
  const preview = useDesignPreview();
  const location = useLocation();
  const navigate = useNavigate();
  const [menu, setMenu] = useState(false);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [loggingOut, setLoggingOut] = useState(false);
  useEffect(() => {
    setMenu(false);
    document.getElementById("main")?.focus({ preventScroll: true });
  }, [location.pathname]);
  useEffect(() => {
    if (!menu) return;
    (
      document.querySelector(".mobile-close") as HTMLButtonElement | null
    )?.focus();
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenu(false);
        (
          document.querySelector(".mobile-menu") as HTMLButtonElement | null
        )?.focus();
      }
    };
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [menu]);
  const username = auth.identity?.session.username ?? "";
  const initials = username
    .replace(/^synthetic\./, "")
    .split(/[.\s@_-]/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();
  async function logout() {
    setError("");
    setLoggingOut(true);
    try {
      await auth.signOut();
      navigate("/connexion", { replace: true });
    } catch (failure) {
      setError(
        failure instanceof Error ? failure.message : "La déconnexion a échoué.",
      );
    } finally {
      setLoggingOut(false);
    }
  }
  return (
    <div className="app-shell">
      {menu && (
        <button
          className="sidebar-backdrop"
          aria-label="Fermer la navigation"
          onClick={() => setMenu(false)}
        />
      )}
      <aside
        className={`sidebar ${menu ? "sidebar-open" : ""}`}
        aria-label="Navigation principale"
      >
        <div className="sidebar-logo">
          <strong>AICED</strong>
          <span>AMEN INVEST · CRM</span>
          <button
            className="mobile-close icon-button"
            aria-label="Fermer la navigation"
            onClick={() => setMenu(false)}
          >
            <X size={20} />
          </button>
        </div>
        <nav>
          <NavLink
            to={`/tableau-de-bord${preview ? "?apercu=maquette" : ""}`}
            className={({ isActive }) =>
              `nav-item ${isActive ? "nav-active" : ""}`
            }
          >
            Tableau de bord
          </NavLink>
          {auth.can("clients.view") ? (
            <NavLink
              to={`/clients${preview ? "?apercu=maquette" : ""}`}
              className={({ isActive }) =>
                `nav-item ${isActive ? "nav-active" : ""}`
              }
            >
              Clients
            </NavLink>
          ) : (
            <button
              className="nav-item"
              disabled
              title="Permission clients.view requise"
            >
              Clients
            </button>
          )}
          {futureNavigation.map((name) =>
            name === "Prospects" &&
            auth.can("prospects.view") &&
            auth.can("clients.view") ? (
              <NavLink
                key={name}
                to="/prospects"
                className={({ isActive }) =>
                  "nav-item " + (isActive ? "nav-active" : "")
                }
              >
                Prospects
              </NavLink>
            ) : name === "Administration" &&
              auth.can("imports.view") &&
              auth.can("clients.view_financial") ? (
              <NavLink
                key={name}
                to="/gestion-donnees"
                className={({ isActive }) =>
                  `nav-item ${isActive ? "nav-active" : ""}`
                }
              >
                Gestion des données
              </NavLink>
            ) : (
              <button
                key={name}
                className="nav-item"
                disabled
                title="Module non disponible dans cette version"
              >
                {name}
              </button>
            ),
          )}
          <p className="nav-section-label">INTELLIGENCE COMMERCIALE</p>
          {["Fidélisation", "Documents intelligents", "Recommandations"].map(
            (name) => (
              <button
                key={name}
                className="nav-item nav-secondary"
                disabled
                title="Module non disponible dans cette version"
              >
                {name}
              </button>
            ),
          )}
        </nav>
        <div className="sidebar-bottom">
          <div className="secure-box">
            <strong>Espace sécurisé</strong>
            <span>Accès professionnel</span>
          </div>
          <strong className="sidebar-amen">AMEN INVEST</strong>
          <p>Clients · Exploitation · Développement</p>
        </div>
      </aside>
      <div className="workspace" inert={menu}>
        <header className="topbar">
          <button
            className="mobile-menu icon-button"
            aria-label="Ouvrir la navigation"
            aria-expanded={menu}
            onClick={() => setMenu(!menu)}
          >
            <Menu size={22} />
          </button>
          <span className="workspace-label">Espace commercial</span>
          <form
            className="global-search input-with-icon"
            onSubmit={(event) => {
              event.preventDefault();
              if (auth.can("clients.view"))
                navigate(
                  `/clients?recherche=${encodeURIComponent(search)}${preview ? "&apercu=maquette" : ""}`,
                );
            }}
          >
            <Search size={17} />
            <input
              aria-label="Rechercher dans AICED"
              placeholder="Rechercher dans AICED…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              disabled={!auth.can("clients.view")}
            />
          </form>
          <button
            className="icon-button notification-button"
            aria-label="Notifications non disponibles"
            title="Notifications non disponibles"
            disabled
          >
            <Bell size={20} />
          </button>
          <details className="profile-menu">
            <summary>
              <span className="avatar">{initials || "AI"}</span>
              <span className="profile-text">
                <strong>{username}</strong>
                <small>Collaborateur habilité</small>
              </span>
              <ChevronDown size={15} />
            </summary>
            <div className="profile-popover">
              <p>Session sécurisée</p>
              <Button variant="text" onClick={() => void auth.refresh()}>
                <RefreshCw size={14} />
                Actualiser mes droits
              </Button>
              <Button
                variant="text"
                disabled={loggingOut}
                onClick={() => void logout()}
              >
                <LogOut size={14} />
                {loggingOut ? "Déconnexion…" : "Se déconnecter"}
              </Button>
            </div>
          </details>
        </header>
        {error && (
          <div role="alert" className="shell-error">
            {error}
          </div>
        )}
        <main id="main" tabIndex={-1} className="workspace-main">
          {import.meta.env.DEV && (
            <div
              className={`development-notice ${preview ? "preview-notice" : ""}`}
            >
              <span>
                {preview
                  ? "MAQUETTE · Valeurs fictives de référence, sans calcul de scoring ni prédiction."
                  : "DÉVELOPPEMENT · Utiliser uniquement des données synthétiques."}
              </span>
              {["/tableau-de-bord", "/clients"].includes(location.pathname) &&
                auth.can("clients.view") &&
                auth.can("clients.view_financial") && (
                  <Link
                    to={`${location.pathname}${preview ? "" : "?apercu=maquette"}`}
                  >
                    {preview ? "Revenir aux données API" : "Aperçu maquette"}
                  </Link>
                )}
            </div>
          )}
          <Outlet />
          <footer className="app-footer">
            <span>
              AICED – AMEN INVEST Clients Exploitation &amp; Développement
            </span>
            <span>
              {preview
                ? "Maquette · Données fictives · 02 octobre 2026"
                : "Données API · Périmètre autorisé"}
            </span>
          </footer>
        </main>
      </div>
    </div>
  );
}

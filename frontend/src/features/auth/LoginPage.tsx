import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { ArrowRight, ChevronDown, Eye, EyeOff, LockKeyhole, Mail, ShieldCheck } from 'lucide-react';
import { useAuth } from './AuthProvider';
import { Button, Dialog } from '../../components/ui';

const loginSchema = z.object({ username: z.string().min(1, 'Renseignez votre identifiant professionnel.').max(150), password: z.string().min(1, 'Renseignez votre mot de passe.').max(4096) });
type LoginValues = z.infer<typeof loginSchema>;

export function LoginPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [visible, setVisible] = useState(false);
  const [help, setHelp] = useState(false);
  const [error, setError] = useState('');
  const form = useForm<LoginValues>({ resolver: zodResolver(loginSchema), defaultValues: { username: '', password: '' } });
  const requested = (location.state as { from?: string } | null)?.from;
  const destination = requested?.startsWith('/') && !requested.startsWith('//') && requested !== '/connexion' ? requested : '/tableau-de-bord';
  if (auth.identity && !auth.error) return <Navigate to={destination} replace />;
  const submit = form.handleSubmit(async (values) => {
    setError('');
    try {
      await auth.signIn(values);
      form.resetField('password');
      navigate(destination, { replace: true });
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'La connexion a échoué. Réessayez.'); }
  });
  return <main id="main" className="login-page">
    <aside className="login-brand" aria-label="AICED, AMEN INVEST">
      <div className="login-logo"><span />AICED</div>
      <div className="login-story"><p className="login-eyebrow">LA RELATION CLIENT, AU CŒUR DE LA PERFORMANCE</p>
        <h1>Une vision claire.<br />Une relation durable.</h1><div className="green-rule" />
        <p className="login-product">AMEN INVEST Clients<br />Exploitation &amp; Développement</p>
        <p className="login-description">Votre environnement de travail pour comprendre vos clients, développer leur potentiel et accompagner chaque relation.</p>
      </div>
      <div className="brand-orbit" aria-hidden="true"><i /><b /></div>
      <div className="login-brand-footer"><strong>AMEN INVEST</strong><p>Expertise financière. Proximité client.</p></div>
    </aside>
    <section className="login-content" aria-labelledby="login-title">
      <header className="login-top"><span>PLATEFORME PROFESSIONNELLE</span><span className="language">Français <ChevronDown size={14} /></span></header>
      <div className="login-form-wrap">
        <div className="shield"><ShieldCheck size={24} /></div>
        <h2 id="login-title">Bienvenue sur AICED</h2>
        <p className="login-subtitle">Connectez-vous à votre espace sécurisé AMEN INVEST.</p>
        <form onSubmit={submit} noValidate>
          <label htmlFor="username">Identifiant professionnel</label>
          <div className="input-with-icon"><Mail size={19} /><input id="username" autoComplete="username" placeholder="Votre identifiant AICED" aria-invalid={Boolean(form.formState.errors.username)} aria-describedby={form.formState.errors.username ? 'username-error' : undefined} {...form.register('username')} /></div>
          {form.formState.errors.username && <p className="field-error" id="username-error">{form.formState.errors.username.message}</p>}
          <label htmlFor="password" className="password-label">Mot de passe</label>
          <div className="input-with-icon"><LockKeyhole size={19} /><input id="password" type={visible ? 'text' : 'password'} autoComplete="current-password" placeholder="Votre mot de passe" aria-invalid={Boolean(form.formState.errors.password)} aria-describedby={form.formState.errors.password ? 'password-error' : undefined} {...form.register('password')} /><button className="icon-button" type="button" aria-label={visible ? 'Masquer le mot de passe' : 'Afficher le mot de passe'} onClick={() => setVisible(!visible)}>{visible ? <EyeOff size={18} /> : <Eye size={18} />}</button></div>
          {form.formState.errors.password && <p className="field-error" id="password-error">{form.formState.errors.password.message}</p>}
          <div className="login-options"><label title="Session serveur limitée à 30 minutes ; connexion persistante non disponible."><input type="checkbox" disabled /> Se souvenir de moi</label><button type="button" className="text-link" onClick={() => setHelp(true)}>Mot de passe oublié ?</button></div>
          {error && <p role="alert" className="form-error">{error}</p>}
          <Button variant="primary" className="login-submit" disabled={form.formState.isSubmitting}>{form.formState.isSubmitting ? 'Connexion en cours…' : 'Connexion'}<ArrowRight size={18} /></Button>
        </form>
        <div className="login-security"><LockKeyhole size={17} /><p>Accès réservé aux collaborateurs habilités. Vos données et celles de vos clients restent confidentielles.</p></div>
      </div>
      <footer className="login-footer"><div><span>Besoin d’aide ?</span><button className="text-link" onClick={() => setHelp(true)}>Contacter l’administrateur</button></div><p>© 2026 AMEN INVEST · AICED{import.meta.env.DEV ? ' · Développement — données synthétiques uniquement' : ''}</p></footer>
    </section>
    {help && <Dialog title="Assistance à la connexion" onClose={() => setHelp(false)}><p>Contactez votre administrateur AMEN INVEST par votre canal interne habituel. La récupération automatique des mots de passe n’est pas disponible.</p><p className="muted mt-4">La connexion utilise votre identifiant AICED. Une adresse email fonctionne uniquement si elle a été définie comme identifiant par votre administrateur.</p></Dialog>}
  </main>;
}

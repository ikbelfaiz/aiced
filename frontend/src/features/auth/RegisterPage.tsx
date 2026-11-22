import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { ArrowRight, ShieldCheck } from 'lucide-react';
import { Button } from '../../components/ui';
import { mutate } from '../../lib/api';

const schema = z.object({
  username: z.string().trim().min(1, 'Renseignez un identifiant.').max(150),
  email: z.email('Renseignez une adresse email valide.').max(254),
  organization_code: z.string().trim().min(1, 'Renseignez le code de votre institution.').max(60),
  password: z.string().min(12, 'Utilisez au moins 12 caractères.').max(4096),
  confirmation: z.string(),
}).refine(values => values.password === values.confirmation, { path: ['confirmation'], message: 'Les mots de passe ne correspondent pas.' });
type Values = z.infer<typeof schema>;

export function RegisterPage() {
  const [error, setError] = useState('');
  const [done, setDone] = useState('');
  const form = useForm<Values>({ resolver: zodResolver(schema), defaultValues: { username: '', email: '', organization_code: '', password: '', confirmation: '' } });
  const submit = form.handleSubmit(async ({ confirmation: _confirmation, ...values }) => {
    setError('');
    try {
      const result = await mutate<{ detail: string }>('/api/auth/register/', values);
      form.reset();
      setDone(result.detail);
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'La demande a échoué. Réessayez.'); }
  });
  const fields = [
    { name: 'username', label: 'Identifiant professionnel', type: 'text', autoComplete: 'username' },
    { name: 'email', label: 'Email professionnel', type: 'email', autoComplete: 'email' },
    { name: 'organization_code', label: 'Code de votre institution', type: 'text', autoComplete: 'off' },
    { name: 'password', label: 'Mot de passe', type: 'password', autoComplete: 'new-password' },
    { name: 'confirmation', label: 'Confirmer le mot de passe', type: 'password', autoComplete: 'new-password' },
  ] as const;
  return <main id="main" className="login-page registration-page">
    <aside className="login-brand" aria-label="AICED">
      <div className="login-logo"><span />AICED</div>
      <div className="login-story"><p className="login-eyebrow">VOTRE ESPACE PROFESSIONNEL</p><h1>Rejoignez votre<br />institution.</h1><div className="green-rule" /><p className="login-description">Demandez votre compte. Votre responsable vérifie votre demande et définit vos accès.</p></div>
      <div className="login-brand-footer"><strong>AICED</strong><p>Vision client. Décisions éclairées.</p></div>
    </aside>
    <section className="login-content" aria-labelledby="register-title">
      <header className="login-top"><span>PLATEFORME PROFESSIONNELLE</span><Link className="text-link" to="/connexion">Connexion</Link></header>
      <div className="login-form-wrap">
        <div className="shield"><ShieldCheck size={24} /></div>
        <h2 id="register-title">Créer un compte</h2>
        {done ? <div role="status"><p className="login-subtitle">{done}</p><Link className="text-link" to="/connexion">Revenir à la connexion</Link></div> : <>
          <p className="login-subtitle">L’activation nécessite l’accord d’un responsable. Demandez-lui le code de votre institution.</p>
          <form onSubmit={submit} noValidate>
            {fields.map(field => <div className="registration-field" key={field.name}>
              <label htmlFor={`register-${field.name}`}>{field.label}</label>
              <div className="input-with-icon"><input id={`register-${field.name}`} type={field.type} autoComplete={field.autoComplete} aria-invalid={Boolean(form.formState.errors[field.name])} aria-describedby={`${field.name}-help`} {...form.register(field.name)} /></div>
              <p id={`${field.name}-help`} className={form.formState.errors[field.name] ? 'field-error' : 'muted'}>{form.formState.errors[field.name]?.message ?? (field.name === 'password' ? 'Au moins 12 caractères ; évitez les mots de passe courants ou proches de votre identifiant.' : '')}</p>
            </div>)}
            {error && <p role="alert" className="form-error">{error}</p>}
            <Button variant="primary" className="login-submit" disabled={form.formState.isSubmitting}>{form.formState.isSubmitting ? 'Envoi en cours…' : 'Demander mon compte'}<ArrowRight size={18} /></Button>
          </form>
          <p className="registration-signin">Déjà un compte ? <Link className="text-link" to="/connexion">Se connecter</Link></p>
        </>}
      </div>
    </section>
  </main>;
}

import { createClient } from '@supabase/supabase-js';
import { createConsentFlow, readAuthorizationId } from './consent_flow.mjs';

function mount() {
  const root = document.getElementById('monynha-oauth-root');
  if (!root) return;
  const sections = {
    loading: document.getElementById('monynha-oauth-loading'),
    login: document.getElementById('monynha-oauth-login'),
    consent: document.getElementById('monynha-oauth-consent'),
    error: document.getElementById('monynha-oauth-error'),
  };
  const message = document.getElementById('monynha-oauth-message');

  function setText(id, value) { document.getElementById(id).textContent = value; }
  function render(state) {
    for (const [key, section] of Object.entries(sections)) section.hidden = key !== state.view;
    message.hidden = !state.message;
    message.textContent = state.message || '';
    if (state.view !== 'consent') return;
    setText('monynha-oauth-client-name', state.clientName);
    setText('monynha-oauth-client-id', state.clientId);
    setText('monynha-oauth-redirect-uri', state.redirectUri);
    setText('monynha-oauth-scopes', state.scopes.join(', ') || 'No optional identity scopes');
    setText('monynha-oauth-user-email', state.userEmail);
  }

  const authorizationId = readAuthorizationId(window.location.search);
  if (authorizationId !== root.dataset.authorizationId) {
    render({ view: 'error' });
    return;
  }

  let clients;
  try { clients = JSON.parse(root.dataset.allowedClients); }
  catch (_e) { render({ view: 'error' }); return; }
  if (!Array.isArray(clients) || !clients.length || !root.dataset.publishableKey) {
    render({ view: 'error' }); return;
  }
  const supabase = createClient(root.dataset.supabaseUrl, root.dataset.publishableKey, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      storageKey: 'monynha-open2-oauth-facodi',
      detectSessionInUrl: false,
    },
  });
  const flow = createConsentFlow({
    auth: supabase.auth,
    authorizationId,
    allowedClientIds: clients,
    render,
    redirect: url => window.location.assign(url),
  });

  document.getElementById('monynha-oauth-login-form').addEventListener('submit', async event => {
    event.preventDefault();
    const email = document.getElementById('monynha-oauth-email').value;
    const passwordField = document.getElementById('monynha-oauth-password');
    const password = passwordField.value;
    passwordField.value = '';
    await flow.signIn(email, password);
  });
  document.getElementById('monynha-oauth-approve').addEventListener('click', () => flow.approve());
  document.getElementById('monynha-oauth-deny').addEventListener('click', () => flow.deny());
  document.getElementById('monynha-oauth-signout').addEventListener('click', () => flow.signOut());
  void flow.load();
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount);
else mount();

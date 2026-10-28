// Open2 OAuth consent state machine. The server retains all permission decisions.
const AUTHORIZATION_ID = /^[a-zA-Z0-9_-]{8,200}$/;

export function readAuthorizationId(queryString) {
  const params = new URLSearchParams(queryString.startsWith('?') ? queryString.slice(1) : queryString);
  const all = params.getAll('authorization_id');
  return all.length === 1 && AUTHORIZATION_ID.test(all[0]) ? all[0] : null;
}

function validatedRedirect(value) {
  if (typeof value !== 'string' || value.length > 8192) throw new Error('Invalid OAuth redirect');
  const url = new URL(value);
  if (url.protocol !== 'https:' || !url.hostname || url.username || url.password) {
    throw new Error('Invalid OAuth redirect');
  }
  return url.href;
}

export function createConsentFlow({ auth, authorizationId, allowedClientIds, render, redirect }) {
  const approvedClients = new Set(allowedClientIds);
  let details = null;
  let busy = false;

  function fail() {
    details = null;
    render({ view: 'error', message: 'Unable to complete this authorization request.' });
  }

  async function load() {
    details = null;
    if (!authorizationId || !AUTHORIZATION_ID.test(authorizationId) || approvedClients.size === 0) {
      fail();
      return;
    }
    render({ view: 'loading' });
    try {
      const userResponse = await auth.getUser();
      const user = userResponse.data?.user;
      if (userResponse.error || !user) {
        render({ view: 'login' });
        return;
      }
      const { data, error } = await auth.oauth.getAuthorizationDetails(authorizationId);
      if (error || !data) throw new Error('OAuth request not found');
      if (!('authorization_id' in data)) {
        // Supabase returns this form only for an authorization already consented to.
        redirect(validatedRedirect(data.redirect_url));
        return;
      }
      const clientId = data.client?.id || data.client?.client_id;
      if (!approvedClients.has(clientId) || data.authorization_id !== authorizationId) {
        throw new Error('Unapproved OAuth client');
      }
      details = data;
      render({
        view: 'consent',
        clientName: String(data.client?.name || 'OAuth application'),
        clientId,
        redirectUri: String(data.redirect_uri || ''),
        scopes: String(data.scope || '').split(/\s+/).filter(Boolean),
        userEmail: String(user.email || ''),
      });
    } catch (_error) {
      fail();
    }
  }

  async function decide(kind) {
    if (!details || busy) return;
    busy = true;
    render({ view: 'busy' });
    try {
      const response = kind === 'approve'
        ? await auth.oauth.approveAuthorization(authorizationId, { skipBrowserRedirect: true })
        : await auth.oauth.denyAuthorization(authorizationId, { skipBrowserRedirect: true });
      if (response.error || !response.data) throw new Error('OAuth decision failed');
      redirect(validatedRedirect(response.data.redirect_url));
    } catch (_error) {
      fail();
    } finally {
      busy = false;
    }
  }

  async function signIn(email, password) {
    render({ view: 'loading' });
    try {
      const response = await auth.signInWithPassword({ email, password });
      if (response.error) throw new Error('Invalid Open2 credentials');
      await load();
    } catch (_error) {
      render({ view: 'login', message: 'Unable to sign in to Open2.' });
    }
  }

  async function signOut() {
    await auth.signOut();
    details = null;
    render({ view: 'login' });
  }

  return { load, approve: () => decide('approve'), deny: () => decide('deny'), signIn, signOut };
}

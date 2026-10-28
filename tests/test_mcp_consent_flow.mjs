import test from 'node:test';
import assert from 'node:assert/strict';
import { createConsentFlow, readAuthorizationId } from '../facodi_mcp_oauth/static/src/consent_flow.mjs';

function harness({ user: initialUser = { id: 'user-1', email: 'authorized@example.test' }, clientId = 'allowed-client', alreadyApproved = false } = {}) {
  let user = initialUser;
  const calls = [];
  const states = [];
  const redirected = [];
  const auth = {
    async getUser() { return { data: { user }, error: null }; },
    async signInWithPassword({ email }) { calls.push(['login', email]); user = { id: 'user-2', email }; return { data: { user }, error: null }; },
    async signOut() { calls.push(['signout']); return { error: null }; },
    oauth: {
      async getAuthorizationDetails(id) {
        calls.push(['details', id]);
        if (alreadyApproved) return { data: { redirect_url: 'https://chatgpt.com/callback?code=ok' }, error: null };
        return { data: { authorization_id: id, client: { id: clientId, name: 'ChatGPT' }, redirect_uri: 'https://chatgpt.com/callback', scope: 'openid email' }, error: null };
      },
      async approveAuthorization(id, options) { assert.deepEqual(options, { skipBrowserRedirect: true }); calls.push(['approve', id]); return { data: { redirect_url: 'https://chatgpt.com/callback?code=ok' }, error: null }; },
      async denyAuthorization(id, options) { assert.deepEqual(options, { skipBrowserRedirect: true }); calls.push(['deny', id]); return { data: { redirect_url: 'https://chatgpt.com/callback?error=access_denied' }, error: null }; },
    },
  };
  const flow = createConsentFlow({ auth, authorizationId: 'a1234567-aaaa-bbbb-cccc-dddddddddddd', allowedClientIds: ['allowed-client'], render: x => states.push(x), redirect: x => redirected.push(x) });
  return { flow, calls, states, redirected };
}

test('rejects missing/malformed authorization ids before sending requests', async () => {
  assert.equal(readAuthorizationId(''), null);
  assert.equal(readAuthorizationId('?authorization_id=%3Cscript%3E'), null);
  assert.equal(readAuthorizationId('?authorization_id=a1234567-aaaa-bbbb-cccc-dddddddddddd'), 'a1234567-aaaa-bbbb-cccc-dddddddddddd');
});

test('unauthenticated user sees Open2 sign-in and cannot consent', async () => {
  const h = harness({ user: null });
  await h.flow.load();
  assert.equal(h.states.at(-1).view, 'login');
  await h.flow.approve();
  assert.equal(h.calls.some(c => c[0] === 'approve'), false);
});

test('client must match configured allowlist before decisions', async () => {
  const h = harness({ clientId: 'unknown-client' });
  await h.flow.load();
  assert.equal(h.states.at(-1).view, 'error');
  await h.flow.approve();
  await h.flow.deny();
  assert.equal(h.calls.some(c => ['approve', 'deny'].includes(c[0])), false);
});

test('known client shows exact details and redirects after explicit approval', async () => {
  const h = harness();
  await h.flow.load();
  assert.equal(h.states.at(-1).view, 'consent');
  assert.equal(h.states.at(-1).clientName, 'ChatGPT');
  assert.deepEqual(h.states.at(-1).scopes, ['openid', 'email']);
  await h.flow.approve();
  assert.equal(h.calls.find(c => c[0] === 'approve')[1], 'a1234567-aaaa-bbbb-cccc-dddddddddddd');
  assert.equal(h.redirected[0], 'https://chatgpt.com/callback?code=ok');
});

test('deny performs only deny action and redirects to OAuth error', async () => {
  const h = harness();
  await h.flow.load();
  await h.flow.deny();
  assert.equal(h.calls.some(c => c[0] === 'approve'), false);
  assert.match(h.redirected[0], /access_denied/);
});

test('previous consent only follows the authorization server HTTPS redirect', async () => {
  const h = harness({ alreadyApproved: true });
  await h.flow.load();
  assert.deepEqual(h.redirected, ['https://chatgpt.com/callback?code=ok']);
});

test('password login is on Open2 only and returns to consent', async () => {
  const h = harness({ user: null });
  await h.flow.load();
  await h.flow.signIn('authorized@example.test', 'example-password');
  assert.equal(h.calls.some(c => c[0] === 'login'), true);
  assert.equal(h.states.at(-1).view, 'consent');
});

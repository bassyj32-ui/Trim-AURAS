/* TrimAURA Auth — Supabase (Google OAuth only) — public/auth.js
 *
 * - Creates the Supabase client (project URL + anon key are frontend-safe).
 * - Injects the session JWT into every /api/* request (fetch + XHR) so the
 *   backend can verify it (app/auth.py).
 * - Renders the account chip: real name/avatar when signed in, "Sign in"
 *   when signed out.
 * - Auth modal with a single "Continue with Google" button.
 * - One-time legacy-data claim: the first account to sign in adopts the
 *   jobs/clips created before auth existed (user_id = 'default').
 * - Guests are redirected to sign-in when they try to create jobs.
 */
(function () {
  'use strict';

  var SUPABASE_URL = 'https://jbnbjsdralphdbjcwukf.supabase.co';
  var SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImpibmJqc2RyYWxwaGRiamN3dWtmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODUzMzU3NjEsImV4cCI6MjEwMDkxMTc2MX0.A36GAaTnBzg-Lm7NIfXMTrM3YkWbA4I70ptIOB2MWfs';

  var client = null;
  var session = null;

  var USER_ICON =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21a8 8 0 10-16 0"/><circle cx="12" cy="7" r="4"/></svg>';

  var GOOGLE_LOGO =
    '<svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>';

  function toast(msg) {
    if (typeof showToast === 'function') showToast(msg);
  }

  function initials(name) {
    var parts = String(name || '').trim().split(/\s+/).filter(Boolean);
    if (!parts.length) return 'TA';
    var first = parts[0].charAt(0);
    var last = parts.length > 1 ? parts[parts.length - 1].charAt(0) : '';
    return (first + last).toUpperCase();
  }

  // --- Token injection ---------------------------------------------------

  function isApiUrl(url) {
    return url.indexOf('/api/') === 0;
  }

  function patchFetch() {
    var origFetch = window.fetch;
    window.fetch = function (input, init) {
      init = init || {};
      var url = typeof input === 'string' ? input : (input && input.url) || '';
      var isApi = isApiUrl(url);
      var method = String((init && init.method) || (typeof input === 'string' ? 'GET' : (input && input.method) || 'GET')).toUpperCase();

      if (isApi) {
        if (window.__authToken) {
          init.headers = init.headers || {};
          if (Array.isArray(init.headers)) {
            init.headers.push(['Authorization', 'Bearer ' + window.__authToken]);
          } else if (typeof Headers !== 'undefined' && init.headers instanceof Headers) {
            init.headers.set('Authorization', 'Bearer ' + window.__authToken);
          } else {
            init.headers['Authorization'] = 'Bearer ' + window.__authToken;
          }
        } else if (method !== 'GET' && method !== 'HEAD') {
          // Guest write attempt — don't hit the network, prompt to sign in.
          openAuth('Sign in to create clips');
          return Promise.resolve(
            new Response(JSON.stringify({ detail: 'Auth required' }), {
              status: 401,
              headers: { 'Content-Type': 'application/json' },
            })
          );
        }
      }

      return origFetch.call(this, input, init).then(function (res) {
        if (isApi && res.status === 401 && window.__authToken) {
          openAuth('Session expired — sign in again');
        }
        return res;
      });
    };
  }

  function patchXHR() {
    var origOpen = XMLHttpRequest.prototype.open;
    var origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (method, url) {
      this.__taMethod = method;
      this.__taUrl = url;
      return origOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function (body) {
      var url = String(this.__taUrl || '');
      var method = String(this.__taMethod || 'GET').toUpperCase();
      if (isApiUrl(url)) {
        if (window.__authToken) {
          this.setRequestHeader('Authorization', 'Bearer ' + window.__authToken);
        } else if (method !== 'GET' && method !== 'HEAD') {
          openAuth('Sign in to create clips');
          try { this.abort(); } catch (e) {}
          if (typeof this.onerror === 'function') this.onerror();
          return;
        }
        var xhr = this;
        this.addEventListener('load', function () {
          if (xhr.status === 401 && window.__authToken) openAuth('Session expired — sign in again');
        });
      }
      return origSend.apply(this, arguments);
    };
  }

  // --- Auth modal --------------------------------------------------------

  function openAuth(msg) {
    var ov = document.getElementById('authOverlay');
    if (ov) ov.classList.add('open');
    if (msg) toast(msg);
  }

  function closeAuth() {
    var ov = document.getElementById('authOverlay');
    if (ov) ov.classList.remove('open');
  }

  // --- Rendering ---------------------------------------------------------

  function renderAuth() {
    var chip = document.getElementById('accountBtn');
    if (!chip) return;
    var avatarEl = document.getElementById('accountAvatar');
    var nameEl = document.getElementById('accountName');

    if (session && session.user) {
      var meta = session.user.user_metadata || {};
      var fullName = meta.full_name || meta.name || '';
      var email = session.user.email || '';
      var label = fullName || email || 'My account';
      if (avatarEl) {
        if (meta.avatar_url) {
          avatarEl.innerHTML = '<img src="' + meta.avatar_url + '" alt="" width="18" height="18">';
        } else {
          avatarEl.textContent = initials(label);
        }
      }
      if (nameEl) nameEl.textContent = label;
      chip.setAttribute('aria-label', 'Account: ' + label);
    } else {
      if (avatarEl) avatarEl.innerHTML = USER_ICON;
      if (nameEl) nameEl.textContent = 'Sign in';
      chip.setAttribute('aria-label', 'Sign in');
    }
  }

  function wireDom() {
    var closeBtn = document.getElementById('closeAuthBtn');
    var overlay = document.getElementById('authOverlay');
    var googleBtn = document.getElementById('googleSignInBtn');
    if (closeBtn) closeBtn.addEventListener('click', closeAuth);
    if (overlay) {
      overlay.addEventListener('click', function (e) {
        if (e.target === overlay) closeAuth();
      });
      document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && overlay.classList.contains('open')) closeAuth();
      });
    }
    if (googleBtn) googleBtn.addEventListener('click', signInWithGoogle);
  }

  // --- Actions -----------------------------------------------------------

  function signInWithGoogle() {
    if (!client) return;
    var redirectTo = window.location.origin + window.location.pathname;
    client.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: redirectTo },
    });
  }

  function signOut() {
    if (!client) {
      window.location.reload();
      return;
    }
    client.auth.signOut().finally(function () {
      window.location.reload();
    });
  }

  function claimLegacyOnce(user) {
    if (!user || !user.id) return;
    var key = 'trimaura_claimed_' + user.id;
    if (localStorage.getItem(key)) return;
    window.fetch('/api/claim-legacy', { method: 'POST' })
      .then(function (res) { return res.ok ? res.json() : null; })
      .then(function (data) {
        if (data && data.claimed > 0) {
          toast('Welcome — ' + data.claimed + ' saved job' + (data.claimed === 1 ? '' : 's') + ' moved to your account');
        }
        localStorage.setItem(key, '1');
      })
      .catch(function () { /* retry on next load — the endpoint is idempotent */ });
  }

  // --- Boot --------------------------------------------------------------

  function init() {
    if (!window.supabase) return; // CDN unavailable — degrade to static shell
    client = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
      },
    });
    patchFetch();
    patchXHR();
    window.addEventListener('DOMContentLoaded', function () {
      wireDom();
      renderAuth();
    });
    client.auth.getSession().then(function (r) {
      session = r.data.session || null;
      window.__authToken = session ? session.access_token : null;
      renderAuth();
      client.auth.onAuthStateChange(function (_event, s) {
        session = s;
        window.__authToken = session ? session.access_token : null;
        renderAuth();
        if (session && session.user) claimLegacyOnce(session.user);
      });
    });
  }

  window.TrimAuraAuth = {
    openAuth: openAuth,
    closeAuth: closeAuth,
    signInWithGoogle: signInWithGoogle,
    signOut: signOut,
    getUser: function () { return session && session.user ? session.user : null; },
  };

  init();
})();

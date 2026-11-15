/* Connection lifecycle shared by controller, projection and book view. */
(function () {
  'use strict';
  // Open Relay publishes this static-auth secret for its free TURN service.
  // TURN credentials expire; WebRTC data remain end-to-end encrypted.
  async function iceConfig() {
    const iceServers = [
      {urls: 'stun:stun.l.google.com:19302'},
      {urls: 'stun:stun.cloudflare.com:3478'}
    ];
    try {
      if (!window.crypto || !window.crypto.subtle) return {iceServers};
      const username = String(Math.floor(Date.now() / 1000) + 86400) + ':gurbanisearch';
      const enc = new TextEncoder();
      const key = await window.crypto.subtle.importKey('raw', enc.encode('openrelayprojectsecret'), {name:'HMAC', hash:'SHA-1'}, false, ['sign']);
      const bytes = new Uint8Array(await window.crypto.subtle.sign('HMAC', key, enc.encode(username)));
      let raw = ''; for (const byte of bytes) raw += String.fromCharCode(byte);
      const credential = btoa(raw);
      iceServers.push({urls:[
        'turn:staticauth.openrelay.metered.ca:80?transport=udp',
        'turn:staticauth.openrelay.metered.ca:80?transport=tcp',
        'turn:staticauth.openrelay.metered.ca:443?transport=tcp',
        'turns:staticauth.openrelay.metered.ca:443?transport=tcp'
      ], username, credential});
    } catch (_) {} // Retain ordinary STUN connections if secure crypto is unavailable.
    return {iceServers};
  }
  window.GurbaniPeer = {
    start: function (options) {
      let current = null, timer = null, attempts = 0, opened = false, creating = false;
      const setStatus = message => options.onStatus(message);
      function schedule(delay) {
        if (timer) return;
        timer = setTimeout(() => { timer = null; retry(); }, delay);
      }
      function retry() {
        if (navigator.onLine === false) {
          setStatus('No internet — reconnecting automatically');
          schedule(5000); return;
        }
        if (current && !current.destroyed && current.open) return;
        if (current && !current.destroyed && current.disconnected && opened) {
          try { current.reconnect(); setStatus('Reconnecting…'); schedule(12000); return; }
          catch (_) { current.destroy(); }
        }
        if (current && !current.destroyed) current.destroy();
        create();
      }
      async function create() {
        if (creating) return;
        if (typeof window.RTCPeerConnection !== 'function') { setStatus('WebRTC unavailable. Update Android System WebView.'); return; }
        if (typeof Peer === 'undefined') { setStatus('Connection library unavailable — reopen app online'); schedule(10000); return; }
        setStatus('Connecting…'); opened = false; creating = true;
        const config = await Promise.race([iceConfig(), new Promise(resolve => setTimeout(() => resolve(undefined), 2500))]);
        creating = false;
        if (current && !current.destroyed) return;
        let p;
        try {
          p = current = new Peer(options.id(), config ? {debug: 0, config} : {debug: 0});
        } catch (error) {
          setStatus('Pairing could not start: ' + error.message);
          schedule(10000);
          return;
        }
        options.onPeer(p);
        p.on('open', () => {
          if (p !== current) return;
          opened = true; attempts = 0;
          if (timer) { clearTimeout(timer); timer = null; }
          options.onOpen();
        });
        p.on('connection', conn => { if (p === current) options.onConnection(conn); });
        p.on('disconnected', () => {
          if (p !== current) return;
          setStatus('Connection offline — reconnecting automatically'); schedule(1500);
        });
        p.on('close', () => {
          if (p !== current) return;
          setStatus('Connection closed — reconnecting automatically'); schedule(2500);
        });
        p.on('error', e => {
          if (p !== current) return;
          if (e.type === 'unavailable-id') {
            current = null; p.destroy(); options.onCollision(); schedule(7000); return;
          }
          if (e.type === 'peer-unavailable') {
            options.onTargetUnavailable(e); return;
          }
          if (e.type === 'network' || e.type === 'socket-error' || e.type === 'socket-closed' || e.type === 'server-error') {
            current = null; p.destroy();
            setStatus('Connection server unavailable — retrying; check internet');
            schedule(Math.min(30000, 3000 * Math.pow(2, Math.min(attempts++, 3))));
          } else if (e.type === 'browser-incompatible') {
            if (timer) { clearTimeout(timer); timer = null; }
            setStatus('WebRTC unavailable. Update Android System WebView.');
          } else {
            setStatus('Connection error: ' + (e.message || e.type || 'unknown'));
          }
        });
        schedule(15000); // Recover a signalling attempt that never reports success or failure.
      }
      addEventListener('online', () => { if (timer) {clearTimeout(timer); timer = null} retry(); });
      document.addEventListener('visibilitychange', () => { if (!document.hidden && (!current || current.disconnected || current.destroyed)) retry(); });
      create();
      return {retry};
    }
  };
})();

'use strict';

window.createRingBellLan = function (code, role, onConnection, onCall) {
  const bridge = window.BellWifi;
  if (!bridge || typeof RTCPeerConnection !== 'function') return null;
  const uuid = () => {
    if (typeof crypto.randomUUID === 'function') return crypto.randomUUID();
    const bytes = crypto.getRandomValues(new Uint8Array(18));
    return Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
  };
  const channels = new Map();
  const searches = new Map();

  function events(target) {
    const handlers = new Map();
    target.on = (name, handler) => {
      const list = handlers.get(name) || [];
      list.push(handler);
      handlers.set(name, list);
    };
    target.emit = (name, value) => {
      for (const handler of handlers.get(name) || []) handler(value);
    };
    return target;
  }

  function createChannel(id, remoteCode) {
    const media = new Map();
    const c = events({
      peer: 'lan:' + remoteCode,
      lan: true,
      open: false,
      send(data) {
        if (c.open) bridge.send(id, JSON.stringify(data));
      },
      close() {
        bridge.close(id);
        end();
      },
      call(stream) {
        if (!c.open) return null;
        const mid = uuid();
        const call = createMedia(mid);
        for (const track of stream.getTracks()) call.pc.addTrack(track, stream);
        call.offer().catch(() => call.emit('error'));
        return call;
      }
    });
    function end() {
      if (!channels.delete(id)) return;
      c.open = false;
      for (const call of media.values()) call.close();
      c.emit('close');
    }
    function createMedia(mid, offer) {
      const pc = new RTCPeerConnection({iceServers: []});
      const call = events({
        pc,
        peer: c.peer,
        close() {
          media.delete(mid);
          pc.close();
        },
        async offer() {
          await pc.setLocalDescription(await pc.createOffer());
          await gatheringComplete(pc);
          c.send({lanMedia: 'offer', mid, description: pc.localDescription});
        },
        answer() {
          (async () => {
            await pc.setRemoteDescription(offer);
            await pc.setLocalDescription(await pc.createAnswer());
            await gatheringComplete(pc);
            c.send({lanMedia: 'answer', mid, description: pc.localDescription});
          })().catch(() => call.emit('error'));
        }
      });
      pc.ontrack = e => {
        if (e.streams[0]) call.emit('stream', e.streams[0]);
      };
      pc.onconnectionstatechange = () => {
        if (pc.connectionState === 'failed') call.emit('error');
      };
      media.set(mid, call);
      return call;
    }
    c.frame = data => {
      if (data.lanMedia === 'offer' && data.description?.type === 'offer'
          && /^[a-f0-9-]{36}$/.test(data.mid) && !media.has(data.mid)) {
        onCall(createMedia(data.mid, data.description), c);
      } else if (data.lanMedia === 'answer' && data.description?.type === 'answer') {
        const call = media.get(data.mid);
        if (call && call.pc.signalingState === 'have-local-offer') {
          call.pc.setRemoteDescription(data.description).catch(() => call.emit('error'));
        }
      } else if (!data.lanMedia) {
        c.emit('data', data);
      }
    };
    channels.set(id, c);
    return c;
  }

  function gatheringComplete(pc) {
    if (pc.iceGatheringState === 'complete') return Promise.resolve();
    return new Promise(resolve => {
      const timer = setTimeout(done, 2500);
      function done() {
        clearTimeout(timer);
        pc.removeEventListener('icegatheringstatechange', check);
        resolve();
      }
      function check() {
        if (pc.iceGatheringState === 'complete') done();
      }
      pc.addEventListener('icegatheringstatechange', check);
    });
  }

  window.gpBellLanEvent = (event, id, payload) => {
    if (event === 'found') {
      searches.get(id)?.found(JSON.parse(payload));
      return;
    }
    if (event === 'search-done') {
      searches.get(id)?.done();
      searches.delete(id);
      return;
    }
    if (event === 'incoming') {
      const c = createChannel(id, payload);
      onConnection(c);
      c.open = true;
      c.emit('open');
      return;
    }
    const c = channels.get(id);
    if (!c) {
      if (event === 'open') bridge.close(id);
      return;
    }
    if (event === 'open') {
      c.open = true;
      c.emit('open');
    } else if (event === 'closed') {
      c.close();
    } else if (event === 'frame') {
      try {
        const data = JSON.parse(payload);
        if (data && typeof data === 'object') c.frame(data);
      } catch (_) {}
    }
  };

  bridge.start(code, role);
  return {
    search(targetCode, found, done) {
      const id = uuid();
      searches.set(id, {found, done});
      bridge.search(id, targetCode);
    },
    connect(target) {
      const id = uuid();
      const c = createChannel(id, target.code);
      bridge.dial(id, target.target, target.code);
      return c;
    }
  };
};

// kyc-tunnel: WebSocket reverse tunnel Worker for the KYC platform.
//
// Why this exists: the KYC platform runs on the owner's VM, which has
// no inbound connectivity and cannot reach the Cloudflare Tunnel edge
// directly (the sandbox gateway intercepts direct TCP/7844). Outbound
// WebSocket through the egress proxy works, so the VM's tunnel client holds
// one WSS connection to this Worker and the Worker proxies public HTTP
// requests down it to http://127.0.0.1:8787 on the VM.
//
// Wire protocol (WS text frames, JSON) — same shape as the proven
// office-tunnel in Agentic-Community:
//   worker -> client: {"id":N,"method":"GET","path":"/...","headers":{...},"body":b64|null}
//   client -> worker: {"id":N,"status":200,"headers":{...},"body":b64|null}
//
// Streaming extension (v2, for SSE / open-ended responses):
//   The Worker adds "stream":1 to every request frame to advertise support.
//   A v2 client answers open-ended responses (e.g. text/event-stream) with:
//     {"id":N,"type":"stream-start","status":200,"headers":{...}}
//     {"id":N,"type":"stream-chunk","body":b64}        (<=16 KiB raw each)
//     {"id":N,"type":"stream-end"}                     (or ..."error":"...")
//   and this Worker emits the public response as a ReadableStream fed by
//   those frames. If the public reader goes away, the Worker sends
//   {"id":N,"type":"stream-cancel"} so the client stops reading the origin.
//   A v1 client ignores the flag and replies with one complete frame, which
//   this Worker still accepts exactly as before — no regression either way.
//
// The tunnel endpoint is /tunnel?secret=<TUNNEL_SECRET>. Everything else is
// public traffic for the KYC platform origin.

const HEAD_TIMEOUT_MS = 60000;   // wait for a complete reply OR a stream-start
const STREAM_IDLE_MS = 90000;    // origin heartbeats every 25s; 90s = dead air

function b64encode(bytes) {
  let bin = "";
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
  }
  return btoa(bin);
}

function b64decode(b64) {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

function replyHeaders(reply) {
  const rheaders = new Headers();
  for (const [k, v] of Object.entries(reply.headers || {})) {
    if (k.toLowerCase() === "content-length") continue;
    try { rheaders.set(k, v); } catch (e) { /* skip bad header */ }
  }
  return rheaders;
}

export class TunnelHub {
  constructor(state, env) {
    this.state = state;
    this.env = env;
    this.ws = null;
    this.nextId = 1;
    // id -> {kind:"head", resolve, timer}
    //     | {kind:"stream", controller, idleTimer}
    this.pending = new Map();
  }

  liveWs() {
    // With hibernatable WebSockets the Durable Object can be reloaded
    // between the tunnel connect and a later request, losing this.ws.
    // The accepted socket survives in state — always look it up there.
    if (this.ws) {
      try { if (this.ws.readyState === 1) return this.ws; } catch (e) { /* stale */ }
      this.ws = null;
    }
    const sockets = this.state.getWebSockets();
    if (sockets && sockets.length) {
      this.ws = sockets[sockets.length - 1];
      return this.ws;
    }
    return null;
  }

  _sendCancel(id) {
    const ws = this.liveWs();
    if (!ws) return;
    try { ws.send(JSON.stringify({ id, type: "stream-cancel" })); } catch (e) { /* gone */ }
  }

  _armStreamIdle(id, entry) {
    if (entry.idleTimer) clearTimeout(entry.idleTimer);
    entry.idleTimer = setTimeout(() => {
      if (this.pending.get(id) !== entry) return;
      this.pending.delete(id);
      try { entry.controller.error(new Error("KYC origin stream idle")); } catch (e) { /* closed */ }
      this._sendCancel(id);
    }, STREAM_IDLE_MS);
  }

  _dropStream(id, entry, err) {
    if (entry.idleTimer) clearTimeout(entry.idleTimer);
    if (this.pending.get(id) === entry) this.pending.delete(id);
    if (err) {
      try { entry.controller.error(err); } catch (e) { /* closed */ }
    } else {
      try { entry.controller.close(); } catch (e) { /* closed */ }
    }
  }

  async fetch(request) {
    const url = new URL(request.url);

    if (url.pathname === "/tunnel") {
      if (request.headers.get("Upgrade") !== "websocket") {
        return new Response("expected websocket", { status: 426 });
      }
      if (!this.env.TUNNEL_SECRET || url.searchParams.get("secret") !== this.env.TUNNEL_SECRET) {
        return new Response("forbidden", { status: 403 });
      }
      const pair = new WebSocketPair();
      const [client, server] = Object.values(pair);
      this.state.acceptWebSocket(server);
      this.ws = server;
      // Re-send in-flight requests on the fresh socket. The tunnel
      // client's socket drops abnormally every few minutes in this
      // environment (no close frame — the path out of the VM recycles
      // long-lived connections) and it reconnects within seconds.
      // Before this, webSocketClose failed every in-flight request on
      // the spot (the owner's live runs died as HTTP 504s); now a head
      // request survives the drop: its frame is re-sent here and its
      // original 30s timer keeps running, so only a reconnect that
      // never comes still ends in a 504. Re-sending is safe for this
      // origin: uploads replace the step's capture and reads are
      // reads, so a request the client had already processed simply
      // processes again with the same result.
      for (const entry of this.pending.values()) {
        if (entry.kind === "head" && entry.frame && !entry.resent) {
          entry.resent = true;   // at most one re-send: a frame the
          // client cannot accept must never become a retry storm.
          try { server.send(entry.frame); } catch (e) { /* timer decides */ }
        }
      }
      return new Response(null, { status: 101, webSocket: client });
    }

    // Public request -> forward down the tunnel.
    let ws = this.liveWs();
    if (!ws) {
      // The tunnel client reconnects within seconds of a drop; a
      // request landing in that window used to die instantly as a
      // 503. Give the reconnect a short grace period first.
      const deadline = Date.now() + 6000;
      while (!ws && Date.now() < deadline) {
        await new Promise(r => setTimeout(r, 250));
        ws = this.liveWs();
      }
    }
    if (!ws) {
      return new Response("KYC tunnel is offline", { status: 503 });
    }
    const id = this.nextId++;
    const headers = {};
    for (const [k, v] of request.headers.entries()) headers[k] = v;
    // Location evidence for the origin's location check: stamp the
    // real client IP + IP country in the canonical headers the origin
    // server reads (X-Client-IP / X-IP-Country). CF-Connecting-IP is
    // set by the Cloudflare edge on every request; request.cf.country
    // is the edge's geo lookup for that IP. The tunnel protocol
    // forwards a headers map, so both ride down it unchanged (the
    // tunnel client passes request headers through verbatim).
    const clientIp = request.headers.get("CF-Connecting-IP");
    if (clientIp) headers["x-client-ip"] = clientIp;
    const ipCountry = (request.cf && request.cf.country) || request.headers.get("CF-IPCountry");
    if (ipCountry) headers["x-ip-country"] = ipCountry;
    let body = null;
    if (request.method !== "GET" && request.method !== "HEAD") {
      const buf = new Uint8Array(await request.arrayBuffer());
      // The tunnel protocol caps frames at 4 MiB and the request body
      // rides base64-encoded (x1.37) inside one: a body over ~2.8MB
      // can never cross. Refuse it HERE with a fast, honest 413
      // instead of framing a request whose arrival kills the tunnel
      // client's socket (the 2026-10-26 selfie-burst incident: five
      // native-resolution frames, one ~9MB frame, a 30s flap storm).
      if (buf.length > 2800000) {
        return new Response("request body too large for the tunnel", { status: 413 });
      }
      if (buf.length) body = b64encode(buf);
    }
    const path = url.pathname + url.search;
    // "stream":1 advertises v2 streaming support; v1 clients ignore it.
    const frame = JSON.stringify({ id, method: request.method, path, headers, body, stream: 1 });

    // First frame back decides: a complete v1 reply, or a v2 stream-start.
    const head = await new Promise((resolve) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        resolve(null);
      }, HEAD_TIMEOUT_MS);
      this.pending.set(id, { kind: "head", resolve, timer, frame });
      try {
        ws.send(frame);
      } catch (e) {
        clearTimeout(timer);
        this.pending.delete(id);
        resolve(null);
      }
    });

    if (!head) {
      return new Response("KYC origin timed out", { status: 504 });
    }

    if (head.type !== "stream-start") {
      // Legacy complete reply — unchanged v1 behavior.
      const rbody = head.body ? b64decode(head.body) : null;
      return new Response(rbody, { status: head.status || 502, headers: replyHeaders(head) });
    }

    // Streaming reply: headers now, body fed by stream-chunk frames.
    const hub = this;
    const entry = { kind: "stream", controller: null, idleTimer: null };
    const stream = new ReadableStream({
      start(controller) {
        entry.controller = controller;
        hub.pending.set(id, entry);
        hub._armStreamIdle(id, entry);
      },
      cancel() {
        // Public reader disconnected: stop the origin read.
        if (entry.idleTimer) clearTimeout(entry.idleTimer);
        if (hub.pending.get(id) === entry) hub.pending.delete(id);
        hub._sendCancel(id);
      },
    });
    return new Response(stream, { status: head.status || 200, headers: replyHeaders(head) });
  }

  async webSocketMessage(ws, message) {
    let msg;
    try { msg = JSON.parse(message); } catch (e) { return; }
    const entry = this.pending.get(msg.id);
    if (!entry) return;

    if (entry.kind === "head") {
      if (msg.type === "stream-chunk" || msg.type === "stream-end") {
        // Chunk before stream-start is a protocol error; fail the request.
        this.pending.delete(msg.id);
        clearTimeout(entry.timer);
        entry.resolve(null);
        return;
      }
      this.pending.delete(msg.id);
      clearTimeout(entry.timer);
      entry.resolve(msg);
      return;
    }

    // kind === "stream"
    if (msg.type === "stream-chunk") {
      this._armStreamIdle(msg.id, entry);
      if (msg.body) {
        try {
          entry.controller.enqueue(b64decode(msg.body));
        } catch (e) {
          // Reader gone but cancel() has not run yet: tell the client.
          this._dropStream(msg.id, entry, null);
          this._sendCancel(msg.id);
        }
      }
    } else if (msg.type === "stream-end") {
      if (msg.error) {
        this._dropStream(msg.id, entry, new Error("KYC origin stream error"));
      } else {
        this._dropStream(msg.id, entry, null);
      }
    }
  }

  async webSocketClose(ws, code, reason) {
    if (this.ws === ws) this.ws = null;
    for (const [id, entry] of Array.from(this.pending.entries())) {
      if (entry.kind === "head") {
        // Do NOT fail head requests on a socket drop: the client
        // reconnects within seconds and the /tunnel handler re-sends
        // their frames (see above). The 30s head timer is the only
        // deadline. Streams cannot survive a socket change and are
        // dropped as before.
        continue;
      }
      this._dropStream(id, entry, new Error("KYC tunnel closed"));
      this.pending.delete(id);
    }
  }

  async webSocketError(ws, error) {
    if (this.ws === ws) this.ws = null;
  }
}

export default {
  async fetch(request, env) {
    const id = env.TUNNEL_HUB.idFromName("kyc");
    const hub = env.TUNNEL_HUB.get(id);
    return hub.fetch(request);
  },
};

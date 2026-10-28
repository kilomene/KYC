#!/usr/bin/env python3
"""kyc-tunnel-client: sandbox side of the office-tunnel reverse tunnel.

Holds one outbound WebSocket to the office-tunnel Cloudflare Worker and
proxies HTTP requests arriving over it to the local KYC server
(127.0.0.1:8790), returning the responses.

Why this exists instead of cloudflared: this sandbox's seccomp blocks
sendto/sendmsg on unconnected UDP sockets (EPERM), and the installed
cloudflared (2026.9.3) is QUIC-only, so it can never reach the Cloudflare
edge from here. Outbound WebSocket through the egress proxy works fine
(the ACP relay daemon proves it), so the tunnel rides a WebSocket.

Wire protocol (WS text frames, JSON):
  worker -> client: {"id":N,"method":"GET","path":"/...","headers":{...},"body":b64|null}
  client -> worker: {"id":N,"status":200,"headers":{...},"body":b64|null}

Streaming extension (v2, used for SSE / open-ended responses):
  The Worker advertises support by adding "stream":1 to the request frame.
  Only then does the client stream; without the flag every response is
  buffered and returned exactly as in v1 (so this client is safe to run
  against a v1 Worker — v1 behavior is unchanged, no regressions).
    client -> worker: {"id":N,"type":"stream-start","status":200,"headers":{...}}
    client -> worker: {"id":N,"type":"stream-chunk","body":b64}   (<=16 KiB raw)
    client -> worker: {"id":N,"type":"stream-end"}                 (clean EOF)
    client -> worker: {"id":N,"type":"stream-end","error":"..."}   (origin died)
    worker -> client: {"id":N,"type":"stream-cancel"}               (reader gone)

Supervised by systemd (kyc-tunnel-client.service, Restart=always);
the client also reconnects on its own with backoff when the socket drops.
"""
import base64
import http.client
import json
import os
import socket
import ssl
import sys
import threading
import time
import traceback
import urllib.parse

sys.path.insert(0, os.path.expanduser("~/.acp/lib"))
from acp_connector import ws_transport as wst  # noqa: E402

SECRET_FILE = os.path.expanduser("~/.cloudflared/kyc-tunnel-secret")
URL_FILE = os.path.expanduser("~/.cloudflared/kyc-tunnel-url")
DEFAULT_URL = "wss://kyc-tunnel.ayiijumo.workers.dev/tunnel"
ORIGIN_HOST = "127.0.0.1"
ORIGIN_PORT = 8790
PING_EVERY = 25
ORIGIN_TIMEOUT = 120
LOG = os.path.expanduser("~/workspace/KYC/logs/tunnel-client.log")

HOP_BY_HOP = {"connection", "transfer-encoding", "keep-alive", "upgrade",
              "proxy-connection", "proxy-authenticate", "te", "trailer"}


def log(msg):
    line = "%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        with open(LOG, "a") as f:
            f.write(line)
    except OSError:
        pass


def load_proxy_env():
    for k in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        if os.environ.get(k):
            return
    p = os.path.expanduser("~/.vm-agent/proxy.env")
    if os.path.isfile(p):
        with open(p) as f:
            for line in f:
                line = line.strip()
                if line.startswith("export "):
                    line = line[len("export "):]
                if "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("'\""))


def send_text(conn, obj):
    data = json.dumps(obj).encode("utf-8")
    conn._send_frame_bytes(wst._encode_frame(0x1, data))


STREAM_CHUNK_BYTES = 16384  # raw bytes per stream-chunk frame (~22 KiB on wire)
_stream_cancels = {}
_stream_cancels_lock = threading.Lock()


def _register_cancel(rid):
    ev = threading.Event()
    with _stream_cancels_lock:
        _stream_cancels[rid] = ev
    return ev


def _unregister_cancel(rid):
    with _stream_cancels_lock:
        _stream_cancels.pop(rid, None)


def _signal_cancel(rid):
    with _stream_cancels_lock:
        ev = _stream_cancels.get(rid)
    if ev is not None:
        ev.set()


def _stream_response(conn, rid, c, r, rheaders):
    """Forward an open-ended origin response incrementally (protocol v2)."""
    cancel = _register_cancel(rid)
    error = None
    try:
        # Poll the origin socket every 5s: a quiet stream must stay open
        # (the origin heartbeats every 25s), but a stream-cancel from the
        # Worker must land within seconds, not at the next heartbeat.
        try:
            if c.sock is not None:
                c.sock.settimeout(5)
        except Exception:
            pass
        send_text(conn, {"id": rid, "type": "stream-start",
                         "status": r.status, "headers": rheaders})
        read = getattr(r, "read1", None) or r.read
        while not cancel.is_set():
            try:
                chunk = read(STREAM_CHUNK_BYTES)
            except (socket.timeout, TimeoutError):
                continue  # idle poll tick; loop re-checks the cancel flag
            if not chunk:
                break
            send_text(conn, {"id": rid, "type": "stream-chunk",
                             "body": base64.b64encode(chunk).decode()})
    except Exception as e:
        error = repr(e)
        log("stream failed id=%s: %s" % (rid, error))
    finally:
        _unregister_cancel(rid)
    end = {"id": rid, "type": "stream-end"}
    if error is not None:
        end["error"] = error
    elif cancel.is_set():
        end["cancelled"] = True
    try:
        send_text(conn, end)
    except Exception:
        pass  # socket is gone; nothing else to do


def handle_request(conn, msg):
    rid = msg.get("id")
    try:
        method = msg.get("method", "GET")
        path = msg.get("path", "/") or "/"
        headers = {k: v for k, v in (msg.get("headers") or {}).items()
                   if k.lower() not in HOP_BY_HOP and k.lower() != "host"}
        body = base64.b64decode(msg["body"]) if msg.get("body") else None
        c = http.client.HTTPConnection(ORIGIN_HOST, ORIGIN_PORT,
                                       timeout=ORIGIN_TIMEOUT)
        try:
            c.request(method, path, body=body, headers=headers)
            r = c.getresponse()
            rheaders = {}
            for k, v in r.getheaders():
                if k.lower() in HOP_BY_HOP:
                    continue
                # last wins on duplicates; dashboard traffic is simple
                rheaders[k] = v
            # Stream only when the Worker advertised v2 support AND the
            # response is open-ended (SSE or unknown-length chunked body).
            ctype = (r.getheader("Content-Type") or "").lower()
            is_stream = (
                bool(msg.get("stream"))
                and method != "HEAD"
                and r.status not in (204, 304)
                and ("text/event-stream" in ctype or r.length is None)
            )
            if is_stream:
                _stream_response(conn, rid, c, r, rheaders)
                return
            rbody = r.read()
            reply = {"id": rid, "status": r.status, "headers": rheaders,
                     "body": base64.b64encode(rbody).decode() if rbody else None}
        finally:
            c.close()
    except Exception as e:
        log("origin fetch failed id=%s: %r" % (rid, e))
        reply = {"id": rid, "status": 502, "headers": {},
                 "body": None}
    try:
        send_text(conn, reply)
    except Exception as e:
        log("reply send failed id=%s: %r" % (rid, e))


def connect_url(url, timeout=15):
    """Connect to a ws:// or wss:// URL and complete the WS handshake."""
    if url.startswith("ws://") and not url.startswith("wss://"):
        # Plain-WS hook for local testing (no TLS). Not used in production.
        rest = url[len("ws://"):]
        hostpart, _, path = rest.partition("/")
        path = "/" + path
        host, _, port_s = hostpart.partition(":")
        port = int(port_s) if port_s else 80
        sock = socket.create_connection((host, port), timeout=timeout)
        sock.settimeout(timeout)
        wst._ws_handshake(sock, host, port, path, timeout=timeout)
        sock.settimeout(None)
        return wst.WsConn(sock)
    return wst.wss_connect(url, timeout=timeout)


def serve(conn):
    """Read frames until the socket dies. Text frames are tunnel requests."""
    stop = threading.Event()

    def pinger():
        while not stop.wait(PING_EVERY):
            try:
                conn.send_ping(b"kyc")
            except Exception:
                break

    t = threading.Thread(target=pinger, daemon=True)
    t.start()
    try:
        while not conn.closed:
            try:
                opcode, payload = conn._read_frame()
            except Exception:
                break
            if opcode == 0x8:  # close
                conn._note_close_frame(payload)
                break
            elif opcode == 0x9:  # ping -> pong
                try:
                    conn._send_pong(payload)
                except Exception:
                    break
            elif opcode == 0xA:  # pong
                continue
            elif opcode == 0x1:  # text: tunnel request or stream control
                try:
                    msg = json.loads(payload.decode("utf-8"))
                except Exception:
                    continue
                if msg.get("type") == "stream-cancel":
                    _signal_cancel(msg.get("id"))
                    continue
                th = threading.Thread(target=handle_request,
                                      args=(conn, msg), daemon=True)
                th.start()
            else:
                continue
    finally:
        stop.set()
        conn.close()


def main():
    load_proxy_env()
    try:
        with open(SECRET_FILE) as f:
            secret = f.read().strip()
    except OSError:
        log("no secret at %s; refusing to start" % SECRET_FILE)
        return 1
    if os.path.isfile(URL_FILE):
        with open(URL_FILE) as f:
            base = f.read().strip() or DEFAULT_URL
    else:
        base = DEFAULT_URL
    base = os.environ.get("PAYMENTS_TUNNEL_URL", base)
    url = base + ("&" if "?" in base else "?") + "secret=" + urllib.parse.quote(secret, safe="")
    log("starting; worker %s" % base)
    backoff = 2
    while True:
        try:
            conn = connect_url(url, timeout=15)
        except Exception as e:
            log("connect failed: %r; retry in %ds" % (e, backoff))
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue
        log("tunnel WebSocket connected")
        backoff = 2
        try:
            serve(conn)
        except Exception:
            log("serve crashed:\n%s" % traceback.format_exc())
        log("socket dropped (close=%s %s); reconnecting" %
            (conn.close_code, conn.close_reason))
        time.sleep(backoff)
        backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    sys.exit(main())

/*
 * Cedar Support Copilot chat widget.
 *
 * <script src="https://YOUR-HOST/static/widget/cedar-widget.js"
 *         data-widget-key="wk_..."
 *         data-api="https://YOUR-HOST"
 *         data-title="Cedar Assistant"
 *         data-accent="#0F766E" defer></script>
 */
(function () {
  "use strict";
  var script = document.currentScript;
  if (!script) return;
  var KEY = script.getAttribute("data-widget-key");
  var API = (script.getAttribute("data-api") || new URL(script.src).origin).replace(/\/$/, "");
  var TITLE = script.getAttribute("data-title") || "Support";
  var ACCENT = script.getAttribute("data-accent") || "#0F766E";
  var STORE = "cedar-widget:" + KEY;
  var POLL_MS = 5000;
  if (!KEY) { console.warn("[cedar-widget] data-widget-key is missing"); return; }

  var state = { token: load(), status: "open", sending: false, seen: 0, pollTimer: null };

  function load() { try { return localStorage.getItem(STORE) || ""; } catch (e) { return ""; } }
  function save(t) { try { localStorage.setItem(STORE, t); } catch (e) {} }

  // ---------- DOM (shadow root keeps host page styles out) ----------
  var host = document.createElement("div");
  host.id = "cedar-widget";
  document.body.appendChild(host);
  var root = host.attachShadow({ mode: "open" });
  root.innerHTML =
    "<style>" +
    ":host{all:initial}" +
    "*{box-sizing:border-box;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif}" +
    ".launcher{position:fixed;right:20px;bottom:20px;width:56px;height:56px;border-radius:50%;border:none;background:" + ACCENT + ";color:#fff;cursor:pointer;display:flex;align-items:center;justify-content:center;z-index:2147483000}" +
    ".launcher:focus-visible{outline:3px solid #16181D;outline-offset:3px}" +
    ".panel{position:fixed;right:20px;bottom:88px;width:360px;max-width:calc(100vw - 24px);height:540px;max-height:calc(100vh - 110px);background:#fff;border:1px solid #E5E5E1;border-radius:16px;display:none;flex-direction:column;overflow:hidden;z-index:2147483000;color:#16181D}" +
    ".panel.open{display:flex}" +
    ".head{background:" + ACCENT + ";color:#fff;padding:14px 16px;display:flex;justify-content:space-between;align-items:center}" +
    ".head h2{margin:0;font-size:15px;font-weight:600}.head p{margin:2px 0 0;font-size:12px;opacity:.85}" +
    ".close{background:none;border:none;color:#fff;font-size:22px;line-height:1;cursor:pointer;width:32px;height:32px}" +
    ".actions{display:flex;align-items:center;gap:4px}" +
    ".new{background:rgba(255,255,255,.18);border:none;color:#fff;font-size:12px;border-radius:999px;padding:6px 10px;cursor:pointer}" +
    ".new:hover{background:rgba(255,255,255,.28)}" +
    ".log{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px;background:#FBFBFA}" +
    ".msg{max-width:85%;padding:9px 12px;border-radius:12px;font-size:14px;line-height:1.45;white-space:pre-wrap;word-wrap:break-word}" +
    ".customer{align-self:flex-end;background:#16181D;color:#fff;border-bottom-right-radius:4px}" +
    ".ai{align-self:flex-start;background:#fff;border:1px solid #E5E5E1;border-bottom-left-radius:4px}" +
    ".agent{align-self:flex-start;background:#FEF3C7;border:1px solid #FDE68A;border-bottom-left-radius:4px}" +
    ".who{display:block;font-size:11px;font-weight:600;color:#7A4B00;margin-bottom:3px}" +
    ".chips{align-self:flex-start;display:flex;flex-wrap:wrap;gap:6px;margin-top:-4px}" +
    ".chip{font-size:11px;background:#E6F4F1;color:#115E59;border-radius:999px;padding:3px 9px}" +
    ".notice{align-self:center;font-size:12px;color:#5B616E;text-align:center}" +
    ".typing{align-self:flex-start;font-size:13px;color:#5B616E}" +
    "form{display:flex;gap:8px;padding:10px;border-top:1px solid #E5E5E1;background:#fff}" +
    "input{flex:1;min-width:0;border:1px solid #D4D4CE;border-radius:10px;padding:11px 12px;font-size:14px}" +
    "input:focus{outline:2px solid " + ACCENT + ";outline-offset:-1px}" +
    "button.send{border:none;border-radius:10px;background:" + ACCENT + ";color:#fff;width:44px;cursor:pointer}" +
    "button.send:disabled{opacity:.5;cursor:default}" +
    ".sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}" +
    "</style>" +
    '<button class="launcher" aria-label="Open support chat" aria-expanded="false">' +
    '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/></svg></button>' +
    '<section class="panel" role="dialog" aria-label="' + esc(TITLE) + ' chat">' +
    '<div class="head"><div><h2>' + esc(TITLE) + "</h2><p>Answers from our help docs · a person can step in</p></div>" +
    '<div class="actions"><button class="new" type="button">New chat</button>' +
    '<button class="close" aria-label="Close chat">×</button></div></div>' +
    '<div class="log" aria-live="polite"></div>' +
    '<form><label class="sr" for="cw-input">Your question</label>' +
    '<input id="cw-input" autocomplete="off" maxlength="2000" placeholder="Ask a question…">' +
    '<button class="send" type="submit" aria-label="Send">➤</button></form></section>';

  var launcher = root.querySelector(".launcher");
  var panel = root.querySelector(".panel");
  var log = root.querySelector(".log");
  var form = root.querySelector("form");
  var input = root.querySelector("input");
  var sendBtn = root.querySelector(".send");

  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function add(sender, content, citations) {
    var el = document.createElement("div");
    el.className = "msg " + sender;
    if (sender === "agent") {
      var who = document.createElement("span");
      who.className = "who";
      who.textContent = "Support team";
      el.appendChild(who);
    }
    el.appendChild(document.createTextNode(content));
    log.appendChild(el);
    if (citations && citations.length) {
      var chips = document.createElement("div");
      chips.className = "chips";
      citations.forEach(function (c) {
        var chip = document.createElement("span");
        chip.className = "chip";
        chip.textContent = "Source: " + c.document_title + (c.section ? " · " + c.section : "");
        chips.appendChild(chip);
      });
      log.appendChild(chips);
    }
    log.scrollTop = log.scrollHeight;
  }

  function notice(text) {
    var el = document.createElement("div");
    el.className = "notice";
    el.textContent = text;
    log.appendChild(el);
    log.scrollTop = log.scrollHeight;
  }

  function setStatus(status) {
    state.status = status;
    if (status === "escalated") startPolling(); else stopPolling();
  }

  // ---------- API ----------
  function send(text) {
    state.sending = true;
    sendBtn.disabled = true;
    var typing = document.createElement("div");
    typing.className = "typing";
    typing.textContent = "…";
    log.appendChild(typing);
    var body = { widget_key: KEY, message: text };
    if (state.token) body.conversation_token = state.token;
    return fetch(API + "/api/chat/", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (r) {
        if (r.status === 404 && state.token) { state.token = ""; save(""); return send(text); }
        if (r.status === 429) throw new Error("You're sending messages quickly. Please wait a moment.");
        if (!r.ok) throw new Error("Something went wrong. Please try again.");
        return r.json();
      })
      .then(function (data) {
        if (!data) return;
        state.token = data.conversation_token;
        save(state.token);
        add("ai", data.reply.content, data.reply.citations);
        state.seen += 2;
        setStatus(data.status);
      })
      .catch(function (err) { notice(err.message); })
      .then(function () {
        typing.remove();
        state.sending = false;
        sendBtn.disabled = false;
        input.focus();
      });
  }

  function restore() {
    if (!state.token) {
      add("ai", "Hi! Ask me about fees, limits or transfers. If I'm not sure, I'll pass you to our team.");
      state.seen = 0;
      return;
    }
    fetchHistory(true);
  }

  function fetchHistory(render) {
    return fetch(API + "/api/chat/" + encodeURIComponent(state.token) + "/?widget_key=" + encodeURIComponent(KEY))
      .then(function (r) {
        if (r.status === 404) { state.token = ""; save(""); if (render) restore(); return null; }
        return r.ok ? r.json() : null;
      })
      .then(function (data) {
        if (!data) return;
        var msgs = data.messages;
        var start = render ? 0 : state.seen;
        for (var i = start; i < msgs.length; i++) add(msgs[i].sender, msgs[i].content, msgs[i].citations);
        state.seen = msgs.length;
        setStatus(data.status);
      })
      .catch(function () {});
  }

  function startPolling() {
    if (state.pollTimer) return;
    state.pollTimer = setInterval(function () {
      if (panel.classList.contains("open") && !state.sending) fetchHistory(false);
    }, POLL_MS);
  }
  function stopPolling() { clearInterval(state.pollTimer); state.pollTimer = null; }

  // ---------- events ----------
  var restored = false;
  function toggle(open) {
    panel.classList.toggle("open", open);
    launcher.setAttribute("aria-expanded", String(open));
    if (open) {
      if (!restored) { restored = true; restore(); }
      input.focus();
    } else {
      launcher.focus();
    }
  }
  launcher.addEventListener("click", function () { toggle(!panel.classList.contains("open")); });
  root.querySelector(".close").addEventListener("click", function () { toggle(false); });
  root.querySelector(".new").addEventListener("click", function () {
    state.token = ""; save(""); state.seen = 0; stopPolling();
    log.innerHTML = "";
    restore();
    input.focus();
  });
  panel.addEventListener("keydown", function (e) { if (e.key === "Escape") toggle(false); });
  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var text = input.value.trim();
    if (!text || state.sending) return;
    input.value = "";
    add("customer", text);
    send(text);
  });
})();

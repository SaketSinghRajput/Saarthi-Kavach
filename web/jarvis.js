/* Saarthi Kavach "Jarvis" visual layer: voice orb, entity lock-on, agent graph, risk dial, count-up.
   Purely visual: it only reads events handed over by dashboard.js (window.SK) and never touches the event loop,
   audio start time, or any network call. One requestAnimationFrame loop, no full-screen filters.
   SECURITY (C5): text is set via textContent only; SVG is built with createElementNS. No HTML-string injection.
   ?theme=classic disables everything here and restores the original look. */
(function () {
  'use strict';
  var q = new URLSearchParams(location.search);
  if (q.get('theme') === 'classic') { document.body.classList.remove('jv'); return; }

  var RM = !!(window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches);
  var SK = window.SK = { replay: false };
  var $ = function (id) { return document.getElementById(id); };
  var NS = 'http://www.w3.org/2000/svg';
  function sv(tag, attrs) { var e = document.createElementNS(NS, tag); for (var k in attrs) e.setAttribute(k, attrs[k]); return e; }
  function clamp(v, a, b) { return v < a ? a : v > b ? b : v; }
  function mmss(t) { t = Math.max(0, Math.round(t)); var m = Math.floor(t / 60), s = t % 60; return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s; }

  var COL = { cyan: [34, 211, 238], red: [255, 92, 108], green: [52, 211, 153], amber: [251, 191, 36], violet: [182, 156, 255] };
  function rgba(c, a) { return 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + a + ')'; }

  var callActive = false, callEnded = false, draftsReady = false;

  /* ================= 1. voice orb ================= */
  var cv = $('orb'), cx = cv.getContext('2d'), SZ = 132, DPR = Math.min(window.devicePixelRatio || 1, 1.5);
  cv.width = cv.height = Math.round(SZ * DPR); cv.style.width = cv.style.height = SZ + 'px'; cx.scale(DPR, DPR);
  var orb = { who: null, until: 0, lvl: 0, label: '' };
  var actx = null, analyser = null, tbuf = null, audioEl = null;

  function setOrbText(who, sub) {
    if (orb.label === who + sub) return; orb.label = who + sub;
    $('orbWho').textContent = who; $('orbSub').textContent = sub;
  }
  function estMs(text) { return clamp(String(text || '').length * 70, 1200, 9000); }   // ~14 chars/s of speech
  function speak(who, ms) { orb.who = who; orb.until = performance.now() + ms; }
  function envelope(ms) {   // synthetic syllable envelope 0.05..1
    var x = ms / 1000;
    return clamp(0.4 + 0.26 * Math.sin(x * 9.3) + 0.18 * Math.sin(x * 15.7 + 1.3) + 0.16 * Math.sin(x * 4.1 + .4), 0.05, 1);
  }
  // Real audio tap: created inside the Call click (user gesture) so the context is running; pure pass-through node.
  function initAudio() {
    if (actx || !window.AudioContext) return;
    try {
      actx = new AudioContext();
      if (actx.state !== 'running') { actx.resume(); }
    } catch (e) { actx = null; }
  }
  SK.audio = function (el) {
    if (!actx || actx.state !== 'running' || analyser) { audioEl = el; return; }
    try {
      var src = actx.createMediaElementSource(el);
      analyser = actx.createAnalyser(); analyser.fftSize = 512; analyser.smoothingTimeConstant = 0.6;
      tbuf = new Uint8Array(analyser.fftSize);
      src.connect(analyser); analyser.connect(actx.destination);   // pass-through: playback is never delayed or muted
    } catch (e) { analyser = null; }
    audioEl = el;
  };
  var btnCall = $('btnCall'); if (btnCall) btnCall.addEventListener('click', initAudio, true);

  function orbFrame(t) {
    var now = performance.now(), audioOn = audioEl && !audioEl.paused && !audioEl.ended;
    var speaking = now < orb.until || audioOn, target = 0;
    if (speaking) {
      if (audioOn && analyser) {
        analyser.getByteTimeDomainData(tbuf);
        var s = 0; for (var i = 0; i < tbuf.length; i++) { var v = (tbuf[i] - 128) / 128; s += v * v; }
        target = Math.min(1, Math.sqrt(s / tbuf.length) * 3.4);
      } else target = envelope(now);
    }
    orb.lvl += (target - orb.lvl) * (target > orb.lvl ? 0.35 : 0.1);
    var who = speaking ? orb.who : null;
    var base = who === 'scammer' ? COL.red : COL.cyan;
    if (!speaking) {
      if (callEnded) setOrbText(draftsReady ? 'CALL ENDED · drafts ready' : 'CALL ENDED', draftsReady ? 'Awaiting human approval' : 'Reporter working');
      else setOrbText(callActive ? 'LISTENING' : 'IDLE', callActive ? 'Waiting for the next line' : 'Press Call to start');
    }
    else setOrbText(who === 'scammer' ? 'SCAMMER SPEAKING' : who === 'filler' ? 'KAMLA JI (FILLER)' : 'KAMLA JI SPEAKING', who === 'scammer' ? 'Caller voice' : 'Decoy voice');

    var L = orb.lvl, c = SZ / 2, k = SZ / 170, ph = RM ? 0 : t / 600;
    cx.clearRect(0, 0, SZ, SZ);
    // outer dashed ring + tick arc
    cx.lineWidth = 2; cx.strokeStyle = rgba(base, 0.55); cx.setLineDash([3, 9]); cx.lineDashOffset = RM ? 0 : -t / 45;
    cx.beginPath(); cx.arc(c, c, 80 * k, 0, 6.2832); cx.stroke();
    cx.setLineDash([]);
    cx.lineWidth = 3; cx.strokeStyle = rgba(base, 0.7);
    var rot = RM ? 0 : t / 1600;
    for (var a = 0; a < 3; a++) { cx.beginPath(); cx.arc(c, c, 70 * k, rot + a * 2.0944, rot + a * 2.0944 + 0.7); cx.stroke(); }
    // level ring
    cx.lineWidth = 2; cx.strokeStyle = rgba(base, 0.15 + L * 0.6);
    cx.beginPath(); cx.arc(c, c, (52 + L * 18) * k, 0, 6.2832); cx.stroke();
    // blob
    var N = 64, r0 = (36 + (RM ? 0 : 2 * Math.sin(t / 700))) * k, amp = (4 + L * 26) * k;
    cx.beginPath();
    for (var j = 0; j <= N; j++) {
      var th = j / N * 6.2832;
      var nz = (Math.sin(th * 3 + ph) + Math.sin(th * 5 - ph * 1.3) + Math.sin(th * 8 + ph * .7)) / 3;
      var rr = r0 + amp * (0.35 + 0.65 * L) * nz * (RM ? 0.3 : 1);
      var px = c + Math.cos(th) * rr, py = c + Math.sin(th) * rr;
      if (j === 0) cx.moveTo(px, py); else cx.lineTo(px, py);
    }
    cx.closePath();
    var g = cx.createRadialGradient(c, c, 4, c, c, r0 + amp);
    g.addColorStop(0, rgba(base, 0.75)); g.addColorStop(1, rgba(base, 0.12));
    cx.fillStyle = g; cx.fill();
    cx.lineWidth = 2; cx.strokeStyle = rgba(base, 0.95); cx.stroke();
    // core
    cx.fillStyle = rgba([230, 241, 250], 0.55 + L * 0.4);
    cx.beginPath(); cx.arc(c, c, (9 + L * 7) * k, 0, 6.2832); cx.fill();
  }

  /* ================= 2. entity lock-on ================= */
  var pendingLock = {}, verifying = {}, CH = 'ABCDEF0123456789#@%&';
  var tasks = [];
  function chipFor(id) { return document.querySelector('#ents .chip[data-eid="' + String(id).replace(/"/g, '') + '"]'); }
  function addBrackets(chip, animate) {
    if (chip.querySelector('.lk')) return;
    var lk = document.createElement('div'); lk.className = 'lk' + (animate ? ' snap' : '');
    ['tl', 'tr', 'bl', 'br'].forEach(function (p) { var b = document.createElement('i'); b.className = p; lk.appendChild(b); });
    chip.appendChild(lk);
  }
  function scramble(id) {
    var chip = chipFor(id); if (!chip) return;
    var vEl = chip.querySelector('.v'); if (!vEl) return;
    var fin = vEl.textContent, sufAt = fin.indexOf(' (synthetic)'), body = sufAt >= 0 ? fin.slice(0, sufAt) : fin, suf = sufAt >= 0 ? fin.slice(sufAt) : '';
    var t0 = 0, DUR = 400;
    tasks.push(function (t) {
      if (!t0) t0 = t;
      var cur = chipFor(id), v = cur && cur.querySelector('.v');
      if (!v) return false;
      var p = (t - t0) / DUR, out = '';
      if (p >= 1) { v.textContent = fin; delete verifying[id]; if (SK.refresh) SK.refresh(); return false; }
      for (var i = 0; i < body.length; i++) {
        var ch = body.charAt(i);
        out += (i < Math.ceil(body.length * (0.15 + 0.85 * p)) || !/[A-Za-z0-9]/.test(ch)) ? ch : '•';   // resolved prefix + bullet tail: a garbled character is never shown
      }
      v.textContent = out + suf;   // the synthetic suffix is never scrambled away
      return true;
    });
  }
  SK.verifying = function (id) { return !!verifying[id]; };
  SK.afterEntities = function () {
    var chips = document.querySelectorAll('#ents .chip.confirmed[data-eid]');
    for (var i = 0; i < chips.length; i++) {
      var id = chips[i].getAttribute('data-eid'), fresh = !!pendingLock[id];
      addBrackets(chips[i], fresh && !RM);
      if (fresh) { delete pendingLock[id]; if (!RM) scramble(id); }
    }
  };

  /* ================= 3. agent graph ================= */
  var NODES = {
    kamla: { n: 'Kamla', x: 68, y: 14, c: COL.green }, detector: { n: 'Detector', x: 200, y: 14, c: COL.red },
    verifier: { n: 'Verifier', x: 458, y: 14, c: COL.green }, saarthi: { n: 'Saarthi', x: 68, y: 49, c: [255, 255, 255] },
    intel: { n: 'Intel', x: 332, y: 49, c: COL.cyan }, skill: { n: 'Skill Scout', x: 200, y: 84, c: COL.violet },
    reporter: { n: 'Reporter', x: 458, y: 84, c: COL.amber }
  };
  var EDGES = [['saarthi', 'kamla'], ['saarthi', 'detector'], ['detector', 'intel'], ['intel', 'verifier'], ['verifier', 'reporter'], ['reporter', 'saarthi'], ['skill', 'intel']];
  var gsvg = $('agraph'), edgeEl = {}, litUntil = {}, litState = {}, pulses = [], NW = 112, NH = 26;
  function key(n) {
    n = String(n == null ? '' : n).toLowerCase().replace(/[_-]/g, ' ');
    return n === 'skill scout' || n === 'scout' || n === 'finch' ? 'skill' : NODES[n] ? n : null;
  }
  EDGES.forEach(function (e) {
    var a = NODES[e[0]], b = NODES[e[1]], l = sv('line', { x1: a.x, y1: a.y, x2: b.x, y2: b.y, 'class': 'ge' });
    gsvg.appendChild(l); edgeEl[e[0] + '>' + e[1]] = edgeEl[e[1] + '>' + e[0]] = l;
  });
  Object.keys(NODES).forEach(function (k) {
    var nd = NODES[k], g = sv('g', { 'class': 'gn', id: 'gn-' + k });
    var h = NH / 2, w = NW / 2, ch = 7;
    g.appendChild(sv('polygon', { points: [(nd.x - w + ch) + ',' + (nd.y - h), (nd.x + w) + ',' + (nd.y - h), (nd.x + w) + ',' + (nd.y + h - ch), (nd.x + w - ch) + ',' + (nd.y + h), (nd.x - w) + ',' + (nd.y + h), (nd.x - w) + ',' + (nd.y - h + ch)].join(' '), stroke: rgba(nd.c, 0.8) }));
    var tx = sv('text', { x: nd.x, y: nd.y + 6, 'text-anchor': 'middle' }); tx.textContent = nd.n; g.appendChild(tx);
    gsvg.appendChild(g); nd.g = g;
  });
  for (var pi = 0; pi < 8; pi++) { var pc = sv('circle', { r: 5, cx: -20, cy: -20, opacity: 0 }); gsvg.appendChild(pc); pulses.push({ c: pc, t0: 0, dur: 0, a: null, b: null, big: false, to: null, col: COL.cyan }); }
  function lit(k, ms) { if (k) litUntil[k] = performance.now() + ms; }
  function firePulse(from, to, big) {
    var f = key(from), t = key(to); if (!f) return;
    lit(f, 1400);
    if (!t || t === f) return;
    var p = null; for (var i = 0; i < pulses.length; i++) if (!pulses[i].dur) { p = pulses[i]; break; }
    if (!p) return;
    p.a = NODES[f]; p.b = NODES[t]; p.t0 = 0; p.dur = RM ? 1 : (big ? 1100 : 650); p.big = big; p.to = t; p.col = big ? COL.amber : NODES[f].c;
    p.c.setAttribute('r', big ? 10 : 5); p.c.setAttribute('fill', rgba(p.col, 1));
    var le = edgeEl[f + '>' + t]; if (le && big) { le.setAttribute('class', 'ge hot'); setTimeout(function () { le.setAttribute('class', 'ge'); }, 1600); }
  }
  function graphFrame(t) {
    var now = performance.now();
    for (var i = 0; i < pulses.length; i++) {
      var p = pulses[i]; if (!p.dur) continue;
      if (!p.t0) p.t0 = t;
      var u = clamp((t - p.t0) / p.dur, 0, 1), e = u * u * (3 - 2 * u);
      p.c.setAttribute('cx', (p.a.x + (p.b.x - p.a.x) * e).toFixed(1)); p.c.setAttribute('cy', (p.a.y + (p.b.y - p.a.y) * e).toFixed(1));
      p.c.setAttribute('opacity', u > 0.85 ? ((1 - u) * 6.6).toFixed(2) : 1);
      if (u >= 1) { p.dur = 0; p.c.setAttribute('opacity', 0); lit(p.to, p.big ? 2200 : 1000); }
    }
    for (var k in NODES) {
      var on = now < (litUntil[k] || 0);
      if (on !== !!litState[k]) { litState[k] = on; NODES[k].g.setAttribute('class', 'gn' + (on ? ' on' : '')); }
    }
  }

  /* ================= 4. risk dial + count-up ================= */
  var dial = $('dial'), R = 62, CX = 80, CY = 80, dialV = 0, dialT = 0, dialShown = -1, dialLvl = '';
  function pt(deg, r) { var a = deg * Math.PI / 180; return (CX + r * Math.cos(a)).toFixed(1) + ' ' + (CY - r * Math.sin(a)).toFixed(1); }
  var arcD = 'M' + pt(210, R) + ' A' + R + ' ' + R + ' 0 1 1 ' + pt(-30, R);
  dial.appendChild(sv('path', { d: arcD, 'class': 'dtrack', pathLength: 100 }));
  for (var ti = 0; ti <= 10; ti++) { var dg = 210 - ti * 24; dial.appendChild(sv('line', { x1: pt(dg, R + 9).split(' ')[0], y1: pt(dg, R + 9).split(' ')[1], x2: pt(dg, R + 15).split(' ')[0], y2: pt(dg, R + 15).split(' ')[1], 'class': 'dtick' })); }
  var dval = sv('path', { d: arcD, 'class': 'dval lo', pathLength: 100 }); dval.setAttribute('stroke-dasharray', '0 100'); dial.appendChild(dval);
  var dnum = sv('text', { x: CX, y: CY + 12, 'text-anchor': 'middle', 'class': 'dnum' }); dnum.textContent = '0'; dial.appendChild(dnum);
  var dlab = sv('text', { x: CX, y: 120, 'text-anchor': 'middle', 'class': 'dlab' }); dlab.textContent = 'RISK'; dial.appendChild(dlab);
  SK.risk = function (risk, lvl) {
    dialT = risk; if (RM) dialV = risk;
    if (lvl !== dialLvl) { dialLvl = lvl; dval.setAttribute('class', 'dval ' + lvl); }
  };
  function dialFrame() {
    if (Math.abs(dialT - dialV) > 0.002) dialV += (dialT - dialV) * 0.12; else dialV = dialT;
    var pct = Math.round(dialV * 100);
    if (pct !== dialShown) { dialShown = pct; dval.setAttribute('stroke-dasharray', (dialV * 100).toFixed(1) + ' 100'); dnum.textContent = String(pct); }
  }
  var cnt = { target: 0, disp: 0, shown: -1 };
  SK.wasted = function (sec) { if (sec < cnt.disp || RM) cnt.disp = sec; cnt.target = sec; };
  function counterFrame() {
    var d = cnt.target - cnt.disp;
    if (d !== 0) cnt.disp += Math.abs(d) < 0.05 ? d : d * 0.1;
    var s = Math.round(cnt.disp);
    if (s !== cnt.shown) { cnt.shown = s; $('wasted').textContent = mmss(s); }
  }

  /* ================= event intake from dashboard.js ================= */
  SK.event = function (type, d, prevSt) {
    if (SK.replay) return;
    switch (type) {
      case 'call_status':
        callActive = d.state === 'active' || d.state === 'ringing';
        callEnded = d.state === 'ended'; if (d.state === 'ringing') draftsReady = false;
        if (d.state === 'ringing') { orb.until = 0; orb.who = null; pendingLock = {}; }
        break;
      case 'turn':
        speak(d.speaker, estMs(d.text));
        if (d.speaker === 'kamla') firePulse('saarthi', 'kamla', false);
        break;
      case 'detector': lit('detector', 1200); break;
      case 'entity': if (d.status === 'confirmed' && prevSt !== 'confirmed' && !RM) { pendingLock[d.id] = true; verifying[d.id] = true; } break;
      case 'band': firePulse(d.from_agent, d.to_agent, d.kind === 'handoff'); break;
      case 'draft': draftsReady = true; break;
      case 'skill': firePulse('skill', 'intel', false); break;
    }
  };

  /* ================= loop + stats ================= */
  var st = { n: 0, work: 0, wmax: 0, dt: 0, dtn: 0, last: 0 };
  function tick(t) {
    var w0 = performance.now();
    if (st.last) { st.dt += t - st.last; st.dtn++; }
    st.last = t;
    orbFrame(t); dialFrame(); counterFrame(); graphFrame(t);
    for (var i = tasks.length - 1; i >= 0; i--) if (!tasks[i](t)) tasks.splice(i, 1);
    var w = performance.now() - w0; st.n++; st.work += w; if (w > st.wmax) st.wmax = w;
    requestAnimationFrame(tick);
  }
  document.addEventListener('visibilitychange', function () { st.last = 0; });
  SK.stats = function () { return { frames: st.n, avgWorkMs: st.work / Math.max(1, st.n), maxWorkMs: st.wmax, avgFrameMs: st.dt / Math.max(1, st.dtn) }; };
  SK.resetStats = function () { st = { n: 0, work: 0, wmax: 0, dt: 0, dtn: 0, last: 0 }; };
  requestAnimationFrame(tick);
})();

/* Saarthi Kavach dashboard.
   One keyed state store, updated from SSE (or mock), rendered once per requestAnimationFrame.
   SECURITY (C5): every string reaches the DOM via textContent / createTextNode only. No HTML-string injection anywhere.
   GATE G1: every phone value is shown with " (synthetic)". */
(function () {
  'use strict';

  var MOCK = /[?&]mock=1\b/.test(location.search);
  var QS = new URLSearchParams(location.search);
  var CITIZEN = QS.get('view') === 'citizen', VOICE = QS.get('voice') === '1';
  var MAX_TURNS = 12, MAX_BAND = 15, MAX_DRAFTS = 2, ENT_SLOTS = 6, PTT_MAX = 500;
  var $ = function (id) { return document.getElementById(id); };
  var SK = window.SK || null;   // optional visual layer (jarvis.js); absent in ?theme=classic

  /* ---------- store ---------- */
  var S = {
    call: { call_id: null, state: 'idle', scenario: null, startedAt: 0, endedAt: 0 },
    turns: new Map(),            // seq -> turn
    detector: null,
    entities: new Map(),         // id -> entity (insertion order = slot order)
    minutes: null,               // from metrics.minutes_wasted / goal_state.minutes_wasted
    metrics: {},
    band: [],
    drafts: new Map(),           // draft_id -> draft
    approving: {},               // draft_id -> true while request in flight
    goals: {}, simMs: 0, simAt: 0, policy: null, pacing: null,
    agents: null,                // agent_status.agents (sponsor rail); null until the backend sends it
    impact: null,                // session_impact tally (simulated calls)
    skillEv: null                // latest Finch scout result
  };
  var dirty = {}, glowPanel = null, scale = (MOCK && window.SaarthiMock && window.SaarthiMock.speed) || 1;

  var PANEL_OF = { call_status: 'pn-call', turn: 'pn-call', detector: 'pn-risk', entity: 'pn-ents',
    goal_state: null, metrics: null, band: 'pn-band', draft: 'pn-drafts', skill: 'pn-band', policy: 'pn-band', agent_status: null };

  function nowMs() { return performance.now() * scale; }

  /* ---------- text helpers (all return plain strings) ---------- */
  var PHONE_RE = /(?:\+91[ -]?\d{5}[ -]?\d{5}|\b[6-9]\d{9}\b|\b[6-9]\d{4}[ -]\d{5}\b)(?!\s*\(synthetic\))/g;
  function tagPhones(t) { return String(t == null ? '' : t).replace(PHONE_RE, '$& (synthetic)'); }
  function phoneValue(v) { v = String(v == null ? '' : v); return /synthetic/i.test(v) ? v : v + ' (synthetic)'; }
  function mmss(totalSec) {
    totalSec = Math.max(0, Math.round(totalSec));
    var m = Math.floor(totalSec / 60), s = totalSec % 60;
    return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
  }
  function minutesToMmss(v) {
    if (v == null) return '00:00';
    if (typeof v === 'string' && /^\d+:\d{2}$/.test(v)) return v;   // already mm:ss
    var n = Number(v);
    return isFinite(n) ? mmss(n * 60) : '00:00';
  }
  function minutesToSec(v) {
    if (v == null) return 0;
    if (typeof v === 'string' && /^\d+:\d{2}$/.test(v)) { var p = v.split(':'); return Number(p[0]) * 60 + Number(p[1]); }
    var n = Number(v); return isFinite(n) ? n * 60 : 0;
  }
  function secs(ms) { return !ms || ms < 50 || !isFinite(ms) ? '—' : (ms / 1000).toFixed(1) + ' s'; }
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }
  function esc(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  var hlRe = null, hlKey = '';
  function highlightRe() {
    var vals = [];
    S.entities.forEach(function (e) {
      var v = e.type === 'phone' ? phoneValue(e.value) : String(e.value || '');
      if (v.length >= 5) vals.push(v);
      if (e.type === 'phone' && e.value) vals.push(String(e.value));
    });
    vals.sort(function (a, b) { return b.length - a.length; });
    var key = vals.join('|');
    if (key !== hlKey) { hlKey = key; hlRe = vals.length ? new RegExp('(' + vals.map(esc).join('|') + ')', 'ig') : null; }
    return hlRe;
  }
  function rich(parent, text) {
    text = tagPhones(text);
    var re = highlightRe();
    if (!re) { parent.appendChild(document.createTextNode(text)); return; }
    var last = 0, m;
    re.lastIndex = 0;
    while ((m = re.exec(text))) {
      if (m.index > last) parent.appendChild(document.createTextNode(text.slice(last, m.index)));
      parent.appendChild(el('span', 'hl', m[0]));
      last = m.index + m[0].length;
      if (m[0].length === 0) re.lastIndex++;
    }
    if (last < text.length) parent.appendChild(document.createTextNode(text.slice(last)));
  }

  /* ---------- event ingestion ---------- */
  var audioQ = [], audioPlaying = false, audioSeen = new Set();
  function apply(type, d) {
    if (!d || typeof d !== 'object') return;
    var prevSt;
    switch (type) {
      case 'call_status':
        var prev = S.call.state;
        S.call.call_id = d.call_id || S.call.call_id;
        S.call.scenario = d.scenario || S.call.scenario;
        S.call.state = d.state || 'idle';
        if (S.call.state === 'active' && prev !== 'active') { S.call.startedAt = nowMs(); S.call.endedAt = 0; if (!S.simMs) S.simAt = nowMs(); }
        if (S.call.state === 'ringing' && prev !== 'ringing') resetCall();
        if (S.call.state === 'ended' && prev !== 'ended') S.call.endedAt = nowMs();
        if (S.call.state === 'idle') { S.call.startedAt = 0; S.call.endedAt = 0; }
        dirty.call = true; dirty.detector = true; break;
      case 'turn':
        if (d.seq == null) return;
        S.turns.set(d.seq, d);
        if (d.t_start != null && d.t_start >= S.simMs) { S.simMs = d.t_start; S.simAt = nowMs(); }
        if (S.turns.size > 200) { var k0 = S.turns.keys().next().value; S.turns.delete(k0); }
        if (d.audio_url && !audioSeen.has(d.seq)) { audioSeen.add(d.seq); audioQ.push(d.audio_url); playNext(); }
        dirty.turns = true; break;
      case 'detector':
        S.detector = d; dirty.detector = true; break;
      case 'entity':
        if (d.id == null) return;
        prevSt = (S.entities.get(d.id) || {}).status;
        S.entities.set(d.id, Object.assign({}, S.entities.get(d.id) || {}, d));
        dirty.ents = true; dirty.turns = true; dirty.drafts = true; break;
      case 'goal_state':
        if (d.goals) { S.goals = d.goals; dirty.ents = true; dirty.drafts = true; }
        if (d.minutes_wasted != null) { S.minutes = d.minutes_wasted; dirty.hero = true; }
        break;
      case 'skill':
        var names = (d.skills || []).map(function (k) { return k.name; }).join(', ') || 'none';
        S.skillEv = d; dirty.finch = true;
        S.band.push({ from_agent: 'Skill Scout', to_agent: 'Intel', kind: 'post', mirrored: null, _syn: true,
          text: 'Scout (' + (d.live ? 'live' : 'local snapshot') + ') for ' + String(d.scam_type || 'scam').replace(/_/g, ' ') + ': ' + names });
        if (S.band.length > MAX_BAND) S.band.splice(0, S.band.length - MAX_BAND);
        dirty.band = true; break;
      case 'agent_status':
        if (d.agents && typeof d.agents === 'object') { S.agents = d.agents; dirty.rail = true; } break;
      case 'policy':
        S.policy = d; dirty.band = true; break;
      case 'metrics':
        S.metrics = Object.assign(S.metrics, d);
        if (d.minutes_wasted != null) S.minutes = d.minutes_wasted;
        dirty.hero = true; break;
      case 'band':
        d._ts = d.ts ? Date.parse(d.ts) : Date.now();
        S.band.push(d); if (S.band.length > MAX_BAND) S.band.splice(0, S.band.length - MAX_BAND);
        dirty.band = true; dirty.drafts = true; dirty.strip = true; break;
      case 'draft':
        if (d.draft_id == null) return;
        S.drafts.set(d.draft_id, Object.assign({}, S.drafts.get(d.draft_id) || {}, d));
        var dd = S.drafts.get(d.draft_id); if (dd.status === 'approved' && !dd.approved_at) dd.approved_at = Date.now();
        if (S.drafts.size > MAX_DRAFTS) { var k1 = S.drafts.keys().next().value; S.drafts.delete(k1); }
        dirty.drafts = true; dirty.strip = true; break;
      case 'call_summary':
        if (d.session) { S.impact = d.session; dirty.hero = true; } break;
      default: return;
    }
    if (SK && SK.event) SK.event(type, d, prevSt);
    if (PANEL_OF[type]) glowPanel = PANEL_OF[type];
    if (type === 'entity') glowPanel = 'pn-ents';
    schedule();
  }
  function resetCall() {
    $('citizen').hidden = true;
    S.turns.clear(); S.entities.clear(); S.band.length = 0; S.drafts.clear();
    S.detector = null; S.minutes = null; S.goals = {}; S.skillEv = null; S.simMs = 0; S.simAt = 0; S.policy = null; S.metrics = {}; audioSeen.clear(); audioQ.length = 0;
    dirty.turns = dirty.ents = dirty.band = dirty.drafts = dirty.detector = dirty.hero = dirty.strip = dirty.finch = true;
  }
  function applySnapshot(s) {
    if (!s || typeof s !== 'object') return;
    if (SK) SK.replay = true;
    if (s.call) apply('call_status', s.call);
    else if (s.call_status) apply('call_status', s.call_status);
    (s.turns || []).forEach(function (t) { apply('turn', t); });
    if (s.detector) apply('detector', s.detector);
    (s.entities || []).forEach(function (e) { apply('entity', e); });
    if (s.goal_state) apply('goal_state', s.goal_state);
    if (s.metrics) apply('metrics', s.metrics);
    if (s.session_impact && s.session_impact.calls_n) { S.impact = s.session_impact; dirty.hero = true; }
    (s.band || []).forEach(function (b) { apply('band', b); });
    (s.drafts || []).forEach(function (d) { apply('draft', d); });
    if (s.agent_status) apply('agent_status', s.agent_status);
    var sk = s.skills || [];
    if (sk.length && sk[0] && sk[0].name != null && !sk[0].skills) apply('skill', { skills: sk, live: !!s.skills_live });   // bare skill items
    else sk.forEach(function (k) { apply('skill', k); });
    if (SK) SK.replay = false;
  }

  /* ---------- audio: play clips in order ---------- */
  var audio = new Audio();
  function playNext() {
    if (audioPlaying || !audioQ.length) return;
    audioPlaying = true;
    audio.src = audioQ.shift();
    var done = function () { audioPlaying = false; playNext(); };
    audio.onended = done; audio.onerror = done;
    var p = audio.play();
    if (p && p.catch) p.catch(done);   // autoplay blocked or bad clip: skip, never stall
    if (SK && SK.audio) SK.audio(audio);
  }

  /* ---------- render (once per animation frame) ---------- */
  var raf = 0;
  function schedule() { if (!raf) raf = requestAnimationFrame(render); }

  var STATE_LABEL = { idle: 'IDLE', ringing: 'RINGING', active: 'LIVE', ended: 'ENDED' };
  function callSeconds() {
    // Driven by call_status + the simulated clock (turn.t_start), so it agrees with minutes_wasted at any pacing.
    if (S.minutes != null) return minutesToSec(S.minutes);   // header clock and big counter both come from minutes_wasted
    var wasted = S.minutes == null ? 0 : (typeof S.minutes === 'string' ? Number(S.minutes.split(':')[0]) * 60 + Number(S.minutes.split(':')[1]) : Number(S.minutes) * 60) * 1000;
    var base = Math.max(S.simMs, wasted || 0);
    if (S.call.state === 'active') return (base + Math.min(nowMs() - (S.simAt || nowMs()), 6000)) / 1000;
    return base / 1000;
  }
  function renderCall() {
    var st = S.call.state, lv = $('live');
    lv.className = 'live' + (st === 'active' ? ' on' : st === 'ringing' ? ' ring' : '');
    $('liveTxt').textContent = (STATE_LABEL[st] || 'IDLE') + ' ' + mmss(callSeconds());
    $('btnCall').disabled = st === 'ringing' || st === 'active';
    $('btnEnd').disabled = !(st === 'ringing' || st === 'active');
    $('mic').disabled = st !== 'active';
  }
  var BUDGET_MS = 1500;   // dead-air budget: silence between the scammer clip ending and the first Kamla audio
  function renderHero() {
    if (SK && SK.wasted) SK.wasted(minutesToSec(S.minutes)); else $('wasted').textContent = minutesToMmss(S.minutes);
    var m = S.metrics, sp = MOCK ? 1 : S.pacing;
    var slow = !!(sp && sp !== 1);   // simulated clock: latencies are only meaningful at real-time speed
    var kt = 0; S.turns.forEach(function (t) { if (t.speaker !== 'scammer' && t.speaker !== 'filler') kt++; });
    var nK = m.kamla_turns != null ? Number(m.kamla_turns) : (m.turns ? Number(m.turns) : kt);
    var small = nK < 10, pw = small ? (m.dead_air_max_ms != null ? 'max so far' : 'p95 (n<10, indicative)') : 'p95';
    var pwA = small ? (m.answer_max_ms != null ? 'max so far' : 'p95 (n<10, indicative)') : 'p95';
    $('mL1').textContent = 'Dead air ' + pw;
    var da = small && m.dead_air_max_ms != null ? m.dead_air_max_ms : m.dead_air_p95_ms != null ? m.dead_air_p95_ms : m.substantive_p95_ms;
    var p95 = slow ? 0 : Number(da) || 0, has = p95 >= 50, ok = p95 <= BUDGET_MS;
    var pe = $('mP95'), be = $('mBudT');
    pe.textContent = secs(p95);
    pe.className = has ? (ok ? 'good' : 'bad') : '';
    be.textContent = has ? (ok ? '✓ under' : 'over') : '—';
    be.className = has ? (ok ? 'good' : 'bad') : '';
    var ans = slow ? 0 : Number(small && m.answer_max_ms != null ? m.answer_max_ms : m.answer_p95_ms != null ? m.answer_p95_ms : m.substantive_p95_ms) || 0;
    $('mAnsL').textContent = 'Kamla answer ' + pwA;
    $('mAnsV').textContent = secs(ans);
    $('mAnsS').textContent = ans >= 50 && m.llm_p95_ms != null
      ? '(LLM ' + (small ? 'indicative' : 'p95') + ' ' + secs(Number(m.llm_p95_ms) || 0) + ' · voice ' + (small ? 'indicative' : 'p95') + ' ' + secs(Number(m.tts_p95_ms) || 0) + ') · budget —' : '';
    $('mAns').title = 'Time from the caller finishing to the real reply starting. No budget: covered by filler; dead air is the budget metric.';
    $('mFill').textContent = !m.filler_rate ? '—' : Math.round(m.filler_rate * 100) + '%';
    $('mTurns').textContent = m.turns ? String(m.turns) : '—';
    $('mN').textContent = nK ? 'n = ' + nK + ' Kamla turns' : '';
    var nt = $('mNote');
    nt.textContent = slow ? 'latency measured only at real-time speed · sim ×' + sp : '';
    nt.hidden = !slow;
    var im = S.impact, ie = $('mImp');
    ie.hidden = !im;
    if (im) ie.textContent = 'This session (simulated): ' + im.calls_n + ' call' + (im.calls_n === 1 ? '' : 's') + ' · '
      + (Math.round(im.engaged_s / 6) / 10) + ' min scammer time engaged · ' + im.identifiers_verified
      + ' identifiers verified · ' + im.drafts + ' drafts';
  }
  if (MOCK) $('mockBadge').hidden = false;
  function renderTurns() {
    var tr = $('tr'), arr = Array.from(S.turns.values()).sort(function (a, b) { return a.seq - b.seq; }).slice(-MAX_TURNS);
    var kids = [];
    if (!arr.length) kids.push(el('div', 'empty', S.call.state === 'idle' ? 'Press Call to start a simulated scam call.' : 'Connecting...'));
    arr.forEach(function (t) {
      var who = t.speaker === 'scammer' ? 'sc' : t.speaker === 'filler' ? 'fl' : 'km';
      var name = t.speaker === 'scammer' ? 'Scammer' : t.speaker === 'filler' ? 'Kamla ji (filler)' : 'Kamla ji';
      var box = el('div', 'ln ' + who), head = el('em');
      head.appendChild(document.createTextNode(name));
      if (t.speaker !== 'scammer' && t.latency_ms > 0) head.appendChild(el('span', null, secs(t.latency_ms)));
      box.appendChild(head);
      var line = el('div'); rich(line, t.text); box.appendChild(line);
      if (t.gloss_en) { var g = el('small'); rich(g, t.gloss_en); box.appendChild(g); }
      kids.push(box);
    });
    var last = arr[arr.length - 1];
    if (S.call.state === 'active' && last && last.speaker === 'scammer') kids.push(el('div', 'typing', 'Kamla ji is replying ...'));
    tr.replaceChildren.apply(tr, kids);
    tr.scrollTop = tr.scrollHeight;
  }
  var SCAM_PLAIN = { digital_arrest: "Fake CBI / police 'digital arrest'", fake_kyc: 'Fake bank KYC / bank officer', fake_investment: 'Fake investment / trading tips' };
  function renderCitizen(d, risk) {
    var tp = String(d.scam_type || ''), known = tp && !/^(unknown|none|benign|normal)$/i.test(tp);
    var on = known && risk >= 0.67, c = $('citizen');
    if (on) $('czType').textContent = '— ' + (SCAM_PLAIN[tp] || tp.replace(/_/g, ' '));
    c.hidden = !on;
  }
  function renderDetector() {
    var d = S.detector;
    if (!d) return;
    var risk = Math.max(0, Math.min(1, Number(d.risk) || 0)), pct = Math.round(risk * 100);
    var lvl = risk >= 0.67 ? 'hi' : risk >= 0.34 ? 'md' : 'lo';
    var rt = $('riskT');
    rt.className = 'risk ' + lvl;
    rt.textContent = String(d.scam_type || 'Unknown').replace(/_/g, ' ') + ' • ' + (lvl === 'hi' ? 'HIGH' : lvl === 'md' ? 'MEDIUM' : 'LOW') + ' ' + pct;
    $('riskS').textContent = 'Stage: ' + String(d.stage || '-').replace(/_/g, ' ');
    renderCitizen(d, risk);
    if (SK && SK.risk) SK.risk(risk, lvl);
    $('riskM').style.left = 'calc(' + pct + '% - 3px)';
    var df = d.deepfake || {}, on = !!df.flag, deep = $('deep');
    var pend = !on && (!df.source || /^stub:/.test(String(df.source)));
    deep.className = 'deep' + (on ? ' flag' : pend ? ' pend' : '');
    var off = pend && S.call.state === 'ended';
    if (off) deep.className = 'deep off';
    $('deepIc').textContent = on ? '!' : off ? '–' : pend ? '?' : '✓';
    $('deepT').textContent = on ? 'caller voice: synthetic voice flagged' : off ? 'Caller voice check: not run (offline mode)' : pend ? 'Caller voice check: pending' : 'caller voice: no synthetic voice flagged';
    $('deepHd').textContent = 'Caller voice check (DetectifAI, not a sponsor)';
    deep.title = "Checks the CALLER's voice only. Kamla's voice is our own Kokoro TTS and is not checked.";
    $('deepS').textContent = on ? String(df.source || 'Flagged by voice check') + (df.score != null ? ' • score ' + Math.round(df.score * 100) + '%' : '') : off ? 'Detector stub, no result' : pend ? 'Not checked yet (flag only, not a verdict)' : 'Source: ' + df.source;
  }
  var TYPE_LABEL = { upi: 'UPI ID', bank_account: 'Account no.', ifsc: 'IFSC', phone: 'Phone' };
  var ST_LABEL = { heard: 'HEARD', suspect: 'SUSPECT', confirmed: '✓ READ-BACK MATCHED', given_up: 'GAVE UP', superseded: 'CORRECTED' };
  var AGENT_NAME = { saarthi: 'Saarthi', kamla: 'Kamla', verifier: 'Verifier', reporter: 'Reporter', intel: 'Intel', detector: 'Detector', skill_scout: 'Skill Scout', 'skill scout': 'Skill Scout', scout: 'Skill Scout', human: 'Human' };
  function agentName(n) { n = String(n == null ? '' : n); return AGENT_NAME[n.toLowerCase()] || (n ? n.charAt(0).toUpperCase() + n.slice(1) : '?'); }
  if (SK) SK.refresh = function () { dirty.ents = true; schedule(); };
  function renderEntities() {
    var all = Array.from(S.entities.values()), shown = all.slice(0, ENT_SLOTS), kids = [];
    shown.forEach(function (e) {
      var c = el('div', 'chip ' + (ST_LABEL[e.status] ? e.status : 'heard')), top = el('div', 'top2');
      top.appendChild(el('div', 'k', TYPE_LABEL[e.type] || String(e.type || 'Entity')));
      var vf = !!(SK && SK.verifying && SK.verifying(e.id));
      if (vf) c.className += ' verifying';
      top.appendChild(el('span', 'st', vf ? 'VERIFYING…' : (e.type === 'ifsc' && e.status === 'confirmed' ? 'FORMAT ✓ · verify in RBI IFSC directory' : (ST_LABEL[e.status] || 'HEARD'))));
      c.appendChild(top);
      if (e.status === 'confirmed' && e.type !== 'ifsc' && !vf) { var sy = el('span', 'syn', 'synthetic demo value'); sy.title = 'Read-back matched on a synthetic demo identifier; not a real account'; c.appendChild(sy); }
      c.appendChild(el('div', 'v' + (e.status === 'superseded' ? ' struck' : ''), e.type === 'phone' ? phoneValue(e.value) : String(e.value == null ? '' : e.value)));
      var res = e.resolved_by ? (e.ifsc_bank || e.upi_psp) : null;
      if (res) { var ra = el('div', 'ra', 'Action Agent lookup → ' + tagPhones(res)); ra.title = String(e.resolved_by);
        if (e.type === 'ifsc') { ra.appendChild(el('span', 'fic', ' (fictional demo lookup — verify in RBI IFSC directory)')); ra.title += ' (fictional demo lookup — verify in RBI IFSC directory)'; }
        c.appendChild(ra); }
      else if (e.ifsc_bank) {
        var xl = el('div', 'x', tagPhones(e.ifsc_bank));
        if (e.type === 'ifsc') {
          xl.appendChild(el('span', 'fic', ' (fictional demo lookup — verify in RBI IFSC directory)'));
          xl.title = String(e.ifsc_bank) + ' (fictional demo lookup — verify in RBI IFSC directory)';
        }
        c.appendChild(xl);
      }
      if (e.status === 'confirmed' && !vf && !res) c.appendChild(el('div', 'why', String(e.reason || e.verified_by || 'Read-back matched (synthetic demo value)')));
      if (e.status === 'superseded') c.appendChild(el('div', 'why dim', 'caller corrected it on read-back'));
      c.setAttribute('data-eid', String(e.id));
      kids.push(c);
    });
    var have = {}; all.forEach(function (e) { have[e.type] = true; });
    var missing = Object.keys(S.goals || {}).filter(function (k) { return !have[k] && TYPE_LABEL[k]; });
    for (var i = shown.length; i < ENT_SLOTS; i++) {
      var mt = missing.shift();
      if (mt) {
        var mc = el('div', 'chip missing'), tp = el('div', 'top2');
        tp.appendChild(el('div', 'k', TYPE_LABEL[mt])); tp.appendChild(el('span', 'st', 'MISSING'));
        mc.appendChild(tp); mc.appendChild(el('div', 'x', 'not yet obtained')); kids.push(mc);
      } else kids.push(el('div', 'chip empty-slot', 'listening for details ...'));
    }
    var ents = $('ents'); ents.replaceChildren.apply(ents, kids);
    if (SK && SK.afterEntities) setTimeout(SK.afterEntities, 0);
    $('more').textContent = all.length > ENT_SLOTS ? '+' + (all.length - ENT_SLOTS) + ' more' : '';
  }
  function agentClass(n) {
    n = String(n || '').toLowerCase();
    return n.indexOf('detect') >= 0 ? 'a-det' : n.indexOf('intel') >= 0 ? 'a-int' : n.indexOf('verif') >= 0 ? 'a-ver' :
      n.indexOf('report') >= 0 ? 'a-rep' : n.indexOf('skill') >= 0 ? 'a-skl' : n.indexOf('saarthi') >= 0 ? 'a-saa' : 'a-oth';
  }
  function hms(t) {
    var d = new Date(t || Date.now()), p = function (n) { return (n < 10 ? '0' : '') + n; };
    return p(d.getHours()) + ':' + p(d.getMinutes()) + ':' + p(d.getSeconds());
  }
  function renderBand() {
    var room = $('room'), kids = [];
    if (!S.band.length) kids.push(el('div', 'empty', 'Agents idle.'));
    S.band.forEach(function (b) {
      var m = el('div', 'msg ' + (b.kind || 'post'));
      m.appendChild(el('div', 'av ' + agentClass(b.from_agent), agentName(b.from_agent).charAt(0)));
      var body = el('div'), h = el('div', 'h'), nm = el('b', null, agentName(b.from_agent));
      h.appendChild(el('span', 'ts', hms(b._ts)));
      nm.appendChild(el('i', null, ' → ' + (b.to_agent ? agentName(b.to_agent) : 'room')));
      h.appendChild(nm);
      if (b.kind === 'handoff') h.appendChild(el('span', 'pill handoff', 'HANDOFF'));
      else if (b.kind === 'thought') h.appendChild(el('span', 'pill', 'thinking'));
      h.appendChild(el('span', 'pill' + (b.mirrored === true ? ' mir' : ''), b.mirrored === true ? '✓✓ on Band' : 'local'));
      body.appendChild(h);
      body.appendChild(el('div', 't', tagPhones(b.text)));
      m.appendChild(body);
      kids.push(m);
    });
    room.replaceChildren.apply(room, kids);
    room.scrollTop = room.scrollHeight;
    $('policy').textContent = S.policy ? 'Policy: ' + String(S.policy.kind || '').replace(/_/g, ' ') + (S.policy.detail ? ' - ' + S.policy.detail : '') : '';
  }
  var DRAFT_TITLE = { bank_alert: 'Bank alert', helpline_1930: '1930 complaint' };
  var HEAD_RE = /^(?:[A-Z0-9][A-Z0-9 \/&()'.,-]{2,46}:?|Intel\b.{0,30}|To be filled by complainant\b.{0,30}|[A-Z][A-Za-z \/&-]{2,40}:)$/;
  function draftText(parent, body, skipCase) {
    var lines = tagPhones(body).split('\n');
    if (/^\s*DRAFT\b.*(NOT SENT|SIMULATED)/i.test(lines[0] || '')) lines.shift();   // strip already shows the watermark
    while (lines.length && !lines[0].trim()) lines.shift();
    lines.forEach(function (ln) {
      var t = ln.trim();
      if (skipCase && /^Case ID:/.test(t)) return;   // shown on the card header instead
      var head = /^(INTEL|SUMMARY|TO BE FILLED BY COMPLAINANT|SUSPECTED FRAUD ALERT|CYBER FRAUD COMPLAINT)/.test(t) || (t && t.length <= 48 && HEAD_RE.test(t) && !/@/.test(t));
      parent.appendChild(el('div', head ? 'dl dh' : 'dl', ln || ' '));
    });
  }
  function openDraft(d) {
    var dlg = $('dlg'), bd = $('dlgBody');
    $('dlgT').textContent = (DRAFT_TITLE[d.kind] || 'Draft report') + (d.status === 'approved' ? ' (approved, simulated)' : ' (ready for approval)');
    var kids = [el('div', 'strip', 'DRAFT – SIMULATED DEMO DATA – NOT SENT TO ANY BANK OR 1930')], p = el('div', 'dtxt');
    if (d.case_id) kids.push(el('div', 'caseid', 'Case ID: ' + d.case_id));
    draftText(p, d.body, !!d.case_id); kids.push(p); bd.replaceChildren.apply(bd, kids);
    if (dlg.showModal) { if (!dlg.open) dlg.showModal(); } else dlg.setAttribute('open', '');
  }
  function renderDrafts() {
    var box = $('drafts'), kids = [];
    S.drafts.forEach(function (d) {
      var c = el('div', 'doc'), row = el('div', 'row');
      c.appendChild(el('div', 'strip', 'DRAFT – SIMULATED DEMO DATA – NOT SENT TO ANY BANK OR 1930'));
      var title = DRAFT_TITLE[d.kind] || 'Draft report';
      row.appendChild(el('h3', null, d.status === 'approved' ? title + ' · ✓ Approved by operator at ' + hms(d.approved_at) + ' — simulated, nothing sent' : title + ' · Ready for approval'));
      var ex = el('button', 'btn ghost', 'Expand'); ex.type = 'button'; ex.setAttribute('aria-label', 'Expand ' + title);
      ex.addEventListener('click', function () { openDraft(S.drafts.get(d.draft_id) || d); });
      row.appendChild(ex);
      if (d.status !== 'approved') {
        var b = el('button', 'btn', S.approving[d.draft_id] ? 'Approving ...' : 'Approve (human)');
        b.type = 'button'; b.disabled = !!S.approving[d.draft_id];
        b.addEventListener('click', function () { approve(d.draft_id); });
        row.appendChild(b);
      }
      c.appendChild(row);
      if (d.case_id) c.appendChild(el('div', 'caseid', 'Case ID: ' + d.case_id + ' (same case on both drafts)'));
      c.appendChild(el('div', 'dfill', 'Complainant must fill: name/account · UTR · amount · debit time'));
      var rq = /^\s*Request:\s*(.+)$/m.exec(String(d.body || ''));
      if (rq) c.appendChild(el('div', 'dreq', 'Request: ' + rq[1].trim()));
      var p = el('div', 'dtxt'); draftText(p, d.body, !!d.case_id); c.appendChild(p);
      kids.push(c);
    });
    if (kids.length) {
      var anyPending = false; S.drafts.forEach(function (d) { if (d.status !== 'approved') anyPending = true; });
      var nApp = 0; S.drafts.forEach(function (d) { if (d.status === 'approved') nApp++; });
      if (nApp === 0) kids.unshift(el('div', 'await', 'AWAITING HUMAN APPROVAL'));
      $('draftTag').textContent = nApp + ' of ' + S.drafts.size + ' approved';
    } else {
      var hand = S.band.some(function (b) { return b.kind === 'handoff'; });
      var gk = Object.keys(S.goals || {}), seen = {};
      S.entities.forEach(function (e) { if (e.status === 'confirmed') seen[e.type] = true; });
      gk.forEach(function (k) { if (S.goals[k] && S.goals[k].status === 'confirmed') seen[k] = true; });
      var got = Object.keys(seen).length;
      var pipe = el('div', 'pipe');
      [['Verifier', hand ? 'done' : 'active'], ['Reporter', hand ? 'active' : 'idle'], ['Human approval', 'idle']].forEach(function (s, i) {
        if (i) pipe.appendChild(el('span', 'parrow', '→'));
        pipe.appendChild(el('span', 'pstep ' + s[1], s[0]));
      });
      $('draftTag').textContent = 'Reporter';
      kids.push(pipe);
      var vtxt = got + '/' + Math.max(gk.length, got) + ' goals verified';
      if (hand) {
        var sp2 = el('div', 'drafting'); sp2.setAttribute('role', 'status');
        sp2.appendChild(el('i', 'spin')); sp2.appendChild(el('span', null, 'Reporter (AdaL) drafting…'));
        kids.push(sp2);
        kids.push(el('div', 'pstat dimm', 'Background job, about 23 s · ' + vtxt));
      } else kids.push(el('div', 'pstat', vtxt + ' · Reporter waiting'));
    }
    box.replaceChildren.apply(box, kids);
  }
  /* ---------- sponsor / agent status rail ---------- */
  var SPONSORS = [
    { name: 'Lyzr', role: 'Voice Agent · Kamla', keys: ['kamla', 'scammer'] },
    { name: 'Band', role: 'Agent room', keys: ['room'] },
    { name: 'AdaL', role: 'Reporter · drafts', keys: ['reporter'] },
    { name: 'Finch', role: 'Scout · catalogue', keys: ['scout'] },
    { name: 'Agent37', role: 'Hosting', keys: ['host'] }
  ];
  function renderRail() {
    var box = $('railChips'), kids = [], A = S.agents;
    SPONSORS.forEach(function (sp) {
      var got = A ? sp.keys.map(function (k) { return A[k]; }).filter(Boolean) : [];
      var live = got.filter(function (g) { return g.mode === 'live'; }).length;
      var st = !got.length ? 'na' : live === got.length ? 'live' : live ? 'part' : 'stub';
      var lab = st === 'live' ? 'LIVE' : st === 'part' ? 'PARTIAL' : st === 'stub' ? 'STUB' : '—', role = sp.role;
      if (sp.name === 'Agent37' && A) {
        var hp = got.length ? String(got[0].platform || '').toLowerCase() : '';
        if (hp !== 'agent37') { lab = 'LOCAL'; st = 'stub'; role = 'Hosting · not deployed'; }
      }
      if (sp.name === 'Lyzr' && A && A.scammer && String(A.scammer.mode).toLowerCase() === 'scripted') { lab = 'SCRIPTED'; st = 'part'; role = 'Kamla live · scammer scripted'; }
      var c = el('div', 'rc r-' + st), t = el('div', 'rt');
      t.appendChild(el('i')); t.appendChild(el('b', null, sp.name)); t.appendChild(el('span', null, lab));
      c.appendChild(t); c.appendChild(el('div', 'rr', role));
      kids.push(c);
    });
    box.replaceChildren.apply(box, kids);
  }

  /* ---------- handoff strip ---------- */
  function msTime(ms) {
    ms = Math.max(0, Math.round(Number(ms) || 0));
    var m = Math.floor(ms / 60000), s = Math.floor(ms / 1000) % 60, r = ms % 1000;
    return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s + '.' + (r < 10 ? '00' : r < 100 ? '0' : '') + r;
  }
  var STRIP_MAX = 6;
  function renderStrip() {
    var hs = $('hs'), all = S.band.filter(function (b) { return !b._syn; }), pick = all.slice(-STRIP_MAX);
    var hand = all.filter(function (b) { return b.kind === 'handoff'; }).pop();
    if (hand && pick.indexOf(hand) < 0) {   // the handoff is the headline: always keep it on the strip
      var keep = all.slice(-(STRIP_MAX - 1)).concat(hand);
      pick = all.filter(function (b) { return keep.indexOf(b) >= 0; });
    }
    var kids = [];
    if (!pick.length) kids.push(el('div', 'hempty', 'Waiting for agents to hand off…'));
    pick.forEach(function (b, i) {
      if (i) kids.push(el('span', 'harr', '›'));
      var isH = b.kind === 'handoff', c = el('div', 'hc' + (isH ? ' hand' : b.kind === 'thought' ? ' thought' : ''));
      c.appendChild(el('div', 'ha', agentName(b.from_agent) + ' → ' + (b.to_agent ? agentName(b.to_agent) : 'room')));
      var l2 = el('div', 'hb');
      l2.appendChild(el('span', 'ht', b.t_ms != null ? msTime(b.t_ms) : hms(b._ts)));
      if (isH) {
        var onBand = b.mirrored === true;
        var woke = false; S.drafts.forEach(function (d) { if (d.trigger === 'band_mention') woke = true; });
        l2.appendChild(el('span', 'hk' + (onBand ? ' mir' : ''), !onBand ? 'local' : woke ? 'Reporter woke from Band ✓' : 'posted ✓' + (b.band_msg_id ? ' msg ' + String(b.band_msg_id).slice(0, 8) : '')));
      } else l2.appendChild(el('span', 'hk', String(b.kind || 'post')));
      c.appendChild(l2);
      kids.push(c);
    });
    hs.replaceChildren.apply(hs, kids);
  }

  /* ---------- Finch catalogue scout card ---------- */
  function renderFinch() {
    var f = $('finch'), d = S.skillEv;
    if (!d || (!(d.skills || []).length && d.total == null)) { f.hidden = true; return; }
    f.hidden = false;
    var list = (d.skills || []).slice(0, 3), n = d.total != null ? d.total : (d.skills || []).length, kids = [];
    var h = el('div', 'fh2');
    h.appendChild(el('b', null, 'Finch catalogue scout'));
    h.appendChild(document.createTextNode(' — discovered ' + n + ' skill' + (n === 1 ? '' : 's') + ' '));
    h.appendChild(el('span', 'fl2' + (d.live ? ' on' : ''), d.live ? 'live' : 'snapshot'));
    kids.push(h);
    var row = el('div', 'fsk');
    list.forEach(function (k) {
      var c = el('span', 'fk'); c.appendChild(el('b', null, String(k.name || '?')));
      if (k.category) c.appendChild(el('i', null, String(k.category)));
      if (k.free === true) c.appendChild(el('u', null, 'free'));
      if (k.summary) c.title = String(k.summary);
      row.appendChild(c);
    });
    kids.push(row);
    kids.push(el('div', 'fnote', 'discovery only, not executed'));
    f.replaceChildren.apply(f, kids);
  }

  function render() {
    raf = 0;
    var d = dirty; dirty = {};
    if (d.call || S.call.state === 'active' || S.call.state === 'ringing') renderCall();
    if (d.hero) renderHero();
    if (d.turns) renderTurns();
    if (d.detector) renderDetector();
    if (d.ents) renderEntities();
    if (d.band) renderBand();
    if (d.drafts) renderDrafts();
    if (d.rail) renderRail();
    if (d.strip) renderStrip();
    if (d.finch) renderFinch();
    if (glowPanel) {
      var p = $(glowPanel); glowPanel = null;
      p.classList.remove('glow'); void p.offsetWidth; p.classList.add('glow');
    }
  }
  setInterval(function () { if (S.call.state === 'active') { dirty.call = true; schedule(); } }, 500);

  /* ---------- actions ---------- */
  function post(url, body) {
    return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
  }
  function note(msg, err) { var m = $('pttMsg'); m.textContent = msg || ''; m.className = 'pmsg' + (err ? ' err' : ''); }

  function approve(id) {
    S.approving[id] = true; dirty.drafts = true; schedule();
    var done = function () { delete S.approving[id]; dirty.drafts = true; schedule(); };
    if (MOCK) { apply('draft', { draft_id: id, status: 'approved', approved_at: Date.now() }); done(); return; }
    post('/api/drafts/' + encodeURIComponent(id) + '/approve', { approver: 'demo-operator' })
      .then(function (r) {
        if (r.status === 409) return { status: 'approved' };   // already approved
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json().catch(function () { return {}; });
      })
      .then(function (j) { apply('draft', { draft_id: id, status: (j && j.status) || 'approved', approved_at: Date.now() }); done(); })
      .catch(function () { note('Approval failed', true); done(); });
  }
  function sendPtt() {
    var ta = $('pttText'), t = ta.value.trim().slice(0, PTT_MAX);   // sent raw; the synthetic suffix is added only when displaying
    if (!t) return;
    ta.value = ''; $('pttCnt').textContent = '0/' + PTT_MAX;
    if (MOCK) { note('Sent (mock mode: scripted replay continues)'); return; }
    post('/api/ptt', { text: t }).then(function (r) { note(r.ok ? 'Sent' : 'Send failed: HTTP ' + r.status, !r.ok); })
      .catch(function () { note('Send failed', true); });
  }
  $('pttText').addEventListener('input', function () { $('pttCnt').textContent = this.value.length + '/' + PTT_MAX; });
  $('pttText').addEventListener('keydown', function (e) { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendPtt(); } });
  $('pttSend').addEventListener('click', sendPtt);

  // Web Speech API: Chrome sends audio to Google for transcription (notice shown in the panel).
  if (VOICE) { $('mic').hidden = false; $('pttTag').textContent = 'voice (Chrome)'; $('pttNotice').textContent = 'Voice is transcribed by Google via Chrome; speak only cue-card details; no real personal information.'; document.querySelector('.ptt').classList.add('hasmic'); }
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition, rec = null;
  $('mic').addEventListener('click', function () {
    var mic = this;
    if (!SR) { note('Speech input needs Chrome. Type instead.', true); return; }
    if (rec) { rec.stop(); return; }
    rec = new SR(); rec.lang = $('pttLang').value; rec.interimResults = false; rec.maxAlternatives = 1;
    rec.onresult = function (ev) {
      var txt = ''; for (var i = ev.resultIndex; i < ev.results.length; i++) txt += ev.results[i][0].transcript;
      $('pttText').value = txt.slice(0, PTT_MAX); sendPtt();
    };
    rec.onerror = function (ev) { note('Mic error: ' + ev.error, true); };
    rec.onend = function () { rec = null; mic.classList.remove('rec'); mic.textContent = 'Tap to talk'; };
    mic.classList.add('rec'); mic.textContent = 'Listening ... tap to stop'; note('');
    try { rec.start(); } catch (e) { rec = null; mic.classList.remove('rec'); mic.textContent = 'Tap to talk'; }
  });

  function startCall() {
    if (MOCK) { window.SaarthiMock.start(apply, { speed: scale }); return; }
    post('/api/call/start', { scenario: $('scenario').value, input_mode: $('inputMode').value })
      .then(function (r) { note(r.ok ? '' : r.status === 429 ? 'Too many calls started; wait a minute' : r.status === 409 ? 'A call is already running' : 'Could not start call: HTTP ' + r.status, !r.ok); })
      .catch(function () { note('Could not start call', true); });
  }
  function endCall() {
    if (MOCK) { window.SaarthiMock.stop(); apply('call_status', { call_id: S.call.call_id, state: 'ended' }); return; }
    post('/api/kill').catch(function () { note('Could not end call', true); });
  }
  $('btnCall').addEventListener('click', startCall);
  $('btnEnd').addEventListener('click', endCall);

  /* ---------- fit 1920x1080 stage to the window ---------- */
  function fit() {
    // Desktop: scale the whole 1920x1080 console into the real window (any laptop size / DPI), centred, no scrollbars.
    // Phones (<=768px) use the stacked CSS layout instead.
    var w = window.innerWidth, h = window.innerHeight, small = w <= 768;
    var k = small ? 1 : Math.min(w / 1920, h / 1080);
    var dx = small ? 0 : Math.max(0, (w - 1920 * k) / 2);
    $('stage').style.transform = small ? '' : 'translate(' + dx + 'px,0) scale(' + k + ')';
    document.documentElement.style.overflow = small ? '' : 'hidden';
    document.body.style.overflow = small ? '' : 'hidden';
  }
  window.addEventListener('resize', fit); fit();

  /* ---------- technical details toggle (default ON for the judge console) ---------- */
  function techPref() { try { var v = localStorage.getItem('sk_tech'); return v === null ? true : v === '1'; } catch (e) { return true; } }
  function setTech(on, save) {
    document.body.classList.toggle('tech-off', !on);
    $('techBtn').setAttribute('aria-pressed', on ? 'true' : 'false'); $('techState').textContent = on ? 'ON' : 'OFF';
    if (save) { try { localStorage.setItem('sk_tech', on ? '1' : '0'); } catch (e) { /* storage blocked: keep in memory */ } }
  }
  if (CITIZEN) { setTech(false, false); $('techBtn').hidden = true; document.body.classList.add('citizen-view'); }
  else { setTech(techPref(), false); $('techBtn').addEventListener('click', function () { setTech(document.body.classList.contains('tech-off'), true); }); }
  $('dlgX').addEventListener('click', function () { var d = $('dlg'); if (d.close) d.close(); else d.removeAttribute('open'); });
  $('dlg').addEventListener('click', function (e) { if (e.target === this && this.close) this.close(); });

  /* ---------- wave bars (static decoration) ---------- */
  (function () {
    var w = $('wave'), hs = [0.4, 0.9, 0.6, 1, 0.5, 0.85, 0.65, 0.95, 0.45, 0.8];
    hs.forEach(function (h, i) { var b = el('i'); b.style.animationDelay = (i * 0.11) + 's'; b.style.animationDuration = (0.6 + h * 0.5) + 's'; w.appendChild(b); });
  })();

  /* ---------- boot ---------- */
  dirty = { call: true, hero: true, turns: true, ents: true, band: true, drafts: true, detector: true, rail: true, strip: true, finch: true };
  render();

  var lastEventId = 0;
  var connTries = 0;
  function connect(since) {
    var qs = [];
    if (since) qs.push('since=' + encodeURIComponent(since));
    var es = new EventSource('/api/events' + (qs.length ? '?' + qs.join('&') : ''));
    es.onopen = function () { connTries = 0; };
    es.onerror = function () {
      if (es.readyState !== 2 || connTries++ > 2) return;   // CLOSED: reconnect a few times
      setTimeout(function () { connect(lastEventId || since); }, 1000);
    };
    if (since) lastEventId = Number(since) || 0;
    ['call_status', 'turn', 'detector', 'entity', 'goal_state', 'band', 'metrics', 'draft', 'skill', 'policy', 'agent_status', 'call_summary'].forEach(function (t) {
      es.addEventListener(t, function (ev) {
        try {
          var d = JSON.parse(ev.data);
          if (d.event_id != null) { if (d.event_id <= lastEventId) return; lastEventId = d.event_id; }   // de-dupe replays
          apply(t, d);
        } catch (e) { /* ignore malformed event */ }
      });
    });
  }
  if (MOCK) {
    var q = new URLSearchParams(location.search);
    if (q.get('autostart') !== '0') setTimeout(startCall, 600);
  } else {
    var getState = function () {
      return fetch('/api/state').then(function (r) { return r.ok ? r.json() : null; });
    };
    fetch('/api/health').then(function (r) { return r.ok ? r.json() : null; }).then(function (h) {
      if (h && h.mode && h.mode.pacing != null) { S.pacing = h.mode.pacing; dirty.hero = true; schedule(); }
    }).catch(function () { /* optional */ });
    getState().then(function (s) { applySnapshot(s); return s; })
      .catch(function () { /* no snapshot available: rely on SSE */ })
      .then(function (s) {
        connect(s && s.last_event_id);
        if (new URLSearchParams(location.search).get('autostart') === '1') setTimeout(startCall, 300);
      });
  }
})();

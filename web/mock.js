/* Mock replay for dashboard.html?mock=1  (add &speed=4 to fast-forward, &autostart=0 to wait for the Call button).
   A realistic ~165 s synthetic digital-arrest call. All names, numbers, IDs are fake. */
(function () {
  'use strict';
  var q = new URLSearchParams(location.search);
  var speed = Math.max(0.25, Number(q.get('speed')) || 1);
  var timers = [];

  var T0 = 3000, STEP = 5400;
  function tt(seq) { return T0 + (seq - 1) * STEP; }
  var ev = [];
  function add(t, type, d) { ev.push({ t: t, type: type, d: d }); }

  var turns = [
    ['scammer', 'Namaste, main Inspector Vikram Rathore bol raha hoon, CBI cyber cell se. Aapke naam se ek parcel pakda gaya hai.', 'Hello, I am Inspector Vikram Rathore from the CBI cyber cell. A parcel in your name has been seized.'],
    ['kamla', 'Arre baap re! CBI? Beta, main to bas Kamla hoon, mere paas koi parcel nahi aaya.', 'Oh my! CBI? Dear, I am just Kamla, no parcel came to me.', 1450],
    ['scammer', 'Madam, parcel mein 140 gram MDMA aur paanch passport mile hain. Aap abhi digital arrest mein hain.', 'Madam, the parcel has 140 grams of MDMA and five passports. You are under digital arrest right now.'],
    ['filler', 'Haan... haan... ek minute beta...', 'Yes... yes... one minute, dear...', 380],
    ['kamla', 'Hai Ram, mera BP badh gaya. Thoda dheere bolo, kaan kam sunte hain.', 'Oh Lord, my BP has shot up. Speak slowly, my hearing is weak.', 1620],
    ['scammer', 'Camera on rakhiye, call kaatna mat. Ye Supreme Court ka order hai. Mera number likh lijiye: +91 90000 12345.', 'Keep your camera on, do not cut the call. This is a Supreme Court order. Note my number: +91 90000 12345.'],
    ['kamla', 'Number dobara bolo na beta, chashma dhoondh rahi hoon, likhne ke liye.', 'Say the number again, dear, I am looking for my glasses to write it down.', 1380],
    ['scammer', 'Plus nine one, nine zero zero zero zero, one two three four five. Likh liya? Ab dhyaan se suniye.', 'Plus nine one, nine zero zero zero zero, one two three four five. Written? Now listen carefully.'],
    ['kamla', 'Haan likh liya. Par beta, mera beta Mumbai mein hai, usse puchun?', 'Yes, I wrote it. But dear, my son is in Mumbai, shall I ask him?', 1510],
    ['scammer', 'Bilkul nahi! Kisi ko mat batana, warna giraftari hogi. Case band karne ke liye RBI secure account mein verification deposit karna hoga.', 'Absolutely not! Tell no one or you will be arrested. To close the case you must pay a verification deposit into the RBI secure account.'],
    ['kamla', 'Deposit? Kitna beta? Aur kahan bhejun?', 'Deposit? How much, dear? And where do I send it?', 1290],
    ['scammer', 'Sirf 48,000 rupaye, refundable. UPI ID likhiye: officer.rathore.cbi@demobank. Jaldi kijiye.', 'Only 48,000 rupees, refundable. Write the UPI ID: officer.rathore.cbi@demobank. Hurry.'],
    ['filler', 'Ek second beta, pen dhoondh rahi hoon...', 'One second, dear, I am looking for a pen...', 410],
    ['kamla', 'UPI ID dobara bolo na, "officer" ke baad kya tha?', 'Say the UPI ID again, what came after "officer"?', 1740],
    ['scammer', 'officer dot rathore dot cbi at demobank. Madam jaldi kijiye, time kam hai!', 'officer dot rathore dot cbi at demobank. Madam, hurry, there is little time!'],
    ['kamla', 'Haan haan likh rahi hoon... Aur koi account number hai? UPI se mujhe darr lagta hai.', 'Yes yes I am writing... Is there an account number too? UPI scares me.', 1560],
    ['scammer', 'Theek hai, bank transfer kar dijiye. Account number 000012345678, IFSC DEMO0000417.', 'Fine, do a bank transfer. Account number 000012345678, IFSC DEMO0000417.'],
    ['kamla', 'Itna lamba number! Dheere dheere bolo, ek ek ank.', 'Such a long number! Say it slowly, digit by digit.', 1420],
    ['scammer', 'Zero zero zero zero, one two three four, five six seven eight. IFSC D-E-M-O zero zero zero zero four one seven.', 'Zero zero zero zero, one two three four, five six seven eight. IFSC D-E-M-O zero zero zero zero four one seven.'],
    ['kamla', 'Beta ye bank kaunsa hai? Mere paas to bas post office ki passbook hai.', 'Dear, which bank is this? I only have a post office passbook.', 1480],
    ['scammer', 'Demo Co-operative Bank hai madam, RBI approved. Aap bas paise bhejiye.', 'It is Demo Co-operative Bank, madam, RBI approved. Just send the money.'],
    ['kamla', 'Achha achha... par mera network ja raha hai. Aap apna doosra number do, callback ke liye.', 'Okay okay... but my network is dropping. Give me your other number for a callback.', 1650],
    ['scammer', 'Mere senior officer ka number hai +91 90000 67890. Unse baat kijiye.', 'My senior officer\'s number is +91 90000 67890. Speak to him.'],
    ['kamla', 'Arre wah, senior se hi baat karun? Ek minute, chai ubal gayi!', 'Oh wow, shall I speak to the senior? One minute, the tea is boiling over!', 1530],
    ['filler', 'Haan beta... hello? Awaaz aa rahi hai?', 'Yes dear... hello? Can you hear me?', 360],
    ['scammer', 'Madam sunai de raha hai? Aap time waste kar rahi hain! Warna warrant nikal jayega.', 'Madam, can you hear? You are wasting time! Or a warrant will be issued.'],
    ['kamla', 'Nahi nahi beta, warrant mat nikalo. UPI app khol rahi hoon... ye kaun sa button hai?', 'No no dear, do not issue a warrant. I am opening the UPI app... which button is this?', 1590],
    ['scammer', 'Madam green button dabaiye... Ye kya, aap mere saath khel rahi hain?', 'Madam, press the green button... What is this, are you playing with me?'],
    ['kamla', 'Bachcha, mere paas to bas 200 rupaye hain. Tum mere bete jaise ho, chai pi lo.', 'Child, I only have 200 rupees. You are like my son, have some tea.', 1700],
    ['scammer', 'Bakwaas band karo! Main call kaat raha hoon.', 'Stop this nonsense! I am cutting the call.']
  ];
  turns.forEach(function (x, i) {
    var seq = i + 1;
    add(tt(seq) + (x[0] === 'scammer' ? 0 : 700), 'turn', { seq: seq, speaker: x[0], text: x[1], gloss_en: x[2], audio_url: null, t_start: tt(seq) + (x[0] === 'scammer' ? 0 : 700) - 2600, latency_ms: x[3] == null ? 0 : x[3] });
  });

  var UPI = 'officer.rathore.cbi@demobank', ACC = '000012345678', IFSC = 'DEMO0000417';
  function ent(seq, dt, id, type, value, status, extra) {
    var d = { id: id, type: type, value: value, status: status };
    if (typeof extra === 'string') d.ifsc_bank = extra; else if (extra) Object.assign(d, extra);
    add(tt(seq) + dt, 'entity', d);
  }
  ent(6, 900, 'e1', 'phone', '+91 90000 12345', 'heard');
  ent(8, 900, 'e1', 'phone', '+91 90000 12345', 'suspect');
  ent(12, 900, 'e2', 'upi', UPI, 'heard');
  ent(15, 900, 'e2', 'upi', UPI, 'suspect');
  ent(17, 900, 'e3', 'bank_account', ACC, 'heard');
  ent(17, 1400, 'e4', 'ifsc', IFSC, 'heard');
  ent(19, 900, 'e3', 'bank_account', ACC, 'suspect');
  ent(19, 1400, 'e4', 'ifsc', IFSC, 'suspect', { ifsc_bank: 'Demo Co-operative Bank (synthetic)', resolved_by: 'action_agent:ifsc_lookup', upi_psp: null });
  ent(21, 1200, 'e2', 'upi', UPI, 'confirmed', { resolved_by: 'action_agent:upi_psp_lookup', upi_psp: 'Demo Pay PSP (synthetic)' });
  ent(21, 2600, 'e4', 'ifsc', IFSC, 'confirmed', { ifsc_bank: 'Demo Co-operative Bank (synthetic)', resolved_by: 'action_agent:ifsc_lookup', upi_psp: null });
  ent(23, 900, 'e5', 'phone', '+91 90000 67890', 'heard');
  ent(25, 900, 'e1', 'phone', '+91 90000 12345', 'confirmed');
  ent(27, 1000, 'e3', 'bank_account', ACC, 'confirmed');
  ent(27, 1800, 'e5', 'phone', '+91 90000 67890', 'suspect');
  ent(28, 1200, 'e6', 'upi', 'cbi.helpdesk7@demopay', 'heard');

  // detector
  add(tt(1) + 1500, 'detector', { scam_type: 'digital_arrest', stage: 'hook', risk: 0.41, deepfake: { flag: false, source: 'stub:not_checked' } });
  add(tt(3) + 1200, 'detector', { scam_type: 'digital_arrest', stage: 'authority', risk: 0.66, deepfake: { flag: false, source: 'stub:not_checked' } });
  add(tt(6) + 1500, 'detector', { scam_type: 'digital_arrest', stage: 'urgency', risk: 0.78, deepfake: { flag: false, source: 'stub:not_checked' } });
  add(tt(8) + 2200, 'detector', { scam_type: 'digital_arrest', stage: 'urgency', risk: 0.84, deepfake: { flag: true, source: 'Flagged by DetectifAI' } });
  add(tt(10) + 1500, 'detector', { scam_type: 'digital_arrest', stage: 'payment_ask', risk: 0.9, deepfake: { flag: true, source: 'Flagged by DetectifAI' } });
  add(tt(17) + 1200, 'detector', { scam_type: 'digital_arrest', stage: 'pressure', risk: 0.94, deepfake: { flag: true, source: 'Flagged by DetectifAI' } });

  // band room
  var bandN = 0;
  function bandId() { bandN++; var h = (0x9e3779b1 * (bandN + 7) >>> 0).toString(16); return ('00000000' + h).slice(-8) + '-6e0b-4d1a-9b3e-5c8d12f07a64'; }
  function band(t, from, to, text, kind, mirrored) {
    kind = kind || 'post';
    add(t, 'band', { from_agent: from, to_agent: to, text: text, kind: kind, mirrored: kind !== 'thought',
      t_ms: Math.max(0, t - 2600), band_msg_id: kind === 'thought' ? null : bandId() });
  }
  band(2600, 'Saarthi', 'Detector', 'Call started, scenario digital_arrest, audio stream open.');
  band(tt(1) + 2000, 'Detector', 'Intel', 'Authority-impersonation pattern, risk 0.41 and rising.');
  band(tt(6) + 2200, 'Intel', null, 'Possible callback number heard, tracking it.', 'thought', false);
  band(tt(8) + 2800, 'Detector', 'Intel', 'Synthetic voice flagged by DetectifAI. Keep him talking.');
  band(tt(12) + 1800, 'Intel', 'Verifier', 'UPI ID heard once, please verify when confirmed twice.');
  band(tt(15) + 1800, 'Skill Scout', 'Intel', 'Found IFSC-format check skill from Finch, attached to the room.');
  band(tt(19) + 2400, 'Intel', 'Verifier', 'UPI + account + IFSC extracted, please verify.');
  band(tt(21) + 2000, 'Verifier', null, 'IFSC prefix lookup running against the synthetic bank table.', 'thought', false);
  band(tt(21) + 3400, 'Verifier', 'Intel', 'UPI confirmed. IFSC format valid, bank is Demo Co-operative Bank (synthetic).');
  band(tt(25) + 1800, 'Intel', 'Verifier', 'Callback +91 90000 12345 repeated twice, marking confirmed.');
  band(tt(27) + 2600, 'Verifier', 'Reporter', '@reporter report job rj_3f9a1c7e2b40 ready', 'handoff');
  band(tt(28) + 2600, 'Reporter', 'Verifier', 'Job rj_3f9a1c7e2b40 accepted, drafting now.');
  band(tt(29) + 1800, 'Reporter', 'Saarthi', 'Two drafts ready for human approval. Nothing is sent.');

  // drafts
  var CASE = 'SK-20261123-3F9A1C';
  function draftBody(title) {
    return ['DRAFT - SIMULATED DEMO DATA - NOT SENT TO ANY BANK OR 1930', '', title, '',
      'Case ID: ' + CASE + '   (one case: the bank and 1930 drafts carry the same ID, file it once)', '',
      'INTEL (extracted by code, verified by read-back; synthetic demo data)',
      '  Beneficiary account : 000012345678',
      '  IFSC                : DEMO0000417 (Demo Co-operative Bank, Demo Branch)',
      '  UPI handle          : officer.rathore.cbi@demobank (Demo Pay PSP)',
      '  Scammer phone(s)    : +91 90000 12345; +91 90000 67890',
      "  Scam type           : Fake CBI / police 'digital arrest'",
      '  Stages observed     : hook > authority > urgency > payment_ask > pressure',
      '  Call start (IST)    : synthetic demo call',
      '  Call ID             : mock-001',
      '  Evidence            : transcript sha256 (synthetic)', '',
      'SUMMARY', 'A synthetic caller posing as a CBI officer demanded a refundable deposit to a secure account under threat of arrest. The synthetic-voice check flagged the call (flag only, not a verdict).', '',
      'TO BE FILLED BY COMPLAINANT BEFORE SUBMISSION',
      '  Complainant name / account: ______________________',
      '  UTR / transaction reference: ______________________',
      '  Amount (INR): ______________________',
      '  Debit date and time: ______________________', '',
      'Request: please review under your own procedures and, if warranted, flag or hold the beneficiary account and UPI handle pending investigation.', '',
      'DRAFT - SIMULATED DEMO DATA - NOT SENT TO ANY BANK OR 1930'].join('\n');
  }
  add(tt(29) + 2000, 'draft', { draft_id: 'd1', kind: 'bank_alert', status: 'pending', case_id: CASE, trigger: 'band_mention', band_msg_id: 'mock0bm1a2b3c4d',
    body: draftBody('SUSPECTED FRAUD ALERT (DRAFT) - for the fraud desk of the receiving bank') });
  add(tt(29) + 3200, 'draft', { draft_id: 'd2', kind: 'helpline_1930', status: 'pending', case_id: CASE, trigger: 'band_mention', band_msg_id: 'mock0bm1a2b3c4d',
    body: draftBody('CYBER FRAUD COMPLAINT (DRAFT) - for the national helpline 1930 / cybercrime portal') });

  add(tt(15) + 2300, 'skill', { scam_type: 'digital_arrest', role: 'discovery_only', live: true, total: 13, query: 'scam',
    skills: [
      { name: 'onlam', slug: 'onlam_finchip', category: 'Security Audit', free: true, summary: 'Online scams are becoming more sophisticated every year.', source: 'finch_live' },
      { name: 'velorin', slug: 'velorin_finchip', category: 'Education & Research', free: true, summary: 'Financial scams target vulnerable individuals through phone calls and online messages.', source: 'finch_live' },
      { name: 'uzi-trap-detector-finchip-new', slug: 'uzi-trap-detector-finchip-new_finchip', category: 'Security Audit', free: true, summary: 'A pump-and-dump detector for A-share tips', source: 'finch_live' }
    ] });
  add(300, 'agent_status', { agents: {
    kamla: { platform: 'Lyzr', mode: 'live' }, scammer: { platform: 'Lyzr', mode: 'scripted' },
    reporter: { platform: 'AdaL', mode: 'live' }, scout: { platform: 'Finch', mode: 'live' },
    room: { platform: 'Band', mode: 'live' }, host: { platform: 'local', mode: 'stub' } } });
  add(tt(24) + 1500, 'policy', { kind: 'c2_filter', detail: 'blocked a non-synthetic number in a draft line' });
  add(2700, 'goal_state', { goals: { upi: { status: 'missing' }, bank_account: { status: 'missing' }, ifsc: { status: 'missing' }, phone: { status: 'missing' } }, minutes_wasted: 0 });

  // metrics + goal_state tick: minutes wasted tracks the call clock, so it can never contradict the timer
  var END = tt(30) + 3200;
  for (var t = 3000; t <= END; t += 2000) {
    var mins = (t - 2600) / 60000;
    var kt = turns.filter(function (x, i) { return x[0] === 'kamla' && tt(i + 1) + 700 <= t; }).length;
    var f = kt ? Math.min(1, kt / 13) : 0;   // ramps to the live-run end state: dead air 1.2 s, answer 6.2 s (LLM 5.3 + voice 1.7), 39% filler, 13 turns
    add(t, 'metrics', { minutes_wasted: mins, dead_air_p95_ms: kt ? Math.round(1200 * Math.min(1, 0.6 + f)) : 0,
      answer_p95_ms: kt ? Math.round(6200 * Math.min(1, 0.6 + f)) : 0,
      substantive_p95_ms: kt ? Math.round(6200 * Math.min(1, 0.6 + f)) : 0, compute_p95_ms: kt ? Math.round(6200 * Math.min(1, 0.6 + f)) : 0,
      llm_p95_ms: kt ? Math.round(5300 * Math.min(1, 0.6 + f)) : 0, tts_p95_ms: kt ? Math.round(1700 * Math.min(1, 0.6 + f)) : 0,
      filler_rate: kt ? 0.39 : 0, turns: kt ? Math.min(13, kt) : 0, kamla_turns: kt ? Math.min(13, kt) : 0 });
  }
  add(END - 500, 'goal_state', { goals: { upi: { status: 'confirmed' }, bank_account: { status: 'confirmed' }, ifsc: { status: 'confirmed' }, phone: { status: 'confirmed' } }, minutes_wasted: (END - 500 - 2600) / 60000 });
  add(END + 400, 'call_summary', { label: 'simulated call', engaged_s: 172.6, identifiers_verified: 3, identifiers_corrected: 1, drafts: 2, fillers: 5, turns: 13,
    session: { calls_n: 1, engaged_s: 172.6, identifiers_verified: 3, identifiers_corrected: 1, drafts: 2, fillers: 5, turns: 13 } });
  add(0, 'call_status', { call_id: 'mock-001', state: 'ringing', scenario: 'digital_arrest' });
  add(2600, 'call_status', { call_id: 'mock-001', state: 'active', scenario: 'digital_arrest' });
  add(END + 500, 'call_status', { call_id: 'mock-001', state: 'ended', scenario: 'digital_arrest' });
  ev.sort(function (a, b) { return a.t - b.t; });

  window.SaarthiMock = {
    speed: speed,
    stop: function () { timers.forEach(clearTimeout); timers = []; },
    start: function (dispatch) {
      this.stop();
      ev.forEach(function (e) { timers.push(setTimeout(function () { dispatch(e.type, e.d); }, e.t / speed)); });
    }
  };
})();

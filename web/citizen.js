/* Optional enhancement: if a passcode is supplied in the URL fragment (#pc=...), show the scam type when the detector flags one.
   The page is fully usable without any server data; nothing here is required. */
(function () {
  'use strict';
  /* language toggle: Hindi only by default; English on demand; remembered */
  var wrap = document.getElementById('wrap'), lb = document.getElementById('langBtn');
  function setEn(on) { wrap.classList.toggle('show-en', on); lb.setAttribute('aria-pressed', on ? 'true' : 'false'); }
  var saved = null; try { saved = localStorage.getItem('sk_lang'); } catch (e) { /* storage blocked */ }
  setEn(saved === 'en');
  lb.addEventListener('click', function () {
    var on = !wrap.classList.contains('show-en'); setEn(on);
    try { localStorage.setItem('sk_lang', on ? 'en' : 'hi'); } catch (e) { /* ignore */ }
  });
  var msg = 'सावधान! यह ठगी (फ्रॉड) कॉल हो सकती है। पैसे मत भेजिए, कॉल काटिए, 1930 पर कॉल कीजिए. / Scam alert: do not send money, hang up, call 1930. Police/CBI never arrest anyone over a phone or video call.';
  document.getElementById('share').href = 'https://wa.me/?text=' + encodeURIComponent(msg);

  var m = /[#&]pc=([^&]+)/.exec(location.hash);
  if (!m || !window.EventSource) return;
  var pc = decodeURIComponent(m[1]);
  history.replaceState(null, '', location.pathname + location.search);   // keep passcode in memory only
  var PLAIN = { digital_arrest: "Fake CBI / police 'digital arrest'", fake_kyc: 'Fake bank KYC / bank officer', fake_investment: 'Fake investment / trading tips' };
  var es = new EventSource('/api/events?pc=' + encodeURIComponent(pc));
  es.addEventListener('detector', function (ev) {
    try {
      var d = JSON.parse(ev.data), tp = String(d.scam_type || '');
      if (tp && !/^(unknown|none|benign|normal)$/i.test(tp) && Number(d.risk_score != null ? d.risk_score : d.risk) >= 0.67) {
        document.getElementById('ctype').textContent = '— ' + (PLAIN[tp] || tp.replace(/_/g, ' '));
      }
    } catch (e) { /* ignore */ }
  });
  es.onerror = function () { if (es.readyState === 2) es.close(); };   // rejected or gone: stay static
})();

/* Preserve any #fragment (e.g. ?mock) when moving on to the console. */
(function () {
  'use strict';
  if (location.hash) {
    var a = document.getElementById('goConsole'), b = document.getElementById('goCitizen');
    if (a) a.href += location.hash;
    if (b) b.href += location.hash;
  }
})();

/* Utilitas umum: CSRF untuk fetch, konfirmasi hapus, bunyi beep. */
(function () {
  const meta = document.querySelector('meta[name="csrf-token"]');
  window.CSRF = meta ? meta.content : '';

  window.postJSON = async function (url, data) {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': window.CSRF },
      body: JSON.stringify(data),
      credentials: 'same-origin',
    });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    return r.json();
  };

  // Konfirmasi untuk form/tombol berbahaya
  document.addEventListener('submit', function (e) {
    const msg = e.target.getAttribute('data-confirm');
    if (msg && !window.confirm(msg)) e.preventDefault();
  });

  // Auto-submit filter select
  document.querySelectorAll('select[data-autosubmit], input[data-autosubmit]').forEach(function (el) {
    el.addEventListener('change', function () { el.form.submit(); });
  });

  // Bunyi konfirmasi scan (tanpa file audio, bekerja offline)
  let ctx;
  window.beep = function (kind) {
    try {
      ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
      const tones = { success: [880, 0.12], warning: [520, 0.25], error: [220, 0.4] };
      const [freq, dur] = tones[kind] || tones.success;
      const o = ctx.createOscillator();
      const g = ctx.createGain();
      o.frequency.value = freq;
      o.type = 'sine';
      g.gain.value = 0.15;
      o.connect(g); g.connect(ctx.destination);
      o.start();
      o.stop(ctx.currentTime + dur);
      if (kind === 'error' || kind === 'warning') {
        const o2 = ctx.createOscillator();
        o2.frequency.value = freq; o2.connect(g);
        o2.start(ctx.currentTime + dur + 0.08); o2.stop(ctx.currentTime + dur * 2 + 0.08);
      }
    } catch (err) { /* audio tidak tersedia */ }
  };

  window.escapeHtml = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };

  window.avatarHtml = function (s, cls) {
    cls = cls || 'avatar';
    if (s && s.foto) return '<img class="' + cls + '" src="/uploads/' + encodeURI(s.foto) + '" alt="">';
    const n = (s && s.nama ? s.nama : '?').trim().charAt(0).toUpperCase();
    return '<span class="' + cls + '">' + escapeHtml(n) + '</span>';
  };
})();

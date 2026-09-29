/* Scanner kartu serbaguna:
 *  - Reader RFID USB / scanner QR USB (HID): mengetik UID / isi QR ke input lalu Enter
 *  - Kamera HP / webcam lewat browser (html5-qrcode, dimuat lokal, tetap jalan offline)
 *  - Antrean offline: bila koneksi ke server putus, scan disimpan di browser lalu dikirim
 *    otomatis (dengan jam scan asli) begitu koneksi kembali
 *
 * initScanner({ endpoint, extra: () => ({...}), resultEl, inputEl, readerId, historyEl })
 */
function initScanner(opt) {
  const input = opt.inputEl;
  const resultEl = opt.resultEl;
  let busy = false;
  let lastCode = '', lastTime = 0;
  let camera = null;

  function render(res) {
    const lvl = res.level || (res.ok ? 'success' : 'error');
    resultEl.className = 'result ' + lvl;
    const ic = iconHtml({ success: 'ok', warning: 'alert', error: 'err' }[lvl]);
    let html = '';
    if (res.siswa) {
      html += avatarHtml(res.siswa, 'avatar');
      html += '<div class="nama">' + escapeHtml(res.siswa.nama) + '</div>';
      html += '<div class="muted">' + escapeHtml(res.siswa.kelas || '') +
        (res.siswa.nis ? ' · NIS ' + escapeHtml(res.siswa.nis) : '') + '</div>';
    } else {
      html += '<div class="big-ic">' + iconHtml(lvl === 'error' ? 'err' : 'alert') + '</div>';
    }
    html += '<div class="pesan">' + (res.siswa ? ic + ' ' : '') + escapeHtml(res.pesan) + '</div>';
    if (res.jam) html += '<div class="muted">Pukul ' + escapeHtml(res.jam) + '</div>';
    resultEl.innerHTML = html;
    beep(lvl);
    if (opt.historyEl && res.siswa) {
      const li = document.createElement('li');
      li.innerHTML = avatarHtml(res.siswa) + '<div class="grow"><div class="title">' +
        escapeHtml(res.siswa.nama) + '</div><div class="sub">' + escapeHtml(res.siswa.kelas || '') +
        ' · ' + escapeHtml(res.pesan) + '</div></div><span class="muted">' +
        escapeHtml(res.jam || new Date().toTimeString().slice(0, 5)) + '</span>';
      opt.historyEl.prepend(li);
      while (opt.historyEl.children.length > 15) opt.historyEl.lastChild.remove();
    }
  }

  // ---- antrean offline (localStorage)
  const QKEY = 'antrean:' + opt.endpoint;
  const antreanEl = opt.antreanEl || (function () {
    const el = document.createElement('div');
    el.className = 'help antrean';
    input.insertAdjacentElement('afterend', el);
    return el;
  })();
  function bacaAntrean() {
    try { return JSON.parse(localStorage.getItem(QKEY) || '[]'); } catch (e) { return []; }
  }
  function simpanAntrean(q) {
    try { localStorage.setItem(QKEY, JSON.stringify(q)); } catch (e) { /* penyimpanan penuh */ }
    antreanEl.textContent = q.length ? q.length + ' scan tersimpan offline — dikirim otomatis saat koneksi kembali' : '';
    antreanEl.classList.toggle('err-text', q.length > 0);
  }
  let mengirim = false;
  async function kirimAntrean() {
    if (mengirim) return;
    let q = bacaAntrean();
    if (!q.length) return simpanAntrean(q);
    mengirim = true;
    try {
      while (q.length) {
        try {
          const res = await postJSON(opt.endpoint, q[0]);
          if (opt.historyEl && res.siswa) render(Object.assign({}, res, { pesan: res.pesan + ' (offline)' }));
        } catch (e) {
          if (e instanceof TypeError) break;  // masih offline
          // server menjawab error (mis. 500): buang agar antrean tidak macet
        }
        q = bacaAntrean().slice(1);
        simpanAntrean(q);
      }
    } finally {
      mengirim = false;
    }
  }
  simpanAntrean(bacaAntrean());
  window.addEventListener('online', kirimAntrean);
  setInterval(kirimAntrean, 10000);
  kirimAntrean();

  async function submit(code, metode) {
    code = (code || '').trim();
    if (!code || busy) return;
    const now = Date.now();
    if (code === lastCode && now - lastTime < 3000) return; // cegah double-read kamera
    lastCode = code; lastTime = now;
    busy = true;
    const payload = Object.assign({ code: code, metode: metode }, opt.extra ? opt.extra() : {});
    try {
      render(await postJSON(opt.endpoint, payload));
    } catch (e) {
      if (e instanceof TypeError) {
        // jaringan putus: simpan dengan jam scan asli, kirim ulang nanti
        const q = bacaAntrean();
        q.push(Object.assign({ ts: now }, payload));
        simpanAntrean(q);
        render({ ok: true, level: 'warning', pesan: 'Koneksi terputus — scan disimpan dan akan dikirim otomatis' });
      } else {
        render({ ok: false, level: 'error', pesan: 'Gagal menghubungi server: ' + e.message });
      }
    } finally {
      busy = false;
    }
  }

  // ---- scanner fisik / input manual
  input.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') {
      e.preventDefault();
      const v = input.value;
      input.value = '';
      submit(v, 'scanner');
    }
  });
  // Jaga fokus ke input agar scanner USB selalu siap (kecuali user sedang memilih kontrol lain)
  setInterval(function () {
    const a = document.activeElement;
    if (!a || a === document.body) input.focus();
  }, 800);
  input.focus();

  // ---- kamera browser
  const btnStart = document.getElementById('cam-start');
  const btnStop = document.getElementById('cam-stop');
  const camSelect = document.getElementById('cam-select');

  async function loadCameras() {
    if (typeof Html5Qrcode === 'undefined') return [];
    try {
      const cams = await Html5Qrcode.getCameras();
      camSelect.innerHTML = '';
      cams.forEach(function (c, i) {
        const o = document.createElement('option');
        o.value = c.id;
        o.textContent = c.label || ('Kamera ' + (i + 1));
        if (/back|belakang|rear|environment/i.test(c.label)) o.selected = true;
        camSelect.appendChild(o);
      });
      camSelect.hidden = cams.length < 2;
      return cams;
    } catch (e) {
      return [];
    }
  }

  async function startCamera() {
    if (typeof Html5Qrcode === 'undefined') {
      render({ ok: false, level: 'error', pesan: 'Library kamera tidak termuat' });
      return;
    }
    if (!window.isSecureContext && location.hostname !== 'localhost' && location.hostname !== '127.0.0.1') {
      render({ ok: false, level: 'warning', pesan: 'Browser HP hanya mengizinkan kamera lewat HTTPS atau localhost. Lihat README bagian "Kamera HP".' });
    }
    await loadCameras();
    // Kotak kamera harus sudah tampil SEBELUM kamera dinyalakan: html5-qrcode mengukur
    // lebarnya saat start — bila masih tersembunyi, video dibuat selebar 0 px (tak terlihat).
    const reader = document.getElementById(opt.readerId);
    reader.hidden = false;
    camera = camera || new Html5Qrcode(opt.readerId);
    const src = camSelect.value ? camSelect.value : { facingMode: 'environment' };
    const qrbox = function (w, h) {
      const s = Math.max(120, Math.floor(Math.min(w, h) * 0.7));
      return { width: s, height: s };
    };
    try {
      await camera.start(src, { fps: 10, qrbox: qrbox },
        function (text) { submit(text, 'kamera'); }, function () {});
      btnStart.hidden = true; btnStop.hidden = false;
    } catch (e) {
      reader.hidden = true;
      render({ ok: false, level: 'error', pesan: 'Kamera tidak dapat dibuka: ' + e });
    }
  }

  async function stopCamera() {
    if (camera && camera.isScanning) await camera.stop();
    document.getElementById(opt.readerId).hidden = true;
    btnStart.hidden = false; btnStop.hidden = true;
  }

  if (btnStart) btnStart.addEventListener('click', startCamera);
  if (btnStop) btnStop.addEventListener('click', stopCamera);
  if (camSelect) camSelect.addEventListener('change', async function () {
    if (camera && camera.isScanning) { await stopCamera(); startCamera(); }
  });

  return { submit: submit };
}

function startClock(el) {
  function tick() { el.textContent = new Date().toLocaleTimeString('id-ID', { hour12: false }); }
  tick(); setInterval(tick, 1000);
}

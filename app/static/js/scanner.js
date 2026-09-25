/* Scanner QR serbaguna:
 *  - Scanner fisik USB (HID): mengetik isi QR ke input lalu Enter
 *  - Kamera HP / webcam lewat browser (html5-qrcode, dimuat lokal, tetap jalan offline)
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

  async function submit(code, metode) {
    code = (code || '').trim();
    if (!code || busy) return;
    const now = Date.now();
    if (code === lastCode && now - lastTime < 3000) return; // cegah double-read kamera
    lastCode = code; lastTime = now;
    busy = true;
    try {
      const payload = Object.assign({ code: code, metode: metode }, opt.extra ? opt.extra() : {});
      render(await postJSON(opt.endpoint, payload));
    } catch (e) {
      render({ ok: false, level: 'error', pesan: 'Gagal menghubungi server: ' + e.message });
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
    camera = camera || new Html5Qrcode(opt.readerId);
    const src = camSelect.value ? camSelect.value : { facingMode: 'environment' };
    try {
      await camera.start(src, { fps: 10, qrbox: { width: 240, height: 240 } },
        function (text) { submit(text, 'kamera'); }, function () {});
      btnStart.hidden = true; btnStop.hidden = false;
    } catch (e) {
      render({ ok: false, level: 'error', pesan: 'Kamera tidak dapat dibuka: ' + e });
    }
  }

  async function stopCamera() {
    if (camera && camera.isScanning) await camera.stop();
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

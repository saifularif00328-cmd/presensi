/* Layar Gerbang — panel per gerbang/scanner + suara.
 * Dipakai di dua tempat dengan sumber data yang sama bentuknya:
 *  - server : /presensi/layar-gerbang  (ESP32 / scanner per perangkat)
 *  - Presensiku Pos : http://127.0.0.1:8765/  (banyak scanner di satu PC, tetap jalan offline)
 *
 * window.LAYAR = { sumber: 'url feed (GET ?sejak=<id>)', aksi: 'url POST pemetaan scanner' | null,
 *                  jeda: milidetik polling }
 * Respons feed: { sekolah, gerbang: [nama], hadir: {nama: n}, item: [{id, jam, gerbang, level, jenis,
 *   status, pesan, siswa: {nama, kelas, foto} | null, awal}], terakhir, online, antrean,
 *   baru: [{kunci, label, jenis}], pilihan_gerbang: [{id, nama}], peringatan }
 */
(function () {
  'use strict';
  var C = window.LAYAR || {};
  var KUNCI = 'layar-gerbang-v1';
  var set = muat();
  var terakhir = null, panel = {}, urutanPanel = [], gagal = 0, dialogTerbuka = null;
  var el = function (id) { return document.getElementById(id); };

  function muat() {
    var d = { suara: true, modeSuara: 'nama', bisu: [] };
    try { var s = JSON.parse(localStorage.getItem(KUNCI) || '{}'); for (var k in s) d[k] = s[k]; } catch (e) {}
    return d;
  }
  function simpan() { try { localStorage.setItem(KUNCI, JSON.stringify(set)); } catch (e) {} }

  // ------------------------------------------------------------ suara
  var audio = null;
  function nada(frek, mulai, lama, vol) {
    if (!audio) return;
    var o = audio.createOscillator(), g = audio.createGain(), t = audio.currentTime + mulai;
    o.type = 'sine'; o.frequency.value = frek;
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(vol || 0.25, t + 0.01);
    g.gain.exponentialRampToValueAtTime(0.0001, t + lama);
    o.connect(g); g.connect(audio.destination); o.start(t); o.stop(t + lama + 0.02);
  }
  function bip(level) {
    if (level === 'success') nada(1046, 0, 0.14);
    else if (level === 'warning') { nada(784, 0, 0.12); nada(784, 0.18, 0.12); }
    else if (level === 'info') nada(1318, 0, 0.06, 0.12);
    else { nada(220, 0, 0.35, 0.3); nada(196, 0.4, 0.35, 0.3); }
  }
  var suaraId = null;
  function pilihSuara() {
    if (!window.speechSynthesis) return;
    var v = speechSynthesis.getVoices();
    suaraId = v.filter(function (x) { return /^id/i.test(x.lang); })[0] || null;
  }
  if (window.speechSynthesis) { pilihSuara(); speechSynthesis.onvoiceschanged = pilihSuara; }
  function ucap(it) {
    if (!window.speechSynthesis || !it.siswa) return false;
    var depan = (it.siswa.nama || '').split(' ')[0];
    var kata = it.level === 'error' ? 'ditolak'
      : it.jenis === 'ganda' ? '' : it.jenis === 'tersimpan' ? 'tercatat' : it.status === 'Telat' ? 'telat'
      : it.jenis === 'pulang' ? 'pulang' : it.jenis === 'peringatan' ? 'sudah absen' : 'hadir';
    if (!kata) return false;
    var u = new SpeechSynthesisUtterance(depan + ', ' + kata);
    u.lang = 'id-ID'; if (suaraId) u.voice = suaraId; u.rate = 1.05;
    speechSynthesis.speak(u);
    return true;
  }
  function bunyikan(it) {
    if (!set.suara || set.bisu.indexOf(it.gerbang || '') >= 0) return;
    bip(it.level);
    if (set.modeSuara === 'nama' && it.level !== 'info') setTimeout(function () { ucap(it); }, 180);
  }

  // ------------------------------------------------------------ panel
  function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
  function inisial(n) { return (n || '?').split(' ').slice(0, 2).map(function (x) { return x[0] || ''; }).join('').toUpperCase(); }
  function label(it) {
    if (it.level === 'error') return 'DITOLAK';
    if (it.jenis === 'ganda') return 'SUDAH TERCATAT';
    if (it.jenis === 'tersimpan') return it.siswa ? 'TERSIMPAN' : 'BELUM DIKENAL';
    if (it.jenis === 'peringatan' || it.jenis === 'ulang') return 'SUDAH ABSEN';
    if (it.status === 'Telat') return 'TELAT';
    if (it.status === 'Pulang Cepat') return 'PULANG CEPAT';
    return it.jenis === 'pulang' ? 'PULANG' : 'HADIR';
  }

  function pastikanPanel(nama) {
    if (panel[nama]) return panel[nama];
    var p = document.createElement('section');
    p.className = 'pnl';
    p.innerHTML = '<header><h2></h2><span class="hitung"></span><button class="bisu" title="Suara gerbang ini"></button></header>' +
      '<div class="utama kosong"><div class="foto"></div><div class="ket"><div class="nama">Menunggu scan…</div>' +
      '<div class="kelas"></div><div class="lbl"></div><div class="psn"></div></div><div class="jam"></div></div><ol class="riwayat"></ol>';
    p.querySelector('h2').textContent = nama || 'Lainnya';
    p.querySelector('.bisu').addEventListener('click', function () {
      var i = set.bisu.indexOf(nama);
      if (i >= 0) set.bisu.splice(i, 1); else set.bisu.push(nama);
      simpan(); tombolBisu();
    });
    el('panel').appendChild(p);
    panel[nama] = { el: p, riwayat: [] };
    urutanPanel.push(nama);
    aturGrid(); tombolBisu();
    return panel[nama];
  }
  function aturGrid() {
    var n = urutanPanel.length, kolom = n <= 1 ? 1 : n === 2 ? 2 : n === 3 ? 3 : n === 4 ? 2 : 3;
    el('panel').style.gridTemplateColumns = 'repeat(' + kolom + ', minmax(0, 1fr))';
    el('panel').dataset.jumlah = n;
  }
  function tombolBisu() {
    Object.keys(panel).forEach(function (n) {
      var b = panel[n].el.querySelector('.bisu'), mati = !set.suara || set.bisu.indexOf(n) >= 0;
      b.textContent = mati ? '🔇' : '🔊'; b.classList.toggle('mati', mati);
    });
    el('t-suara').textContent = set.suara ? '🔊 Suara' : '🔇 Bisu';
    el('t-mode').textContent = set.modeSuara === 'nama' ? 'Sebut nama' : 'Bip saja';
  }

  function tampil(it) {
    var p = pastikanPanel(it.gerbang || '');
    var u = p.el.querySelector('.utama');
    u.className = 'utama lv-' + (it.level || 'info');
    var s = it.siswa;
    u.querySelector('.foto').innerHTML = s && s.foto ? '<img alt="" src="' + esc(s.foto) + '">' : '<span>' + esc(inisial(s ? s.nama : '!')) + '</span>';
    u.querySelector('.nama').textContent = s ? s.nama : 'Kartu tidak dikenali';
    u.querySelector('.kelas').textContent = s ? s.kelas : '';
    u.querySelector('.lbl').textContent = label(it);
    u.querySelector('.psn').textContent = it.pesan || '';
    u.querySelector('.jam').textContent = (it.jam || '').slice(0, 5);
    if (!it.awal) { u.classList.remove('kilat'); void u.offsetWidth; u.classList.add('kilat'); }
    p.riwayat.unshift(it);
    p.riwayat = p.riwayat.slice(0, 6);
    p.el.querySelector('.riwayat').innerHTML = p.riwayat.slice(1).map(function (r) {
      return '<li class="lv-' + esc(r.level) + '"><b>' + esc((r.jam || '').slice(0, 5)) + '</b> ' +
        esc(r.siswa ? r.siswa.nama : 'Tidak dikenali') + ' <span>' + esc(label(r)) + '</span></li>';
    }).join('');
  }

  // ------------------------------------------------------------ scanner baru (khusus Pos)
  function tanyaScanner(baru, pilihan) {
    if (!C.aksi || !baru || !baru.length) { tutupDialog(); return; }
    var sc = baru[0];
    if (dialogTerbuka === sc.kunci) return;
    dialogTerbuka = sc.kunci;
    var d = el('dialog');
    d.querySelector('.sc-label').textContent = sc.label || sc.kunci;
    d.querySelector('.sc-jenis').textContent = sc.jenis === 'com' ? 'port COM' : 'USB';
    var wadah = d.querySelector('.pilihan');
    wadah.innerHTML = '';
    (pilihan || []).forEach(function (g) {
      var b = document.createElement('button');
      b.textContent = g.nama; b.className = 'pilih';
      b.onclick = function () { kirimPeta({ kunci: sc.kunci, gerbang_id: g.id }); };
      wadah.appendChild(b);
    });
    if (!(pilihan || []).length) wadah.innerHTML = '<p>Belum ada gerbang. Tambahkan di menu <b>Perangkat Scan</b> aplikasi sekolah, lalu tunggu sebentar.</p>';
    d.querySelector('.abaikan').onclick = function () { kirimPeta({ kunci: sc.kunci, abaikan: true }); };
    d.hidden = false;
  }
  function tutupDialog() { el('dialog').hidden = true; dialogTerbuka = null; }
  function kirimPeta(data) {
    fetch(C.aksi, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
      .then(function (r) { return r.json(); })
      .then(function (r) { if (!r.ok) alert(r.pesan || 'Gagal menyimpan'); tutupDialog(); })
      .catch(function () { alert('Gagal menghubungi Presensiku Pos'); });
  }

  // ------------------------------------------------------------ polling
  function ambil() {
    var url = C.sumber + (terakhir !== null ? (C.sumber.indexOf('?') < 0 ? '?' : '&') + 'sejak=' + terakhir : '');
    fetch(url, { cache: 'no-store', credentials: 'same-origin' })
      .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(function (d) {
        gagal = 0;
        el('sekolah').textContent = d.sekolah || '';
        (d.gerbang || []).forEach(pastikanPanel);
        (d.item || []).forEach(function (it) { tampil(it); if (!it.awal) bunyikan(it); });
        Object.keys(panel).forEach(function (n) {
          var h = (d.hadir || {})[n];
          panel[n].el.querySelector('.hitung').textContent = h ? h + ' hadir' : '';
        });
        terakhir = d.terakhir != null ? d.terakhir : terakhir;
        status(d.online !== false, d.antrean || 0, d.peringatan);
        tanyaScanner(d.baru, d.pilihan_gerbang);
        if (!urutanPanel.length) pastikanPanel('');
      })
      .catch(function () { gagal++; status(false, null, gagal > 2 ? 'Layar tidak terhubung ke sumber data' : ''); })
      .then(function () { setTimeout(ambil, C.jeda || 1500); });
  }
  function status(online, antrean, peringatan) {
    var s = el('status');
    s.className = 'status ' + (online ? 'on' : 'off');
    s.textContent = online ? (antrean ? 'Online · ' + antrean + ' scan dikirim…' : 'Online')
      : 'Offline' + (antrean ? ' · ' + antrean + ' scan tersimpan' : '');
    el('peringatan').textContent = peringatan || '';
    el('peringatan').hidden = !peringatan;
  }
  setInterval(function () {
    var d = new Date();
    el('jam').textContent = ('0' + d.getHours()).slice(-2) + ':' + ('0' + d.getMinutes()).slice(-2) + ':' + ('0' + d.getSeconds()).slice(-2);
  }, 1000);

  // ------------------------------------------------------------ kontrol
  el('t-suara').onclick = function () { set.suara = !set.suara; simpan(); tombolBisu(); };
  el('t-mode').onclick = function () { set.modeSuara = set.modeSuara === 'nama' ? 'bip' : 'nama'; simpan(); tombolBisu(); };
  el('t-layar').onclick = function () {
    if (document.fullscreenElement) document.exitFullscreen(); else document.documentElement.requestFullscreen().catch(function () {});
  };
  el('mulai').onclick = function () {
    try { audio = new (window.AudioContext || window.webkitAudioContext)(); } catch (e) {}
    el('mulai').hidden = true;
    if (set.suara) bip('success');
  };
  tombolBisu();
  ambil();
})();

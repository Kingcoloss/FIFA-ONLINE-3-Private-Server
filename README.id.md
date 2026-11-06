# FO3ID Private Server

[English](README.md) | **Bahasa Indonesia** | [简体中文](README.zh-CN.md) | [ไทย](README.th.md) | [Tiếng Việt](README.vi.md) | [한국어](README.ko.md)

> Terjemahan dari [README.md](README.md). Kalau ada yang berbeda, README.md yang terbaru.

Private server lokal untuk **FIFA Online 3 Indonesia** (Garena, client build 654420), ditulis
dengan Python. Garena menutup server resminya pada 2020-06-30; proyek ini membuat ulang backend
yang diajak bicara oleh client, jadi game bisa dimainkan offline di satu PC.

> Tidak berafiliasi dengan EA, Spearhead, atau Garena. Repositori ini **tidak berisi file game**
> (tanpa client, database, aset, atau musik), jadi kamu perlu instalasi FO3 ID sendiri. Proyek ini
> **tidak** menyertakan, mengubah, atau mengakali anti-cheat client (XIGNCODE3 / HackShield); itu
> di luar cakupan. Dibuat untuk pelestarian game dan riset.

## Yang sudah jalan

Diuji di client asli (UI bahasa Indonesia):

- Login → pilih / buat manager (pemilih klub dari 501 klub berlisensi) → lobi (FREEROAM).
- **Single → Liga** (satu musim penuh: kalender, pertandingan, klasemen, hadiah, promosi) dan
  **Cup** (undian, grup, gugur, perpanjangan waktu, adu penalti).
- **Market** (beli / jual; harga kartu mengikuti rating dan grade-nya: median harga fifaaddict
  semua kartu dengan rating itu), **Upgrade** (grade +1…+10), trade pemain **Tukar** dan
  **Tukar Scout** (semua kartu Market, bukan hanya yang berlisensi di region ini), Tim inti /
  Tim Cadangan, simpan skuad dan taktik.
- **Shop** dengan semua tab (pak pemain, item konsumsi, paket, MP Shop, paket bulanan dan paket
  berantai, bonus spesial), buka pak dengan grade acak, Item saya, Bag, hadiah login harian.
  **Gudang** (Item saya > Gudang): pindahkan pak dan item konsumsi ke sana dan kembali.
  Pak tambahan: **All Season +8** (musim apa saja, +1…+8) dan satu pak untuk '07 serta tiap
  musim yang ada di fifaaddict.
- Selalu VIP + benefit warnet resmi (IGR), hapus / pulihkan manager, kartu musim '17.
- Daftar formasi (formasi klub sendiri + 33 formasi umum game, dibaca dari tabel formasi client)
  dan level manager / pemain: EXP setelah tiap pertandingan, pemain LV.1-23 (+1 ke semua atribut
  per level), manager LV.1-100.
- Suara game dan musik menu EA Trax. `tools/eatrax_song.py` menaruh lagumu sendiri di urutan
  pertama, tapi game lalu crash setelah pertandingan (lihat masalah yang diketahui di bawah).
- Halaman admin web di http://127.0.0.1:8088/ (EP, pemain, pak, hadiah, hadiah harian, hadiah match, Shop, log)
  dengan pilihan bahasa (issue #15): Bahasa Indonesia, English, 简体中文, ไทย, Tiếng Việt, 한국어;
  browser mengingat pilihannya.
- Jersey klub asli di pertandingan (kit id = `teamid << 5 | type`; `<< 10` yang lama menghasilkan
  papan catur).
- Pertandingan berjalan sampai babak kedua dengan **team color** aktif (dulu warna musim membuatnya
  crash saat turun minum), lalu menampilkan layar EXP dan hadiah.

Sudah ditambahkan dan lolos tes, tapi belum dicek di client:

- Bonus **team color** itu sendiri: starting XI mendapat bonus OVR untuk pemain dari klub yang sama
  (4-5 pemain +1 sampai 10-11 +4), negara atau musim yang sama (5-6 +1 sampai 9-11 +3); per pemain
  hanya yang terbaik yang dihitung.
- **Opsi > Kontrol** (tombol keyboard dan gamepad) tersimpan: server selalu mengirim susunan tombol
  bawaan game, jadi layar itu bisa menerapkan dan menyimpan perubahan (dulu perubahan hilang).
- **Pilihan kit** di layar pengaturan pertandingan (kandang / tandang per sisi) dipakai di
  pertandingan.
- **Pilih manager** menampilkan pemain paling mahal klub dengan kit klub (dulu menampilkan pemain
  Barcelona bawaan game).
- Crash yang diperbaiki: popup pengumuman saat mulai (URL web kosong), tutorial liga Beginner's
  Guide (script tidak ada).
- **Peluang upgrade**: peluang dasar per grade tujuan, dikali label "Rasio bonus keberhasilan" yang
  ditampilkan tab Upgrade dari grade bahan (Kosong x1, Low x1.1, Normal x1.25, High x1.5). Upgrade
  yang gagal dari +5 ke atas turun satu grade.
- **Pak Top 200**: pak tambahan sekarang memberi 200 kartu terbaik musimnya ("17 Top 200",
  "07 Top 200", …); **All Season Top 300 +8** memberi kartu musim apa saja dengan rating 81 ke atas.
- **Upgrade dengan kartu +0** (issue #5): kartu +0 milik klub menjaga grade tujuan di 100%
  (+4 dengan +0 tetap +4) dan kartu +10 juga bisa memakainya; kartu yang dipertahankan keluar dari
  Tim Cadangan saat mengambil slot skuad kartu yang dipakai.
- **Upgrade 2.5** (layar Upgrade client yang lebih baru, `features...enhancement.v2_5`):
  - **poin upgrade**: upgrade yang gagal memberi poin; "Gunakan poin" memakainya untuk +10%;
    beli lagi gratis di Shop > Paket (Upgrade Point 100 / 500 / 1.000);
  - **item boost** Enhancement Boost Gold / Silver / Bronze (+15 / +10 / +5%), gratis di
    Shop > Dapat dikonsumsi;
  - **event upgrade** permanen (+10% untuk tujuan +1…+9, `GET /events`);
  - "Coba pengembalian lagi" mengembalikan grade yang hilang karena gagal, dengan poin.
- **Tukar v2** (`trade2`): trade dinilai dari nilainya (TP) dalam 15 level, masing-masing dengan
  grade tawaran maksimum; tab menampilkan apa yang didapat manager lain "kemarin" di level itu;
  kartu musim legenda dihitung 1.5x; tanpa batas harian atau nilai. Tukar Scout tetap jalan di
  sampingnya.
- **Tukar Scout**: dua scout lain dari client, Scout Khusus (event; quest musim legenda) dan
  VVIP Scout (tawaran terbaik; quest 1 miliar EP). Scout Amatir dihapus agar daftar pas di 5 baris
  (dulu saat daftar bisa di-scroll, quest yang terpenuhi menyalakan kartu scout lain atau tidak
  sama sekali).
- **Team color upgrade** ("Upgraded Team" di client): starter dengan grade +2, +5, atau +8 ke
  atas; 5-6 / 7-8 / 9-11 pemain memberi +1 / +2 / +3, +2 / +3 / +4 dan +3 / +4 / +5 OVR. Yang
  satu-grade ("+3 club" … "+10 Golden summit") butuh ke-11 starter di grade itu atau lebih:
  +4 (club +3/+4), +5 (silver +5…+7), +6 (Golden passion +8/+9), +7 (Golden summit +10). Pemain
  mendapat warna upgrade terbaiknya di atas warna klub / negara / musim terbaiknya.
- **Semua team color yang ada namanya di client** (sekarang 188):
  - 27 klub (Real Madrid … Jeonbuk): tingkatan Single team ditambah boost khusus klub dari
    tooltip game, mis. Barcelona MF agility +3;
  - 30 negara: tingkatan Satu Negara ditambah mis. Spanyol MF ball control +2;
  - warna musim dengan nama dari game (World Best sampai +5, World Legend, 2014 WC All-Star, …);
  - sekitar 75 spesial: '14 WC dan EC per negara, nation BEST, MSN / BBC Trio, Arsenal
    Invincibles, Galácticos, LEGENDS, TOP 100, Power Header, New Star, ….

  Boost dan daftar pemain aslinya adalah data server dan sudah hilang. Daftar pemain diambil dari
  database pemain (musim, klub, pemain yang disebut namanya, batas stat); boost dari satu baris
  tooltip yang masih ada di game. Tidak dimasukkan: warna [Test], "+2~7", "14 WC Single Nation"
  dan empat entri klub ganda.
- **Formasi** tidak lagi terbuka dengan "Tidak cukup pemain" (layar itu memuat preset skuad 1,
  yang tidak pernah dikirim server). Lubang di XI (issue #7, upgrade dua starter dari satu pemain)
  diisi dari bangku cadangan, dan bangku cadangan tidak pernah berisi kartu kedua dari satu pemain.
  Tiap starter mendapat data `starting`-nya (workrate dan posisi di lapangan): tanpa itu game
  menampilkannya di bangku cadangan.
- **Tim > Peran** menyimpan kapten dan tiap eksekutor bola mati (issue #8:
  `PUT /game/my/team/captain` dan `/game/my/team/kickers/<0-4>` belum ada). Lima slot eksekutor
  (sepak pojok kiri, sepak pojok kanan, tendangan bebas, penalti, tendangan bebas 2) tetap di
  tempatnya; slot kosong diisi seorang starter.
- **Tim > Locker room** jalan (issue #13): model dan lengan jersey, tato, gelang, sarung tangan
  (kiper: 39 desain sarung tangan), kaus kaki, pelindung lutut, 614 sepatu per merek, dan nomor
  punggung (mengambil nomor menukarnya dengan pemakainya). Tabel item
  `/static/db/LOCKERROOMITEM` belum ada, jadi semua daftar kosong dan panel sepatu rusak.
  Tampilan pemain disimpan di kartunya, dan Item saya berisi tiket locker room permanen, yang
  dibutuhkan game untuk menampilkan tampilan itu di pertandingan. Hanya model gelang, sarung
  tangan, dan pelindung lutut milik client yang ditawarkan (masing-masing satu).
- **Kontrol Shop di halaman admin** (issue #10): semua tab Shop (pak pemain, item konsumsi, paket,
  paket bulanan, Rekomendasi, MP Shop, Bonus spesial, paket berantai). Pak baru (menurut musim,
  top N, OVR, grade maks., posisi, liga), kotak acak, kartu EP, paket dan paket bulanan, dengan
  ikon mana saja dari 147 ikon shop client. Produk bawaan bisa diubah, disembunyikan, atau diberi
  harga tetap, dan seluruh Shop bisa dibuat gratis atau tidak. Perubahan masuk ke
  `gamedata/shop.json`.
- Kupon **Simulasi Liga** (item 2001, Shop > Dapat dikonsumsi): tombol Simulasi di Liga memberi
  hasil pertandingan tanpa bermain, satu kupon per pertandingan. Layar simulasi memutar gol,
  tembakan, penyelamatan, dan kartu pertandingan sesuai hasilnya (`eventlist` kosong, jadi tampil
  0-0), dan layar hasil setelahnya menampilkan skor, rating dan statistik pemain, penguasaan bola,
  dan MOTM (dulu kosong), lalu hadiah EP dan kembali ke menu Liga. Tombol itu menghitung kupon di
  Item saya dan tetap mati karena itemnya belum ada. Kupon baru bisa dibuat di halaman admin
  (jenis "Kupon Simulasi Liga").
- **Layar skuad sebelum pertandingan** (Liga dan Cup, issue #16): tukar posisi, pergantian pemain,
  dan perubahan formasi sekarang bertahan dan tersimpan ke klub (`PUT /match/<id>/side/<side>/squad`
  belum punya handler, jadi tiap perubahan batal sendiri). Daftar formasi terisi, dan bar stamina
  tampil penuh (kelelahan tidak disimpan antar pertandingan).
- **Rating FW / MF / DF tim sesuai pemainnya** (issue #18): di layar skuad dan lobi, nilainya rata-rata
  rating yang tampil di daftar pemain (rating di posisi pemain ditambah grade upgrade, level, dan team
  color). Dulu dihitung dari rating kartu saja, sekitar 12 lebih rendah.
- **Tab Rekor liga** (issue #19): tabel klasemen tampil (tab-nya error karena tabel `league2difficulty`
  tidak ada; tabel itu sekarang juga menentukan siapa naik atau turun di akhir musim). Rekorku
  menampilkan pertandingan, rating, gol, assist, umpan, tekel, dan penyelamatan tiap pemain dari
  pertandingan musim ini yang dimainkan, dan Rekor gabungan menampilkan best XI dan pemimpin statistik
  musim ini. Hanya pemain sendiri yang dihitung, dan pertandingan simulasi tidak menambah statistik pemain.
- **Squad A / B / C di Formasi** (issue #20): kotak di kiri tombol formasi memilih satu dari tiga
  squad tersimpan (dulu kosong karena server tidak mengirim jumlah squad). Tiap squad menyimpan XI,
  formasi, dan perannya sendiri.
- **Setelan kontroler dan kamera tetap berlaku di match** (issue #21): setelah Opsi > Konfirmasi,
  game membaca opsi tersimpan dari balasan server, yang dulu kosong, jadi tiap match kembali ke opsi
  saat login (keyboard, kamera lama). Di match, F3-F9 mengganti kamera (F5 = Co-op).
- **Ganti tim menampilkan klub dan pemainmu** (issue #23): layar klub item ini sekarang menampilkan
  liga, rival, stadion, tahun dibangun, dan kapasitas, serta pemainmu dengan seragam klub baru beserta
  tanggal lahir, tinggi, dan berat. Info klub dari server dulu tidak memuat semua itu, dan tanpa
  seragam pemain 3D tidak pernah digambar.
- **Tinggi dan zoom kamera bisa diatur** (issue #24): di Opsi > Kamera setting, gauge Customise (tinggi dan
  zoom; zoom, kecepatan, dan ayunan untuk kamera Pro) dulu kosong dan tidak bisa diubah karena
  server mengirim setelan kamera kosong. Sekarang mulai dari 10 (dari 20).
- **Semua timnas ada di Tim lain** (issue #24): liga Internasional (negara terakhir di daftar) berisi
  40 timnas, termasuk Italia, Inggris, Jerman, Spanyol, dan Prancis. Skuad timnas diambil dari
  tautan timnas tiap pemain; dulu hanya timnas yang pemainnya tanpa klub berlisensi yang muncul.
- **Posisi pemain di layar hasil** (issue #26): setelah match, lapangan di layar hasil menumpuk semua
  pemain di gawang karena game melaporkan semua pemain sebagai kiper. Sekarang server memberi tiap
  pemain posisi slot squad-nya.
- **Kartu hadiah setelah match** (issue #26): kartu di layar hadiah dulu kosong. Sekarang ada tiga
  kartu: kartu yang kamu pilih berisi EP (1.000 sampai 10.000), pack pemain (Semua Pemain atau
  '14 Top 200) atau item Lucky EP, dan dua kartu lainnya menunjukkan hadiah yang bisa didapat.
- **Pak draft dan EXP capsule** (issue #27): Shop > Pak pemain menjual pak draft ("06 Draft Pick 3",
  "2017 Draft Pick 5", "World Legend Draft Pick 3"). "Gunakan" membuka layar pilih pemain, terisi kartu
  termahal musim itu; pilih N kartu musim itu (cari nama, liga atau klub) dan salah satunya yang dibuka.
  Shop > Dapat dikonsumsi menjual EXP capsule (1.000, 5.000, Max = LV.23, satu untuk LV.10 ke bawah,
  satu untuk kartu 2017): pilih pemain, dia dapat EXP-nya. Request layar draft
  (`/item/draftpack/<id>/players/<n>`, `/transfer/price/default/<grade>`) dan jenis item capsule belum
  ada. Admin page bisa membuat lagi keduanya (isian "Draft" di pak, jenis item "EXP Capsule").
- **Kotak acak bisa dibuka** (Kotak Platinum dan lainnya, issue #12): layar kotak menampilkan
  hadiahnya dari `staticdata.availables`, yang belum ada, jadi tiap kotak gagal saat "Gunakan".
- **Kartu baru masuk Tim Cadangan**: kartu dari pak, trade, Market, Bag, atau halaman admin tampil
  "-" di kolom Tim pada Skuad, siap untuk Tukar Scout. Tombolnya memindahkan kartu ke Tim inti (RES
  hijau: Tim inti di luar 18 pemain skuad), yang bisa menampung seluruh klub (200). Halaman admin bisa
  memindahkan semua kartu Tim Cadangan ke Tim inti sekaligus.
- **Pencarian Market** menemukan kartu dari semua musim: game hanya mencari musim di
  `/static/roster`, yang tidak punya 29 musim dengan kartu Market (World Legend, World Best,
  '14 TOTS, …), jadi mis. WL R. Gullit tidak pernah muncul. Daftar musim di filter Market jalan
  (issue #14: memilih musim memunculkan "cannot convert 39 to Array", karena `value` tiap musim
  harus berupa list) dan menampilkan nama musim dari client (World Legend, 02 Chinese Legend, …).
- **Semua kartu yang bisa diperdagangkan** ada di Market, di trade, dan di pak: kartu dihitung
  kalau fifaaddict mencantumkannya atau game sendiri menandainya bisa diperdagangkan
  (`permid.transferable`). fifaaddict saja melewatkan 6.599 kartu (4.313 di antaranya '17);
  Market sekarang berisi 44.703. Pak baru **Semua Pemain** bisa memberi kartu mana saja di
  antaranya.
- **Tim > Klub > Informasi tim** (issue #9) menampilkan tanggal mulai, stadion kandang, dan
  "tahun dibangun / kapasitas" (`coach.career`, `coach.stadium`, `GET /stadium/<id>` dari tabel
  stadion client), dan panel pemainnya (stepper, pemain 3D, harga, grade), yang tetap kosong tanpa
  stadion. Nama dari database client dibaca sebagai UTF-8 (`tools/re/eadb.py` membacanya latin-1).
- **Cahaya saat buka pak** mengikuti nilai kartu: tidak ada di bawah 10 juta EP, lalu level 1-3
  mulai 10 juta, 100 juta, dan 1 miliar EP.

Masalah yang diketahui, belum terpecahkan: dengan lagu EA Trax sendiri yang dipasang
`tools/eatrax_song.py`, game kehabisan memory pool RAssets setelah tiap pertandingan, saat layar Cup
atau lobi dimuat lagi (crash di `FifaRNA::Crowd::PlacementData::Seats[]`); dengan musik bawaan game
tidak. Crash yang sama terjadi dengan lagu sebagai PCM mentah (37,7 MB), sebagai EALayer3 (6,5 MB,
`tools/re/ealayer3.py`) yang ditambahkan sebagai track ke-10, dan sebagai EALayer3 yang mengganti
TrackID 1 dengan bank musik lebih kecil dari aslinya, jadi ukuran musik bukan penyebabnya. Pakai
musik bawaan game: `python -I tools/eatrax_song.py --restore` mengembalikannya.

Belum dikerjakan: mode online (ranked, friendly, King of the Hill), Road to World, simulasi liga.

## Kebutuhan

- Windows, Python 3.12, `pip install cryptography` (messenger + ekstraksi DB).
- Instalasi client FO3 ID (path bawaan `D:\FO3ID\32795`; kalau di tempat lain, isi `FO3_GAME`
  dengan foldernya; server memberi peringatan saat mulai kalau cache gambar client tidak
  ditemukan di sana).
- Opsional: ffmpeg (hanya untuk `tools/eatrax_song.py`).

## Pemasangan

1. Ekstrak database pemain dari client-mu:
   `python extract_fifadb.py D:\FO3ID\32795` → `gamedata/fifadb.sqlite`.
2. Harga market opsional: `python tools/fa_sync.py` → `gamedata/fa_prices.json` (scraper
   fifaaddict.com yang sopan; tanpanya harga dihitung dari rumus rating).
3. Sertifikat TLS untuk host API client yang di-hardcode, `APSEODESK172` (self-signed diterima):

   ```
   openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=APSEODESK172" -addext "subjectAltName=DNS:APSEODESK172" -keyout key.pem -out cert.pem
   python -c "open('certs/server.pem','w').write(open('cert.pem').read()+open('key.pem').read())"
   ```

4. File hosts (sebagai admin): `127.0.0.1 APSEODESK172`.
5. Build launcher sekali (`launcher/fifalauncher.cs`, baris build ada di dalamnya), lalu klik dua
   kali **`play.bat`**: file itu membuka jendela server (`python start_all.py` = `http_config.py 443
   --tls` + `messenger.py`; tutup jendela itu untuk menghentikan server) dan menjalankan game tanpa
   prompt UAC.

6. Atau manual: `python start_all.py`, lalu jalankan client dengan argumen server (yang dikirim
   `launcher/fifalauncher.exe` dan `launch_game.ps1`):

   ```
   fifazf.exe -QUICKMATCH/SERVER=127.0.0.1:28000 -QUICKMATCH/PROTOCOL=tcp -QUICKMATCH/NOTISERVER=127.0.0.1:28001 -FIFA/LAUNCHER/PID=<pid> -PUBLISHER/GARENA/TOKEN=testtoken -LOCALE/PUBLISHING_REGION=ID -DUMPTRUCK/SERVER=127.0.0.1 region id token testtoken
   ```

## File

| File | Fungsi |
|---|---|
| `http_config.py` | Backend REST yang dipanggil client (`https://APSEODESK172`): login, akun, manager, pembuatan klub, skuad, liga, cup, market, upgrade, trade, shop, item, Bag, hadiah harian, tabel statis, dan `/cdn/` (menyajikan logo dan kartu dari `_cache` milik client). State disimpan di `gamedata/state.json`. Env: `FO3_LANGUAGE` (bawaan `ind`), `FO3_GAME` (folder client), `FO3_ASSETS`, `FO3_HALF_LENGTH`, `FO3_ADMIN_PORT`. |
| `messenger.py` | Server notifikasi di `:28002`. Frame `<u16 LE len><u16 type=2><Blowfish-CBC(key "kueec", IV 0) of JSON+"\n">`; menjawab `auth`, `ping`, `signon`. `python messenger.py --selftest`. |
| `admin.py` + `admin/index.html` | Halaman admin (dijalankan `http_config.py`, hanya localhost, tanpa password). Tab Shop-nya menyimpan ke `gamedata/shop.json`. Semua kata di halaman itu, termasuk pesan error, ada di tabel `I18N` di akhir `admin.py`, satu per bahasa; bahasa baru cukup satu tabel lagi, dan `python admin.py` mengecek bahwa semua tabel punya key yang sama. |
| `responses/` | Body JSON per endpoint (`/a/b/c` → `responses/a_b_c.json`, dibaca ulang tiap request). Bentuknya diambil dari kode AS3 client. |
| `extract_fifadb.py` | DB pemain client (`data_0.big`, RefPack + Blowfish) → SQLite. |
| `gen_teams.py` | Skuad awal dan ringkasan klub dari `gamedata/fifadb.sqlite`. |
| `tools/eatrax_song.py` | Menaruh lagu di urutan pertama musik menu EA Trax sebagai EALayer3, mengganti TrackID 1 (mengubah `data_0.big` / `data_1.big` dengan menambahkan di akhir; `--restore` mengembalikan aslinya). Membuat game crash setelah pertandingan, lihat masalah yang diketahui. |
| `tools/fa_sync.py` | Sinkronisasi harga fifaaddict.com. |
| `tools/fa_faces.py` | Menambahkan wajah mini pemain yang tidak ada di cache client (fifaaddict menyajikan PNG 128x128 yang sama); `--crests` menambahkan logo klub yang tidak ada (kebanyakan klub tidak punya di cache, jadi game menampilkan logo bawaan). Bisa dilanjutkan, `--remove` membatalkannya. |
| `tools/re/` | Alat bantu reverse engineering: `bigdir.py` (tabel arsip BIg4), `refpack.py` (codec RefPack), `eadb.py` (tabel database "DB" EA), `abc*.py` (parser / grep / penambang skema bytecode AS3), `gfxx.py` (SWF UI), `memgrab.py`, `gamectl.ps1` (mengendalikan jendela client untuk tes). |
| `blaze.py`, `server.py`, `test_client.py`, `analyze_capture.py` | Framing EA Blaze (Fire/TDF) dan server tes loopback dari fase pertama proyek; ternyata client memakai REST + messenger. |
| `analysis/` | Script analisis client awal (string, section PE, endpoint jaringan). |
| `FO3ID-private-server.md`, `reports/` | Temuan dan laporan progres (`reports/` dalam bahasa Indonesia). |

## Tes

```
python run_tests.py
```

Menjalankan self-test Blaze/loopback dan `test_league.py`, yang menjalankan semua fitur backend
(pembuatan klub, liga, cup, market, upgrade, trade, shop, hadiah harian, API admin, hapus manager)
pada akun baru. Butuh `gamedata/fifadb.sqlite`.

## Kontributor

- **SoloPlayer** — pemilik proyek, menguji di client asli.
- **Claude** (asisten AI Anthropic, lewat Claude Code) — reverse engineering dan sebagian besar
  kode server, ditulis bersama pemilik.

## Lisensi

[GNU GPL v3](LICENSE) untuk kode dan dokumentasi di repositori ini. FIFA Online 3, client, data,
aset, dan musiknya milik pemiliknya masing-masing dan tidak termasuk.

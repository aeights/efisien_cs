# Production Integrations — Gmail SMTP + Google Calendar + WhatsApp (WAHA) — Design Spec

**Date:** 2026-06-12
**Status:** Approved (design phase)
**Goal:** Mengganti integrasi console/lokal dengan layanan nyata (kirim email via Gmail SMTP, kelola jadwal via Google Calendar) dan menambah **channel WhatsApp** via WAHA sehingga klien bisa chat dengan agen lewat WhatsApp.

Satu milestone, tiga slice independen di balik interface yang sudah ada (`EmailAdapter`, `CalendarAdapter`) + satu channel baru. Core agent (orchestrator/tools) sudah channel-agnostic dan provider-agnostic, jadi perubahan terlokalisasi pada `integrations/`, `api/`, config, dan Compose.

## 1. Slice A — Gmail SMTP (`EmailAdapter`)

- **`SmtpEmail(EmailAdapter)`** di `app/integrations/email.py`:
  - `__init__(self, host, port, user, password, sender, smtp_factory=smtplib.SMTP)` — `smtp_factory` disuntik agar bisa di-test tanpa jaringan.
  - `send(to, subject, body)`: bangun `email.message.EmailMessage` (From=`sender`, To=`to`, Subject, body), buka koneksi `smtp_factory(host, port)`, `starttls()`, `login(user, password)`, `send_message(msg)`, tutup.
- Config baru: `smtp_host="smtp.gmail.com"`, `smtp_port=587`, `smtp_user=""`, `smtp_password=""`, `smtp_from=""` (default ke `smtp_user` bila kosong).
- Wiring `get_email()`: kembalikan `SmtpEmail(...)` bila `smtp_user` & `smtp_password` terisi; else `ConsoleEmail()` (fallback — app tetap boot tanpa kredensial).

## 2. Slice B — Google Calendar (`CalendarAdapter`)

- **Perluas ABC `CalendarAdapter`**: tambah method **non-abstract** dengan default no-op:
  ```python
  def create_event(self, start: datetime, *, summary: str, description: str) -> str | None:
      return None
  ```
  Sehingga `LocalCalendar` dan `FakeCalendar` otomatis aman (mewarisi no-op).
- **Refactor kecil (DRY):** ekstrak generator slot jam-kerja ke fungsi modul `iter_business_slots(now) -> list[datetime]` di `calendar.py`; `LocalCalendar.available_slots` memakainya (perilaku tetap sama, test lama hijau).
- **`GoogleCalendar(CalendarAdapter)`** di `app/integrations/google_calendar.py`:
  - `__init__(self, service, calendar_id)` — `service` = resource `googleapiclient` (disuntik; di-test dengan fake).
  - `available_slots(booked, *, now)`: panggil `service.freebusy().query(...)` untuk rentang `now`..`now+HORIZON_DAYS`, kumpulkan interval `busy`; ambil `iter_business_slots(now)` lalu buang slot yang `in booked` (via `fmt_slot`) atau jatuh di dalam interval busy.
  - `create_event(start, *, summary, description)`: `service.events().insert(calendarId=calendar_id, body={...start/end (+1 jam, timeZone Asia/Jakarta), summary, description})` → kembalikan `event["id"]`.
  - **Factory** `build_google_calendar(settings)`: import lazy `google.oauth2.service_account` + `googleapiclient.discovery.build`; muat kredensial dari `google_service_account_file` dengan scope `https://www.googleapis.com/auth/calendar`; `build("calendar","v3",credentials=...)`; return `GoogleCalendar(service, settings.google_calendar_id)`.
- Config baru: `google_calendar_id=""`, `google_service_account_file=""`.
- Wiring `get_calendar()`: `build_google_calendar(settings)` bila `google_calendar_id` & `google_service_account_file` terisi; else `LocalCalendar()`.

### Perubahan model & migration (event_id)
- **`Meeting`** (`app/models/meeting.py`): tambah `google_event_id: Mapped[str | None] = mapped_column(String(255))`.
- **Migration ke-6** (`down_revision = cb654acf820e`): `op.add_column("meetings", sa.Column("google_event_id", sa.String(255), nullable=True))`; downgrade drop_column. Ditulis tangan (tanpa autogenerate).
- **`MeetingRepository.set_google_event_id(meeting, event_id)`**: set atribut + `flush()`.
- **`create_meeting` (tools.py)**: setelah membuat baris meeting, panggil `calendar.create_event(parse_slot(chosen), summary="Konsultasi - PT Efisien Integrasi Indonesia", description=f"Link: {link}")` di dalam `try/except` (best-effort; kegagalan calendar tak membatalkan booking). Bila mengembalikan id non-None → `MeetingRepository.set_google_event_id(meeting, event_id)`. Response tool menambah `google_event_id`.

## 3. Slice C — WhatsApp via WAHA (channel baru)

- **`WahaClient`** (`app/integrations/whatsapp.py`):
  - `__init__(self, base_url, session, api_key, client=None)` — `client` = `httpx.Client` (disuntik untuk test).
  - `send_text(self, chat_id, text)`: `POST {base_url}/api/sendText`, JSON `{"session": session, "chatId": chat_id, "text": text}`, header `X-Api-Key: api_key`.
- **Route** `app/api/whatsapp.py` — `POST /webhook/whatsapp`:
  1. Baca payload WAHA. Lanjut hanya bila `event == "message"`.
  2. **Abaikan**: `payload.fromMe` true; `chatId` berakhiran `@g.us` (grup); `body` kosong/non-teks. (Kembalikan `{"status":"ignored"}` 200.)
  3. `chat_id = payload["from"]`; `phone = chat_id.split("@")[0]`; `text = payload["body"]`.
  4. `reply, _ = handle_chat(session, llm, retriever, message=text, phone=phone, calendar=calendar, mailer=email)`.
  5. `waha.send_text(chat_id, reply)`; kembalikan `{"status":"ok"}`.
  - Dependency via `Depends` yang sama (`get_session/get_llm/get_retriever/get_calendar/get_email/get_waha_client`).
- Config baru: `waha_base_url=""`, `waha_session="default"`, `waha_api_key=""`.
- `get_waha_client()` → `WahaClient(base_url, session, api_key)`.
- Daftarkan router di `app/main.py` (sebelum mount static).

## 4. Cross-cutting

- **Dependency baru (runtime, `pyproject.toml`):** `httpx`, `google-api-python-client`, `google-auth`. (`httpx` pindah/ditambah ke deps utama; tetap dipakai test.)
- **`app/config.py`:** semua field baru default kosong → app boot tanpa kredensial. `.env.example` diperbarui dengan semua kunci baru + komentar.
- **Docker Compose:** tambah service `waha` (`devlikeapro/waha`), port `3000:3000`, env webhook (`WHATSAPP_HOOK_URL=http://app:8000/webhook/whatsapp`, `WHATSAPP_HOOK_EVENTS=message`) + API key, volume `waha_sessions` (persist login QR). Service `app` dapat `WAHA_BASE_URL=http://waha:3000`, `WAHA_SESSION=default`, `WAHA_API_KEY` (+ kredensial SMTP/Google via `.env`). Catatan: nama env var internal WAHA mengikuti dokumentasi image `devlikeapro/waha` dan dirapikan saat implementasi/dokumentasi.
- **Dokumentasi:** perbarui `docs/menjalankan-dengan-docker.md` — langkah scan QR WAHA + variabel env baru.

## 5. Error Handling

- **SMTP gagal:** `send_invitation` membungkus error → balasan terstruktur; chat tak crash (pola `dispatch` `try/except` sudah ada).
- **Calendar gagal:** `create_event` best-effort di `try/except` dalam `create_meeting` — booking tetap tersimpan; `google_event_id` tetap NULL.
- **Webhook payload tak terduga / event lain:** di-skip aman dengan 200 (`status: ignored`), tak melempar 500.
- **Kredensial kosong:** fallback ke `ConsoleEmail`/`LocalCalendar`; webhook tetap terpasang (akan gagal kirim bila WAHA tak dikonfigurasi, tapi tak meng-crash app).

## 6. Testing (mock, tanpa jaringan)

- **`tests/test_email_smtp.py`:** `SmtpEmail` dengan fake SMTP factory (objek merekam `starttls/login/send_message`) → assert host/port, login(user,pass), pesan berisi To/Subject/body.
- **`tests/test_google_calendar.py`:** `GoogleCalendar` dengan fake `service`:
  - `available_slots` membuang slot yang busy (freebusy) maupun yang `booked`.
  - `create_event` memanggil `events().insert(...).execute()` dan mengembalikan id.
- **`tests/test_whatsapp.py`:**
  - `WahaClient.send_text` dengan fake httpx client → assert URL `/api/sendText`, body `{session,chatId,text}`, header `X-Api-Key`.
  - Route `/webhook/whatsapp` via `TestClient` (override deps: FakeLLM ter-script, fake retriever, FakeCalendar/FakeEmail, fake WahaClient) → kirim payload contoh → assert `handle_chat` jalan (balasan ter-persist) & `WahaClient.send_text` dipanggil dengan balasan; plus kasus abaikan (`fromMe`, grup).
- **`tests/test_meeting_repo.py` / `test_tools.py` (tambahan):** `set_google_event_id` mengisi kolom; `create_meeting` menyimpan `google_event_id` saat `create_event` mengembalikan id (pakai FakeCalendar yang meng-override `create_event`).
- **84 test lama tetap hijau** — fallback wiring + default no-op `create_event` tidak mengubah jalur web/test yang ada.

## 7. Definition of Done

- `send_invitation` mengirim email nyata via Gmail SMTP bila dikonfigurasi (tervalidasi unit dengan mock; live oleh user dengan App Password).
- `get_available_slots` membaca freebusy Google Calendar dan `create_meeting` membuat event nyata + menyimpan `google_event_id` (mock-tested; live oleh user dengan service account + calendar yang di-share).
- Klien dapat **chat lewat WhatsApp**: pesan masuk via webhook WAHA diproses agen dan dibalas via WAHA (mock-tested; live oleh user dengan instance WAHA + scan QR).
- Semua di balik config env dengan fallback aman; suite test hijau; Compose menyalakan `app` + `db` + `waha`.

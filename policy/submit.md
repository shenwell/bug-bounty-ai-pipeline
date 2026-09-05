# Пакет отправки — досье + лид

Одна папка на **лид** внутри **досье**. Площадка (Standoff, HackerOne, Bugcrowd, …) не влияет на структуру — только на поля формы в paste.

## Правило

Когда отчёт готов к отправке, оператор открывает **одну папку**:

`data/dossiers/<Dossier>/leads/<lead>/`

Пример: `data/dossiers/<Dossier>/leads/bl002/`

| `attachments/` | **Все файлы для формы** — открыть, Ctrl+A, загрузить |
| `*-paste.md` | Текст описания — копировать, **не** загружать |
| `КАК_ОТПРАВИТЬ.txt` | Чеклист |
| `manifest.json` | Конфиг сборки (агент) — **не** загружать |

В `attachments/` только вложения для формы — без paste, manifest, PoC-скриптов и служебных файлов. Скрипты (`reports/poc-*.sh`) остаются в `reports/`, в manifest не кладём, если triager не просит bash.

Рабочие артефанты (hunt, drafts, probe JSON) остаются на своих местах. `leads/<lead>/` — **собранный пакет** для оператора.

## Сборка

```bash
# From repository root
uv run python scripts/pack_submit.py data/dossiers/<Dossier> <LEAD>
```

1. `leads/<lead>/manifest.json` — что включить (шаблон: `scripts/submit-manifest.example.json`).
2. Пути в manifest — от **корня досье** (`data/dossiers/<Dossier>/`).
3. `paste` — источник текста в `reports/submit/` (в пакет копируется).
4. `pack_submit.py` — paste + вложения в `leads/<lead>/`.

Перезапускайте pack после правок paste или evidence.

## Paste

Редактирование: `reports/submit/*-paste.md`. В пакет — копия.

Секция **«Описание (скопировать…)»** — текст для формы отчёта.

### Запрещено в «Описание» (не в черновиках)

| Категория | Примеры |
|-----------|---------|
| Жирный текст | `**текст**`, `<b>` |
| Другие находки | `SUB-001`, «отдельный отчёт» |
| Внутренние пути | `evidence/`, `hunt/`, `reports/drafts/` |
| ID процесса в нарративе | `LEAD-024` в тексте (в **именах файлов** — OK) |

Связи между багами — в drafts, brain; не в paste.

## Проверка paste

```powershell
uv run python scripts/validate_submit_paste.py data/dossiers/<Dossier>/leads/<lead>/*-paste.md --lead <LEAD>
```

(Валидатор заточен под Standoff365; для других площадок — те же правила чистоты текста.)

## Скриншоты

`policy/screenshots.md` — до pack.

## Агент

Перед «готово к отправке»:

1. Paste в `reports/submit/`.
2. `leads/<lead>/manifest.json` полный.
3. `pack_submit.py` выполнен.
4. `validate_submit_paste` на paste **в пакете** — OK.
5. Сообщить оператору путь: `data/dossiers/<Dossier>/leads/<lead>/`.

Не отправлять оператора в `hunt/`, `evidence/` для сбора файлов.

## Legacy

`evidence/<lead>/submit/` + `pack_lead_submit.py` — устарело → `leads/<lead>/` + `pack_submit.py`.

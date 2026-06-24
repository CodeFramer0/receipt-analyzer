# Receipt Fraud Analyzer

Python-сервис для анализа PDF-чеков и выявления признаков подделки. Каждый PDF анализируется независимо **на байтовом уровне**: парсинг content streams, анализ объектной структуры, детекция инструментов по бинарным сигнатурам. Метаданные (Producer, Creator, даты, Keywords) и размер файла **не используются** для определения вердикта — они легко подделываются.

## Запуск

```bash
docker-compose up --build
```

Сервис доступен на `http://localhost:8000`.
Документация API: `http://localhost:8000/docs`.

## Эталонные чеки

В папку `references/` можно добавить оригинальные PDF-чеки. Сервис сравнивает проверяемые файлы с эталонами побайтово: SHA256-хэши raw bytes изображений, content stream и бинарных данных шрифтов.

## Как отправить файл на проверку

```bash
curl -X POST http://localhost:8000/check-receipt \
  -F "files=@receipt_1.pdf" \
  -F "files=@receipt_2.pdf"
```

Ответ (HTTP 202):
```json
{
  "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending"
}
```

Анализ выполняется асинхронно через Celery + Redis.

## Как получить результат анализа

```bash
curl http://localhost:8000/receipt/{analysis_id}
```

Ответ:
```json
{
  "analysis_id": "550e8400-...",
  "status": "completed",
  "files": [
    {
      "filename": "receipt_1.pdf",
      "verdict": "fake",
      "detected_bank": "tinkoff",
      "score": 3.5,
      "reasons": [
        {
          "anomaly_type": "tool_mismatch",
          "description": "HTML-to-PDF generator 'CPDF (dompdf)' detected in binary content",
          "severity": 0.95
        }
      ],
      "technical_info": {
        "producer": "...",
        "creator": "...",
        "pdf_version": "1.5",
        "page_height": 411.0,
        "page_width": 270.0,
        "is_encrypted": false,
        "revision_count": 1
      }
    }
  ],
  "created_at": "2026-06-18T12:00:00Z"
}
```

Возможные вердикты:
- `original` — аномалий не обнаружено
- `suspicious` — обнаружены подозрительные признаки (score 0.8–2.0)
- `fake` — обнаружены явные признаки подделки (score >= 2.0)
- `unknown` — невозможно извлечь данные из PDF

## Какие проверки реализованы

Все проверки работают на уровне байт и PDF-объектов, без опоры на метаданные.

### Байтовый анализ

| Проверка | Что анализируется |
|----------|------------------|
| Generator detection | Поиск бинарных сигнатур HTML-to-PDF генераторов (dompdf/CPDF, wkhtmltopdf, mPDF, WeasyPrint) и PDF-редакторов (Nitro, PDFelement) в raw bytes файла |
| JavaScript | Наличие /JS и /JavaScript объектов |
| Actions | OpenAction, Additional Actions (AA) в каталоге и на страницах |
| Incremental updates | Анализ объектов после первого %%EOF: модификация Page-объектов, текстовые операторы (Tj/TJ) в поздних ревизиях |
| Content stream | Белый текст (1 1 1 rg + Tj), невидимый текст (Tr 3), множественные Form XObject overlays, clipping masks |
| Stream filters | Нетипичные фильтры (JBIG2Decode, Crypt, LZWDecode), сложные цепочки |
| Stream length | Расхождение между объявленным /Length и фактическим размером stream |
| Trailing data | Данные после финального %%EOF маркера |
| Embedded files | Встроенные файлы внутри PDF |
| Annotations | Аннотации на страницах |
| Forbidden objects | AcroForm (интерактивные формы), Signature/Widget объекты |

### Объектно-структурный анализ

| Проверка | Что анализируется |
|----------|------------------|
| Page dimensions | Размер страницы из MediaBox (не метаданные, а свойство page object) |
| Object count | Количество PDF-объектов |
| Image count | Количество image XObjects |
| Image raw bytes | Суммарный размер raw bytes изображений (5% tolerance) |
| Font count | Количество font-объектов |
| Font raw bytes | Суммарный размер raw bytes шрифтов (диапазон) |
| Font embedding | Смешение embedded/non-embedded шрифтов |
| Font size variance | Аномальный разброс размеров шрифтов |
| Revisions | Множественные %%EOF маркеры |
| Text layer | Пустой текст при наличии страниц |

### Сравнение с эталонами (references/)

| Проверка | Что сравнивается |
|----------|-----------------|
| Image bytes | SHA256 raw bytes каждого изображения |
| Content stream | SHA256 decoded content stream |
| Font bytes | SHA256 бинарных данных шрифтов (FontFile2/FontFile/FontFile3) |

Аномалии: идентичные изображения но разный content stream (модифицированная копия), идентичные изображения но другие шрифты (подмена шрифтов).

### Пример: побайтовое сравнение поддельного и оригинального чека

| Параметр | Fake | Original |
|---|---|---|
| Image SHA256 (logo, QR) | `4814e08e`, `1d916221`, `655e8751` | **идентичные** |
| Content stream hash | `627d87f1` | `17da3559` |
| Content stream size | 872 bytes | 927 bytes |
| Font binary hash (FontFile2) | `f92b14f6` | `c9e6f23a` |
| Font binary size | 24 867 bytes | 25 513 bytes |

Изображения побайтово совпадают (одинаковые SHA256 raw bytes), а content stream и шрифтовой бинарник отличаются — кто-то взял оригинальный чек и подменил текстовые данные (ФИО, дату, сумму). Шрифт изменился потому, что при смене текста меняется subset встроенного шрифта.

### Банк-специфичные проверки

Банк определяется по тексту чека (не по метаданным). Для Сбера — проверка объектной структуры по эталонным спецификациям (object/image/font counts, raw bytes). Для Тинькофф — проверка email fb@tbank.ru в тексте.

## Как формируется итоговый вывод

1. Байтовый анализ: парсинг raw bytes, content streams, поиск сигнатур генераторов, проверка stream integrity
2. Объектно-структурный анализ: counts, raw byte sizes, font embedding, revisions
3. Сравнение с эталонами (если есть): побайтовое сравнение image/font/content stream хэшей
4. Каждая проверка генерирует индикатор с типом аномалии и severity (0.0–1.0)
5. Итоговый score = сумма(severity * weight):

| Тип аномалии | Вес |
|---|---|
| javascript_detected | 5.0 |
| revision_anomaly | 3.0 |
| tool_mismatch | 2.5 |
| content_stream_anomaly | 2.5 |
| structure_anomaly | 1.5 |
| font_inconsistency | 1.5 |
| stream_anomaly | 1.5 |
| text_layer_anomaly | 1.0 |

6. Вердикт по score: `original` (< 0.8) → `suspicious` (0.8–2.0) → `fake` (>= 2.0)

## Стек

Python 3.12, FastAPI, Celery, Redis, pikepdf, pdfplumber, Pydantic v2, Docker

## Тесты

```bash
pip install ".[test]"
pytest tests/ -v
```

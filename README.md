# Receipt Fraud Analyzer

Python-сервис для анализа PDF-чеков и выявления признаков подделки. Каждый PDF анализируется независимо. Допускается сравнение с набором эталонных оригинальных чеков.

## Запуск

```bash
docker-compose up --build
```

Сервис доступен на `http://localhost:8000`.
Документация API: `http://localhost:8000/docs`.

## Эталонные чеки

Для повышения точности анализа в папку `references/` можно добавить оригинальные PDF-чеки. Сервис сравнивает проверяемые файлы с эталонами по producer, размеру страницы и версии PDF.

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
      "verdict": "suspicious",
      "detected_bank": "tinkoff",
      "score": 1.2,
      "reasons": [
        {
          "anomaly_type": "structure_anomaly",
          "description": "Keywords contain MD5-style hash instead of expected UUID format",
          "severity": 0.8
        }
      ],
      "technical_info": {
        "producer": "OpenPDF 1.3.30.jaspersoft.2",
        "creator": "JasperReports Library version 6.20.3",
        "pdf_version": "1.5",
        "page_height": 411.0,
        "page_width": 270.0,
        "is_encrypted": false,
        "revision_count": 1,
        "keywords": "28.05.2026 21:38:32 | bdf4585b... | 991"
      }
    },
    {
      "filename": "receipt_2.pdf",
      "verdict": "original",
      "detected_bank": "tinkoff",
      "score": 0.0,
      "reasons": [],
      "technical_info": { "..." }
    }
  ],
  "created_at": "2026-06-18T12:00:00Z"
}
```

Возможные вердикты:
- `original` - аномалий не обнаружено
- `suspicious` - обнаружены подозрительные признаки (score 1.0 - 3.0)
- `fake` - обнаружены явные признаки подделки (score >= 3.0)
- `unknown` - невозможно извлечь данные из PDF

## Какие проверки реализованы

Сервис автоматически определяет банк-эмитент чека (Тинькофф, Сбер) и применяет соответствующий набор проверок.

### Общие проверки (все банки)

| Проверка | Что анализируется |
|----------|------------------|
| Имя файла | Наличие ключевого слова "receipt" |
| Producer | Обнаружение HTML-to-PDF генераторов (dompdf, mPDF, wkhtmltopdf) |
| Producer/Creator | Соответствие ожидаемым значениям для банка |
| PDF version | Соответствие ожидаемой версии |
| Даты | Несоответствие даты создания и модификации |
| Шрифты | Смешение embedded/non-embedded, большой разброс размеров |
| Ревизии | Множественные %%EOF маркеры (признак редактирования) |
| Текстовый слой | Пустой текст при наличии страниц |

### Тинькофф

| Проверка | Критерий |
|----------|---------|
| Email | Наличие fb@tbank.ru в тексте чека |
| Keywords | Формат идентификатора (UUID vs MD5) |
| Keywords | Наличие метаданных квитанции |

### Сбер

| Проверка | Критерий |
|----------|---------|
| Размер страницы | Соответствие эталону (300x699 или 300x795) |
| Количество объектов | Соответствие эталону (16 или 17) |
| Количество изображений | Соответствие эталону (3 или 4) |
| Размер шрифтов (raw bytes) | Попадание в допустимый диапазон |
| Размер файла | Попадание в допустимый диапазон |

### Сравнение с эталонами

| Проверка | Что сравнивается |
|----------|-----------------|
| Producer | Совпадение с producer эталонных чеков |
| Размер страницы | Совпадение с эталонными значениями |
| PDF-версия | Совпадение с эталонными версиями |

## Как формируется итоговый вывод

1. Сервис определяет банк-эмитент по тексту чека и метаданным producer
2. Каждая проверка генерирует индикатор с типом аномалии и severity (0.0 - 1.0)
3. Итоговый score = сумма(severity * weight), где weight зависит от типа аномалии
4. Вердикт определяется по score:
   - `original` - score = 0, аномалий нет
   - `suspicious` - score от 1.0 до 3.0
   - `fake` - score >= 3.0
   - `unknown` - ошибка при извлечении данных из PDF

## Стек

Python 3.12, FastAPI, Celery, Redis, pikepdf, pdfplumber, Pydantic v2, Docker

## Тесты

```bash
pip install ".[test]"
pytest tests/ -v
```

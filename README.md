# Receipt Fraud Analyzer

Python-сервис для анализа PDF-чеков и выявления признаков подделки. Каждый PDF анализируется независимо.

## Запуск

```bash
docker-compose up --build
```

Сервис доступен на `http://localhost:8000`.

## Эталонные чеки

Для повышения точности анализа в папку `references/` можно добавить оригинальные PDF-чеки. Сервис будет сравнивать проверяемые файлы с эталонами по producer, размеру страницы и версии PDF.

## API

### POST /check-receipt

Отправка одного или нескольких PDF на анализ. Обработка выполняется асинхронно через Celery.

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

### GET /receipt/{analysis_id}

Получение результата анализа.

```bash
curl http://localhost:8000/receipt/{analysis_id}
```

Ответ:
```json
{
  "analysis_id": "...",
  "status": "completed",
  "files": [
    {
      "filename": "receipt_1.pdf",
      "verdict": "suspicious",
      "score": 1.2,
      "reasons": [
        {
          "anomaly_type": "structure_anomaly",
          "description": "Keywords contain MD5-style hash instead of expected UUID format",
          "severity": 0.8
        }
      ]
    }
  ],
  "created_at": "2026-06-18T12:00:00Z"
}
```

Возможные вердикты: `original`, `fake`, `suspicious`, `unknown`.

## Реализованные проверки

### Индивидуальный анализ файла

| Проверка | Что ищем |
|----------|----------|
| Имя файла | Наличие ключевого слова "receipt" |
| Email | Наличие fb@tbank.ru в тексте чека |
| Producer | Обнаружение HTML-to-PDF генераторов (dompdf, mPDF, wkhtmltopdf и др.) |
| Keywords | Формат идентификатора (UUID vs MD5), наличие метаданных |
| Даты | Несоответствие даты создания и модификации |
| Шрифты | Количество, смешение embedded/non-embedded, системные шрифты, разброс размеров |
| Ревизии | Множественные %%EOF маркеры (признак редактирования) |
| Текстовый слой | Пустой текст, табуляция, избыточные пробелы |

### Сравнение с эталонами (если добавлены в references/)

| Проверка | Что сравниваем |
|----------|---------------|
| Producer | Совпадение с producer эталонных чеков |
| Размер страницы | Совпадение высоты с эталонными значениями |
| PDF-версия | Совпадение с эталонными версиями |

### Формирование вердикта

Каждая проверка создает индикатор с severity (0.0-1.0). Итоговый score = сумма(severity * weight). Вердикт определяется по score:

- `original` - score = 0, аномалий нет
- `suspicious` - score от 1.0 до 3.0
- `fake` - score >= 3.0
- `unknown` - невозможно извлечь данные

## Стек

Python 3.12, FastAPI, Celery, Redis, pikepdf, pdfplumber, Pydantic v2, Docker

# Техническое задание: BlockchainSection

- **ID ноды:** `662:808`
- **Имя компонента (PascalCase):** `BlockchainSection`

## 1. Общее описание

Макет `BlockchainSection` содержит 3 нод(ы). Необходимо реализовать веб-страницу/секцию, максимально приближенную к дизайну Figma.

## 2. Структура страницы

- **BlockchainSection** (FRAME, id: `662:808`)
  - **Title** (TEXT, id: `662:809`)
  - **Description** (TEXT, id: `662:810`)

## 3. Цветовая палитра

| HEX | RGB | Где используется |
| --- | --- | ---------------- |
| #0D0D14 | rgb(13, 13, 20) | BlockchainSection |

## 4. Типографика

| Шрифт | Размер | Вес | Пример текста |
| ----- | ------ | --- | ------------- |
| Inter | 48px | 700 | Decentralized Future |
| Inter | 16px | 400 | Building secure and scalable solutions on the blockchain. |

## 5. Layout и отступы

```
- [FRAME] **BlockchainSection**: AutoLayout vertical, spacing=0px, padding (pt=0 pr=0 pb=0 pl=0)
    - Text: "Decentralized Future" (font=Inter, size=48, weight=700)
    - Text: "Building secure and scalable solutions on the blockchain." (font=Inter, size=16, weight=400)
```

## 8. Требования к фронтенду

- Использовать React + Next.js + TypeScript.
- Стилизация через Tailwind CSS.
- Цвета и шрифты должны соответствовать таблицам выше.
- Layout, padding и spacing должны соответствовать AutoLayout Figma.
- Ассеты должны быть сохранены в `public/images/` и подключены через `<img>`.
- Компонент должен быть семантичным и доступным (a11y).

## 9. Предполагаемые требования к бэкенду

На основе дизайна однозначно определить бэкенд невозможно. Ниже — типовые эндпоинты, которые могут понадобиться для страницы такого типа:

- `GET /api/content/{section}` — получение текстового контента секций.
- `GET /api/assets` — список медиа-ассетов для страницы.
- `POST /api/contact` или `POST /api/lead` — если в дизайне есть формы.

Для точного ТЗ на бэкенд необходимо указать:
- бизнес-логику страницы,
- источники данных,
- сценарии взаимодействия пользователя.

## 10. Рекомендуемые следующие шаги

1. Запустить генерацию компонента: `python agent.py --node-id 662:808`
2. Скачать ассеты: `python asset_downloader.py` (или через `agent.py` без `--skip-assets`)
3. Проверить результат в `components/BlockchainSection.tsx`.

# GadgetFlow — Design Specification

## 1. Project identity
- **Name:** GadgetFlow
- **Tagline:** «Техника, которая работает на вас»
- **Domain:** интернет-магазин электроники и гаджетов
- **Markets:** Россия + СНГ + Южный Кавказ + Балканы (KZ, AM, AZ, GE, RS, HR, BG, BY)
- **MVP language:** русский
- **MVP currency:** RUB (единая валюта для всех рынков)
- **Business model:** ИП, дистанционная торговля, гостевой checkout
- **Anti-slop direction:** `minimal_tech`

## 2. Sources and constraints
- **Brief:** `TECHNICAL_ASSIGNMENT.md`
- **Reference screenshots:** `shablons/scrinhost.png`, `scrinhost1.png`, `scrinhost2.png`
- **Requirement:** повторить структуру, компоновку секций, UX-паттерны и пропорции референса на 95–99%, но заменить брендинг, тексты, логотип и изображения на уникальные.
- **Stack:** Next.js 15 App Router, TypeScript strict, Tailwind CSS 4, Framer Motion, Lucide React, shadcn/ui.
- **Data:** mock JSON in `src/lib/data/`; cart + wishlist via `localStorage` + React Context.
- **Lighthouse hard gate:** ≥90 Performance, ≥95 Accessibility, ≥95 Best Practices, ≥95 SEO.

## 3. Visual system

### 3.1 Palette
| Token | Hex | Usage |
|---|---|---|
| `background` | `#FFFFFF` | основной фон |
| `surface` | `#F6F6F6` | серые секции, карточки |
| `surface-muted` | `#F8F9FA` | hover-фоны, badges |
| `text` | `#0A0A0A` | основной текст |
| `text-secondary` | `#525252` | подписи, описания |
| `text-muted` | `#737373` | placeholder, disabled |
| `accent` | `#2563EB` | CTA, links, active states |
| `accent-hover` | `#1D4ED8` | hover CTA |
| `accent-subtle` | `#EBF2FF` | badge backgrounds |
| `border` | `#E5E5E5` | borders, dividers |
| `success` | `#16A34A` | in stock, success |
| `warning` | `#EAB308` | sale, attention |
| `error` | `#DC2626` | out of stock, errors |

### 3.2 Typography
- **UI / body:** Geist Sans, sans-serif
- **Hero / display headings:** Playfair Display, serif
- **Base size:** 16 px
- **Scale:** xs 12 / sm 14 / base 16 / lg 18 / xl 20 / 2xl 24 / 3xl 30 / 4xl 36 / 5xl 48 / 6xl 60 px
- **Line height:** 1.5 body, 1.2 display
- **Font weights:** 400 regular, 500 medium, 600 semibold, 700 bold

### 3.3 Spacing and shape
- **Section vertical padding desktop:** 80–120 px
- **Container max-width:** 1280 px
- **Grid gap:** 24–32 px
- **Card radius:** `rounded-2xl` (16 px)
- **Button radius:** `rounded-full` (pill)
- **Input radius:** `rounded-xl` (12 px)
- **Shadows:** subtle `0 4px 24px rgba(0,0,0,0.06)` for cards and images

### 3.4 Motion
- **Easing:** `cubic-bezier(0.16, 1, 0.3, 1)`
- **Duration:** 0.3–0.5 s
- **Scroll reveal:** fade-in + translateY(24px → 0), stagger 0.1 s
- **Card hover:** `translateY(-4px)` + shadow lift
- **Image hover:** scale 1.02
- **Hero:** static image with subtle parallax on scroll (optional)

## 4. Logo and brand mark
- **Type:** уникальный SVG-знак + текстовая часть «GadgetFlow»
- **Concept:** абстрактный tech-знак, передающий поток/движение технологий (не сердечко, не копирует референс)
- **Usage:** header left, footer, favicon, OG image

## 5. Page structure — Home

### 5.1 Header
- Height ~72 px desktop, ~64 px mobile
- Left: logo + hamburger menu (mobile + catalog overlay)
- Center: search bar with icon
- Right: support phone, account icon, wishlist icon, cart icon with amount
- Below header: category navigation bar (desktop): Смартфоны, Ноутбуки, Аудио, Смарт-часы, Умный дом, Аксессуары, Распродажа

### 5.2 Hero
- Full-width slider / static banner
- Theme: «Wireless Sound Revolution»
- Big headline, subheadline, pill CTA
- Large product image (headphones/smart watch) on light/gradient background
- Slide indicators (dots)

### 5.3 Collections
- 4 category cards in a row:
  - Смарт-часы
  - Наушники и аудио
  - Смартфоны
  - Аксессуары
- Image + title overlay, hover lift

### 5.4 Featured Products
- Section title + horizontal slider / 4-column grid
- Product card:
  - image (1:1, white/light bg)
  - rating stars + review count
  - product name
  - price in RUB
  - hover add-to-cart button

### 5.5 Split Banner — «Выбор редакции»
- Left: large lifestyle image (phone + headphones / laptop)
- Right: mini carousel of editor's choice products
- Layout 50/50 or 55/45 desktop, stacked mobile

### 5.6 Value Proposition
- Background: soft blue `#EBF2FF`/gray `#F6F6F6`
- Title: «Всё необходимое — в одном месте»
- 3–4 benefit items with icons

### 5.7 Product Showcase
- Full-width lifestyle photo
- Overlay product card + sale badge
- Badge examples: «Рекомендуем», «Летняя распродажа», «-30%»

### 5.8 Benefits Strip
- 4 icons with text:
  - Быстрая доставка
  - Официальная гарантия
  - Поддержка 7 дней в неделю
  - Безопасная оплата

### 5.9 Reviews
- 3–5 testimonial cards
- Avatar, name, rating, text

### 5.10 Blog / News
- 3 article cards
- Image, category, title, date

### 5.11 FAQ
- Accordion
- Topics: delivery, payment, warranty, returns

### 5.12 Instagram / Lifestyle Gallery
- Grid 4–6 images
- CTA «Следите за нами @gadgetflow»

### 5.13 Subscribe
- Dark/gradient background
- Title + email input + subscribe button

### 5.14 Footer
- 4 columns:
  - About + contacts
  - Customers (Delivery, Payment, Warranty, Returns)
  - Catalog categories
  - Connect (messengers, socials)
- Payment method logos
- Copyright + legal links

## 6. Catalog
- Routes: `/catalog/[category]`, `/catalog/[category]/[slug]`
- Grid: 4 cols desktop / 2 tablet / 1 mobile
- Filters (client-side, no reload): brand, price range, category, availability, rating, attributes (color, memory, screen, connection)
- Sort: popularity, price asc/desc, newest, rating
- Pagination or Load more

## 7. Product Page (PDP)
- Image gallery with main + thumbnails
- Zoom on hover
- Title, brand, rating, reviews count
- Price + discount
- Stock status
- Short description
- Variant selector (color / memory / size) when applicable
- Quantity
- Add to cart + Add to wishlist buttons
- Tabs: Description, Specifications, Reviews, Warranty/Delivery
- Cross-sell block

## 8. Cart & Checkout
- Cart: drawer + separate `/cart` page
- Checkout route: `/checkout`
- Guest checkout only
- Checkout steps:
  1. Contacts (name, phone, email)
  2. Delivery: country selector (KZ, AM, AZ, GE, RS, HR, BG, BY, RU), city, address, delivery zone → mocked rates and terms (СДЭК/Boxberry zones)
  3. Payment: mock acquiring UI with success/failure scenario
  4. Order confirmation
- No real payment gateway in MVP
- No currency selector (always RUB)

## 9. Static pages
- `/about` — About company (requisites of ИП, UNP, address, phone, email, working hours, trade registry mention)
- `/delivery` — Delivery & payment methods by zones
- `/warranty` — Warranty & returns (14 days)
- `/contacts` — Contacts + map + messengers
- `/privacy` — Privacy policy
- `/terms` — Terms of service / offer
- `/faq` — FAQ page (duplicate/expanded)
- `/news` + `/news/[slug]` — Blog / news
- `/wishlist` — Wishlist
- `/account` — Account placeholder (Phase 2)

## 10. Data & content
- Mock products in `src/lib/data/products.json`
- Mock categories in `src/lib/data/categories.json`
- Mock reviews in `src/lib/data/reviews.json`
- Mock articles in `src/lib/data/articles.json`
- Mock delivery zones in `src/lib/data/delivery.json`
- All prices in RUB
- Product images: clean tech photos on light backgrounds

## 11. Regional specifics
- Single currency: RUB
- Country selector appears only at checkout
- Phone validation per selected country
- Delivery rates mocked by 3–4 zones (СДЭК/Boxberry style)
- Legal pages: universal package based on ИП registration country, covering EAEU distant trade rules

## 12. Components to build (high-level)
- `Header`, `Footer`, `MobileMenu`, `SearchBar`
- `HeroSlider`, `CollectionCard`, `ProductCard`
- `ProductCarousel`, `SplitBanner`, `ValueProposition`
- `ProductShowcase`, `BenefitsStrip`, `ReviewCard`
- `ArticleCard`, `FaqAccordion`, `GalleryGrid`
- `SubscribeForm`, `FilterPanel`, `SortSelect`
- `ImageGallery`, `ProductInfo`, `Tabs`
- `CartDrawer`, `CartItem`, `CheckoutForm`
- `CountrySelect`, `DeliveryEstimator`, `PaymentMock`

## 13. Anti-slop checks
- No generic Unsplash placeholders without styling
- No copied reference brand names/logos/texts/badges
- Structure repeats reference at 95–99%
- Unified typography and palette
- Avoid centered "3 feature cards" hero clutter
- Every section has a clear visual purpose

## 14. MVP acceptance criteria
1. Home page matches reference structure 95–99%.
2. Unique branding, texts, logo, images.
3. Responsive 320–1920 px.
4. Catalog filters work without reload.
5. Cart + checkout collect data and show confirmation screen.
6. All required legal blocks present.
7. Lighthouse ≥90/95/95/95.
8. Strict TypeScript, modular structure, no unjustified `any`.

"""Import supplier price list (praise_5.xlsx) into GadgetFlow products.ts.

Heavily improved parser:
- Category mapping is based on the supplier's Russian group names.
- Brand extraction uses a curated brand dictionary and falls back to parsing.
- Short description and basic specs are extracted from parenthesized characteristics.
- Empty/placeholder category headers are ignored.
"""

import argparse
import json
import re
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

DEFAULT_LIMIT_PER_CATEGORY = 6
DEFAULT_MAX_ROW = 20000
DEFAULT_FALLBACK_RUB_TO_BYN = 0.0351

# Map supplier category group names to site categories.
# Order matters: more specific groups should come before generic ones.
CATEGORY_KEYWORDS = [
    # smartfony
    (["телефоны", "смартфон"], "smartfony"),
    # noutbuki
    (["планшеты", "ноутбуки", "мониторы"], "noutbuki"),
    # audio
    (["наушники", "колонки", "автозвук", "fm модуляторы", "aux/3.5", "тюльпаны", "rca"], "audio"),
    # smart-chasy
    (["часы", "браслеты", "ремешки", "фитнес"], "smart-chasy"),
    # umnyy-dom
    (["умная техника", "tv приставки", "tv тюнеры", "wi-fi роутеры", "лампы/фонари", "прожекторы", "гирлянды", "умный дом", "телевизоры", "пульты"], "umnyy-dom"),
    # aksessuary (catch-all for accessories)
    ([
        "power bank", "аккумуляторы внешние", "зарядные", "зу", "кабели", "чехлы",
        "стекла", "защитные", "держатели", "флеш", "накопители", "карта памяти",
        "переходники", "адаптеры", "бампер", "накладк", "акссесуары", "аксессуары",
        "автомобильные", "видеорегистраторы", "клавиатуры", "мышки", "сим карта",
        "автовизитка", "сетевые фильтры", "удлинители", "подставки", "чехол",
    ], "aksessuary"),
]

# Category headers that contain no useful product group information.
IGNORED_CATEGORY_HEADERS = [
    "товары", "цифровая техника", "видеонаблюдение", "расходники",
    "электронные испарители", "картриджи/испарители",
]

# Curated brand dictionary. Order: longer names first to avoid partial matches.
BRAND_NAMES = [
    "blackview", "samsung", "xiaomi", "redmi", "poco", "iphone", "apple", "honor", "huawei",
    "realme", "infinix", "tecno", "nokia", "motorola", "sony", "philips", "jbl", "anker",
    "baseus", "borofone", "canyon", "edifier", "havit", "hoco", "lenovo", "logitech", "nomi",
    "oneplus", "oppo", "vivo", "zte", "meizu", "asus", "dell", "hp", "acer", "microsoft",
    "beats", "bose", "sennheiser", "skullcandy", "marshall", "harman kardon", "tommy",
    "belkin", "remax", "usams", "dp", "pineng", "romoss", "df", "ugreen",
    "a data", "adata", "kingston", "sandisk", "transcend", "silicon power", "goodram",
    "tplink", "tp-link", "netis", "dlink", "d-link", "tenda", "keenetic", "mercusys",
    "yeelight", "yandex", "sber", "garmin", "amazfit", "haylou", "ledeme",
    # Supplier-specific / niche brands found in the price list
    "agm", "aion", "ballons", "borofone", "bq", "colmi", "cubot", "dendy", "denmen", "dexp",
    "digma", "doogee", "dream", "dtno.1", "elephone", "elari", "energy power", "explay",
    "highscreen", "hk", "homtom", "irbis", "jokade", "kakusiga", "kieslect", "kumo",
    "leagoo", "lemfo", "maxvi", "mdk", "micromax", "microlab", "nomi", "oukitel",
    "perfeo", "pioneer", "pioneeir", "prestigio", "rapoo", "ritmix", "sega",
    "senbono", "sma", "supra", "tcl", "teclast", "trust", "ulefone", "vkworld",
    "wileyfox", "yotaphone",
    # Generic PC/peripheral brands found in accessories sections
    "a4tech", "defender", "dialog", "genius", "gembird", "oklick", "sven",
    # Other supplier/niche names
    "билайн",
]

# Normalize brand display names.
BRAND_DISPLAY = {
    "iphone": "Apple",
    "samsung": "Samsung",
    "xiaomi": "Xiaomi",
    "redmi": "Xiaomi",
    "poco": "Xiaomi",
    "blackview": "BLACKVIEW",
    "honor": "HONOR",
    "huawei": "Huawei",
    "realme": "realme",
    "infinix": "Infinix",
    "tecno": "TECNO",
    "nokia": "Nokia",
    "motorola": "Motorola",
    "philips": "Philips",
    "jbl": "JBL",
    "anker": "Anker",
    "baseus": "Baseus",
    "borofone": "BOROFONE",
    "hoco": "HOCO",
    "lenovo": "Lenovo",
    "logitech": "Logitech",
    "oneplus": "OnePlus",
    "oppo": "OPPO",
    "vivo": "vivo",
    "zte": "ZTE",
    "asus": "ASUS",
    "dell": "Dell",
    "hp": "HP",
    "acer": "Acer",
    "pioneeir": "Pioneer",
    "pioneer": "Pioneer",
    "denmen": "DENMEN",
    "hk": "HK",
    "билайн": "Билайн",
    "ballons": "Ballons",
    "dendy": "Dendy",
    "sega": "Sega",
    "maxvi": "MAXVI",
    "bq": "BQ",
    "aion": "Aion",
    "dream": "Dream",
    "energy power": "Energy Power",
    "jokade": "Jokade",
    "kakusiga": "Kakusiga",
    "kumo": "KUMO",
    "mdk": "MDK",
}

IMAGE_MAP = {
    "smartfony": "/images/products/iphone15.jpg",
    "smart-chasy": "/images/products/watch-s9.jpg",
    "audio": "/images/products/sony-xm5.jpg",
    "noutbuki": "/images/products/macbook-air.svg",
    "umnyy-dom": "/images/products/yandex-station-mini.svg",
    "aksessuary": "/images/products/anker-powerbank.jpg",
}


def fetch_rub_to_byn_rate() -> float:
    """Fetch RUB to BYN conversion rate from exchangerate.host."""
    try:
        url = "https://api.exchangerate.host/convert?from=RUB&to=BYN"
        with urllib.request.urlopen(url, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
        rate = data.get("result") or data.get("info", {}).get("rate")
        if isinstance(rate, (int, float)) and rate > 0:
            print(f"Fetched RUB->BYN rate: {rate}")
            return float(rate)
    except Exception as exc:
        print(f"Currency API failed ({exc}); using fallback rate {DEFAULT_FALLBACK_RUB_TO_BYN}")
    return DEFAULT_FALLBACK_RUB_TO_BYN


def parse_args():
    parser = argparse.ArgumentParser(description="Import supplier price list into GadgetFlow products.ts")
    parser.add_argument("--input", "-i", default="praise_5.xlsx", help="Path to .xlsx price list")
    parser.add_argument("--output", "-o", default="gadgetflow/src/lib/data/products.ts", help="Path to generated products.ts")
    parser.add_argument("--limit-per-category", "-l", type=int, default=DEFAULT_LIMIT_PER_CATEGORY,
                        help="Maximum products per site category")
    parser.add_argument("--max-row", type=int, default=DEFAULT_MAX_ROW,
                        help="Last row to scan in sheet1.xml")
    parser.add_argument("--rate", "-r", type=float, default=None,
                        help="RUB to BYN conversion rate (default: fetch from API)")
    parser.add_argument("--dry-run", action="store_true", help="Print stats without writing products.ts")
    return parser.parse_args()


def read_sheet(xlsx_path: str, max_row: int):
    """Read supplier sheet and return a list of raw product dicts."""
    z = zipfile.ZipFile(xlsx_path)
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

    sst = z.read("xl/SharedStrings.xml").decode("utf-8-sig")
    root = ET.fromstring(sst)
    strings = [
        si.find("m:t", ns).text if si.find("m:t", ns) is not None else ""
        for si in root.findall("m:si", ns)
    ]

    xml = z.read("xl/worksheets/sheet1.xml").decode("utf-8-sig")
    sheet = ET.fromstring(xml)
    rows = sheet.find(".//m:sheetData", ns)

    # Build an O(1) cell lookup table. Keys: (row_number, col_letter).
    cells = {}
    max_seen_row = 10
    for r in rows:
        row_num = int(r.attrib["r"])
        if row_num > max_seen_row:
            max_seen_row = row_num
        for c in r:
            ref = c.attrib["r"]
            col_letter = re.sub(r"\d", "", ref)
            t = c.attrib.get("t", "")
            v = c.find("m:v", ns)
            if t == "s" and v is not None:
                value = strings[int(v.text)]
            else:
                value = v.text if v is not None else ""
            cells[(row_num, col_letter)] = value

    def get_val(row_num: int, col_letter: str) -> str:
        return cells.get((row_num, col_letter), "")

    catalog = []
    current_category = None
    last_row = min(max_row, max_seen_row)

    # Some product rows contain only the product keyword and no price in D/E/F,
    # but they do have a price in D. Category rows have no price.
    for r in range(10, last_row + 1):
        b = get_val(r, "B").strip()
        c = get_val(r, "C").strip()
        d = get_val(r, "D").strip().replace(",", ".")
        e = get_val(r, "E").strip().replace(",", ".")
        f = get_val(r, "F").strip()
        if not b:
            continue

        # Category/group row heuristic: no price columns and not a stock marker.
        is_category = b.isupper() or (
            not d and not e and not f and c != "+" and len(b) < 120
        )
        if is_category:
            current_category = b.strip()
            continue

        if d and d.replace(".", "").isdigit():
            price = int(float(d))
            catalog.append({
                "category": current_category,
                "name": b,
                "available": c == "+",
                "price_cash": price,
                "price_cashless": int(float(e)) if e and e.replace(".", "").isdigit() else price,
                "qty": f,
            })

    return catalog


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def is_ignored_category(raw_cat: str) -> bool:
    norm = normalize_text(raw_cat or "")
    return any(header in norm for header in IGNORED_CATEGORY_HEADERS)


def map_category(raw_cat: str, name: str) -> str:
    """Map supplier group + product name to a site category."""
    text = normalize_text(raw_cat or "") + " " + normalize_text(name)

    # Direct category keyword matching (specific groups first).
    for keywords, target in CATEGORY_KEYWORDS:
        if any(kw in text for kw in keywords):
            return target

    # Fallback by product name keywords.
    if any(kw in name.lower() for kw in ["смартфон", "телефон", "iphone"]):
        return "smartfony"
    if any(kw in name.lower() for kw in ["планшет", "ноутбук", "монитор"]):
        return "noutbuki"
    if any(kw in name.lower() for kw in ["наушник", "колонк", "гарнитура", "aux", "rca", "тюльпан"]):
        return "audio"
    if any(kw in name.lower() for kw in ["часы", "браслет", "ремешок", "fitness", "фитнес"]):
        return "smart-chasy"
    if any(kw in name.lower() for kw in ["tv", "роутер", "лампа", "фонарь", "умный дом", "пульт"]):
        return "umnyy-dom"

    return "aksessuary"


def extract_brand(raw_cat: str, name: str) -> str:
    """Extract brand from category group and product name."""
    combined = (raw_cat or "") + " " + name
    combined_lower = combined.lower()

    # 1. Try to extract brand from category group names like:
    #    "Телефоны BQ", "Чехлы Samsung A10s", "Автодинамики Pioneer", "Часы HK".
    cat_lower = normalize_text(raw_cat or "")
    group_match = re.match(
        r"^(?:телефоны?|чехлы|защитные стекла|защитные стёкла|наушники|колонки|клавиатуры|мышки|" +
        r"автодинамики|сабвуферы|видеорегистраторы|зу|ремешки|часы|" +
        r"аккумуляторы|сетевые зу|кабели|стекла|чехол|планшеты|мониторы)\s+([a-z0-9а-яё]+)",
        cat_lower,
    )
    if group_match:
        brand = group_match.group(1).strip()
        if brand and brand not in ["для", "на", "с", "в", "по", "из", "и", "copy", "original", "copi"]:
            return BRAND_DISPLAY.get(brand.lower(), brand.title())

    # 2. Brand dictionary lookup (longest match first) across category + name.
    best_match: Optional[str] = None
    best_len = 0
    for brand in BRAND_NAMES:
        bnorm = brand.lower()
        # Require word boundaries for short brands to avoid false matches.
        if len(brand) <= 3:
            if re.search(r"\b" + re.escape(bnorm) + r"\b", combined_lower):
                if len(brand) > best_len:
                    best_len = len(brand)
                    best_match = brand
        else:
            if bnorm in combined_lower:
                if len(brand) > best_len:
                    best_len = len(brand)
                    best_match = brand

    if best_match:
        return BRAND_DISPLAY.get(best_match.lower(), best_match.title())

    # 3. Fallback: try to grab first meaningful word after removing product prefixes.
    cleaned = re.sub(
        r"^(?:Смартфон|Монитор|Наушники|Часы|Умные часы|Планшет|Колонка|Power Bank|" +
        r"Зарядное|Зарядка|Кабель|Чехол|Защитное|Защитное стекло|Держатель|Аккумулятор|" +
        r"Флеш|Карта памяти|Мобильный телефон|Телефон|Умные|Беспроводные|Проводные|" +
        r"Портативная|Напольная|Автомобильные|Автомобильный|Сетевые|Сетевой|" +
        r"Универсальные|Универсальный|Силиконовый|Автомагнитола|Ресивер|Картридж|" +
        r"Сабвуфер|Видеорегистратор|Автовизитка|Ремешки|Защитные|Защитный|Активный|" +
        r"Парковочная|LCD|Воздушный|Домкрат|Акустический|Рамка|Дневные|Диагностический|" +
        r"Комплект|Двудиновая|Игровая|Игровой|Магнитола|" +
        r"Рамка для номера|Кабель диагностический|Акустический комплект)\s*",
        "",
        name,
        flags=re.IGNORECASE,
    ).strip()
    match = re.match(r"([A-Za-z0-9А-Яа-я]+)", cleaned)
    brand = match.group(1) if match else "Unknown"
    ignore = [
        "для", "на", "с", "в", "по", "из", "и", "copy", "original", "copi",
        "без", "white", "black", "серый", "синий", "красный", "зеленый", "голубой",
        "желтый", "оранжевый", "розовый", "фиолетовый", "коричневый", "золотой",
        "серебристый", "графит", "белый", "черный", "синий", "красный",
        "авто", "bluetooth", "салфетка", "гидравлический", "монитор", "парктроник",
        "ходовые", "диагностический", "комплект", "приставка", "игрушка", "рамка",
        "воздушный", "дневные", "акустический", "домкрат", "парковочная", "активный",
        "магнитола", "игровая", "игровой", "двудиновая", "автомобильный", "автомобильные",
        "беспроводные", "проводные", "портативная", "напольная", "сетевые", "сетевой",
        "универсальные", "универсальный", "силиконовый", "защитный", "защитные",
    ]
    if brand.lower() in ignore:
        return "Unknown"
    return brand.title()


def extract_features(name: str) -> tuple[str, dict[str, str]]:
    """Extract short description and specs from parenthesized characteristics."""
    short = ""
    specs: dict[str, str] = {}
    parens = re.findall(r"\(([^()]*)\)", name)
    if parens:
        # Use the last parenthetical block as the main characteristics string.
        chars = parens[-1].strip()
        if chars:
            short = chars
            # Attempt to identify common spec keys.
            # Screen size
            m = re.search(r"(\d+(?:[,.]\d+)?)\s*\"", chars)
            if m:
                specs["Экран"] = m.group(1).replace(",", ".") + "\""
            # Camera
            m = re.search(r"(\d+(?:\+\d+)?)\s*МП", chars, re.IGNORECASE)
            if m:
                specs["Камера"] = m.group(1) + " МП"
            # Battery
            m = re.search(r"(\d+)\s*mAh", chars, re.IGNORECASE)
            if m:
                specs["Аккумулятор"] = m.group(1) + " мА·ч"
            # Memory
            m = re.search(r"(\d+(?:/\d+)?)\s*Gb", chars, re.IGNORECASE)
            if m:
                specs["Память"] = m.group(1) + " ГБ"
            # NFC
            if re.search(r"\bNFC\b", chars, re.IGNORECASE):
                specs["NFC"] = "есть"
            # IP rating
            m = re.search(r"IP\s*(\d+[^/\s]*)", chars, re.IGNORECASE)
            if m:
                specs["Защита"] = "IP" + m.group(1)
    return short, specs


def select_products(catalog, limit_per_category: int):
    # Map categories and brands.
    for item in catalog:
        item["site_category"] = map_category(item["category"], item["name"])
        item["brand"] = extract_brand(item["category"], item["name"])
        item["short_description"], item["specs"] = extract_features(item["name"])

    # Deduplicate exact name+price within the same site category to avoid obvious duplicates.
    seen: set[tuple[str, str, int]] = set()
    deduped = []
    for item in catalog:
        key = (item["site_category"], item["name"], item["price_cash"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    selected = []
    counts: dict[str, int] = {}
    for cat in ["smartfony", "aksessuary", "audio", "smart-chasy", "umnyy-dom", "noutbuki"]:
        items = [i for i in deduped if i["site_category"] == cat]
        selected.extend(items[:limit_per_category])
        counts[cat] = len(items[:limit_per_category])
    return selected, counts


def slugify(text: str) -> str:
    # Keep Cyrillic and Latin letters, digits, spaces and dashes.
    base = re.sub(r"[^\w\s-]", "", text).strip().lower()
    base = re.sub(r"\s+", "-", base)
    base = re.sub(r"-+", "-", base)
    return base


def escape_ts_string(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def format_specs(specs: dict[str, str]) -> str:
    if not specs:
        return "    specs: {},"
    lines = ["    specs: {"]
    for k, v in specs.items():
        lines.append(f'      "{escape_ts_string(k)}": "{escape_ts_string(v)}",')
    lines.append("    },")
    return "\n".join(lines)


def generate_products_ts(selected: list, output_path: str, rate: float):
    lines = [
        'import { Product } from "./index";',
        "export type { Product };",
        "",
        "// Products imported from praise_5.xlsx supplier price list.",
        "// Prices are in Belarusian rubles (BYN), converted from Russian rubles (RUB).",
        f"// Conversion rate used: RUB->BYN = {rate}.",
        "export const products: Product[] = [",
    ]

    for idx, item in enumerate(selected):
        name = escape_ts_string(item["name"])
        category = item["site_category"]
        brand = escape_ts_string(item["brand"])
        slug = (slugify(item["name"])[:80] + "-" + str(idx + 1))[:120]
        short = escape_ts_string(item["short_description"])
        specs_block = format_specs(item["specs"])

        # Convert supplier RUB prices to BYN for the catalog.
        price_byn = round(item["price_cash"] * rate * 100) / 100
        price_cashless_byn = round(item["price_cashless"] * rate * 100) / 100

        lines.append("  {")
        lines.append(f'    id: "p{idx + 1}",')
        lines.append(f'    name: "{name}",')
        lines.append(f'    slug: "{slug}",')
        lines.append(f'    category: "{category}",')
        lines.append(f'    brand: "{brand}",')
        lines.append(f'    price: {price_byn},')
        lines.append(f'    oldPrice: {price_cashless_byn},')
        lines.append("    rating: 4.5,")
        lines.append("    reviews: 0,")
        lines.append(f'    image: "{IMAGE_MAP[category]}",')
        lines.append(f'    inStock: {str(item["available"]).lower()},')
        lines.append(f'    shortDescription: "{short}",')
        lines.append('    description: "",')
        lines.append(specs_block)
        lines.append("  },")

    lines.append("];")
    lines.append("")
    lines.append("export function getProductBySlug(slug: string): Product | undefined {")
    lines.append("  return products.find((p) => p.slug === slug);")
    lines.append("}")
    lines.append("")
    lines.append("export function getProductsByCategory(slug: string): Product[] {")
    lines.append("  return products.filter((p) => p.category === slug);")
    lines.append("}")
    lines.append("")
    lines.append("export function getFeaturedProducts(): Product[] {")
    lines.append("  return products.slice(0, 6);")
    lines.append("}")
    lines.append("")
    lines.append("export function searchProducts(query: string): Product[] {")
    lines.append('  const q = query.trim().toLowerCase();')
    lines.append("  if (!q) return [];")
    lines.append("  return products.filter(")
    lines.append("    (p) =>")
    lines.append("      p.name.toLowerCase().includes(q) ||")
    lines.append("      p.brand.toLowerCase().includes(q) ||")
    lines.append("      p.category.toLowerCase().includes(q)")
    lines.append("  );")
    lines.append("}")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    args = parse_args()
    rate = args.rate if args.rate is not None else fetch_rub_to_byn_rate()

    catalog = read_sheet(args.input, args.max_row)
    selected, counts = select_products(catalog, args.limit_per_category)

    print(f"Parsed {len(catalog)} products from {args.input}")
    print(f"Conversion rate: RUB->BYN = {rate}")
    print(f"Selected {len(selected)} products by category: {counts}")

    if args.dry_run:
        return

    generate_products_ts(selected, args.output, rate)
    print(f"Wrote {len(selected)} products to {args.output} (prices in BYN)")


if __name__ == "__main__":
    main()

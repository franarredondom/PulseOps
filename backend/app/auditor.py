from __future__ import annotations

import asyncio
from dataclasses import dataclass
from html.parser import HTMLParser
import re
from time import perf_counter
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from .checker import ensure_public_target

MAX_HTML_BYTES = 2_000_000
MAX_AUXILIARY_BYTES = 256_000
MAX_REDIRECTS = 5
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.7",
    "Accept-Language": "es-CL,es;q=0.9,en;q=0.7",
    "Cache-Control": "no-cache",
}


class AuditError(Exception):
    pass


@dataclass(frozen=True)
class FetchedPage:
    requested_url: str
    final_url: str
    status_code: int
    latency_ms: float
    body: bytes
    headers: dict[str, str]
    redirects: list[str]


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.in_title = False
        self.h1_parts: list[list[str]] = []
        self.current_h1: list[str] | None = None
        self.metas: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.current_link: dict[str, str] | None = None
        self.images: list[dict[str, str]] = []
        self.scripts: list[str] = []
        self.html_lang = ""
        self.canonical = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): (value or "") for key, value in attrs}
        tag = tag.lower()
        if tag == "html":
            self.html_lang = values.get("lang", "").strip()
        elif tag == "title":
            self.in_title = True
        elif tag == "meta":
            self.metas.append(values)
        elif tag == "h1":
            self.current_h1 = []
        elif tag == "a":
            self.current_link = {"href": values.get("href", ""), "text": ""}
            self.links.append(self.current_link)
        elif tag == "img":
            self.images.append(values)
        elif tag == "script":
            self.scripts.append(values.get("src", ""))
        elif tag == "link" and "canonical" in values.get("rel", "").lower().split():
            self.canonical = values.get("href", "").strip()

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "title":
            self.in_title = False
        elif tag == "h1" and self.current_h1 is not None:
            self.h1_parts.append(self.current_h1)
            self.current_h1 = None
        elif tag == "a":
            self.current_link = None

    def handle_data(self, data: str) -> None:
        text = " ".join(data.split())
        if not text:
            return
        if self.in_title:
            self.title_parts.append(text)
        if self.current_h1 is not None:
            self.current_h1.append(text)
        if self.current_link is not None:
            self.current_link["text"] = f'{self.current_link["text"]} {text}'.strip()

    @property
    def title(self) -> str:
        return " ".join(self.title_parts).strip()

    @property
    def h1s(self) -> list[str]:
        return [" ".join(parts).strip() for parts in self.h1_parts if " ".join(parts).strip()]

    def meta(self, key: str) -> str:
        key = key.lower()
        for meta in self.metas:
            if meta.get("name", "").lower() == key or meta.get("property", "").lower() == key:
                return meta.get("content", "").strip()
        return ""


async def _read_limited(response: httpx.Response, limit: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in response.aiter_bytes():
        size += len(chunk)
        if size > limit:
            raise AuditError(f"La página supera el límite de análisis de {limit // 1_000_000 or limit // 1_000} MB")
        chunks.append(chunk)
    return b"".join(chunks)


def looks_like_html(body: bytes) -> bool:
    prefix = body[:16_384].decode("utf-8", errors="ignore").lstrip("\ufeff\x00\t\r\n ").lower()
    return prefix.startswith(("<!doctype html", "<html", "<head", "<body")) or "<html" in prefix[:2_000]


async def fetch_page(raw_url: str) -> FetchedPage:
    current_url = raw_url
    redirects: list[str] = []
    started = perf_counter()
    try:
        async with httpx.AsyncClient(timeout=15, headers=REQUEST_HEADERS) as client:
            redirect_count = 0
            rate_limit_retries = 0
            while redirect_count <= MAX_REDIRECTS:
                await ensure_public_target(current_url)
                async with client.stream("GET", current_url, follow_redirects=False) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise AuditError("La página respondió con una redirección sin destino")
                        current_url = urljoin(current_url, location)
                        if urlparse(current_url).scheme not in {"http", "https"}:
                            raise AuditError("La redirección usa un protocolo no permitido")
                        redirects.append(current_url)
                        redirect_count += 1
                        continue
                    body = await _read_limited(response, MAX_HTML_BYTES)
                    if response.status_code == 429 and rate_limit_retries < 2:
                        retry_after = response.headers.get("retry-after", "")
                        delay = min(4.0, float(retry_after)) if retry_after.replace(".", "", 1).isdigit() else 1.5 * (rate_limit_retries + 1)
                        rate_limit_retries += 1
                        await asyncio.sleep(delay)
                        continue
                    if response.status_code == 429:
                        raise AuditError("El sitio limitó temporalmente las solicitudes del auditor (HTTP 429). Espera un minuto e inténtalo otra vez.")
                    if response.status_code >= 400:
                        raise AuditError(f"El sitio rechazó la visita del auditor con HTTP {response.status_code}")
                    content_type = response.headers.get("content-type", "").lower()
                    declared_html = "text/html" in content_type or "application/xhtml+xml" in content_type
                    if not declared_html and not looks_like_html(body):
                        raise AuditError(f"La URL no entrega una página HTML ({content_type or 'tipo desconocido'})")
                    return FetchedPage(
                        requested_url=raw_url,
                        final_url=str(response.url),
                        status_code=response.status_code,
                        latency_ms=round((perf_counter() - started) * 1000, 2),
                        body=body,
                        headers={key.lower(): value for key, value in response.headers.items()},
                        redirects=redirects,
                    )
            raise AuditError(f"La página supera el máximo de {MAX_REDIRECTS} redirecciones")
    except AuditError:
        raise
    except httpx.TimeoutException as error:
        raise AuditError("La página tardó demasiado en responder") from error
    except (httpx.HTTPError, OSError, ValueError) as error:
        raise AuditError(str(error)[:300]) from error


async def resource_exists(url: str) -> bool:
    try:
        await ensure_public_target(url)
        async with httpx.AsyncClient(timeout=6, headers=REQUEST_HEADERS, follow_redirects=False) as client:
            async with client.stream("GET", url) as response:
                if response.status_code >= 400:
                    return False
                await _read_limited(response, MAX_AUXILIARY_BYTES)
                return True
    except (AuditError, httpx.HTTPError, OSError, ValueError):
        return False


def _clamp(score: float) -> int:
    return max(0, min(100, round(score)))


def _recommend(recommendations: list[dict[str, str]], category: str, severity: str, title: str, detail: str) -> None:
    recommendations.append({"category": category, "severity": severity, "title": title, "detail": detail})


def _technologies(parser: PageParser, html: str, headers: dict[str, str]) -> list[str]:
    haystack = " ".join([html.lower(), " ".join(parser.scripts).lower(), " ".join(f"{key}:{value}" for key, value in headers.items()).lower()])
    signatures = {
        "WordPress": ("wp-content", "wordpress"),
        "React": ("react", "__next_data__"),
        "Next.js": ("/_next/", "__next_data__", "next.js"),
        "Vue": ("vue", "__nuxt__"),
        "Nuxt": ("/_nuxt/", "__nuxt__"),
        "Angular": ("ng-version", "angular"),
        "Shopify": ("cdn.shopify.com", "shopify"),
        "Cloudflare": ("cloudflare", "cf-ray"),
        "Vercel": ("vercel", "x-vercel"),
        "Render": ("render",),
        "nginx": ("nginx",),
    }
    found = [name for name, needles in signatures.items() if any(needle in haystack for needle in needles)]
    generator = parser.meta("generator")
    if generator and generator not in found:
        found.append(generator[:80])
    return found[:12]


def build_report(page: FetchedPage, robots_exists: bool, sitemap_exists: bool) -> dict[str, Any]:
    charset_match = re.search(r"charset\s*=\s*[\"']?([^;\s\"']+)", page.headers.get("content-type", ""), re.IGNORECASE)
    charset = charset_match.group(1) if charset_match else "utf-8"
    try:
        html = page.body.decode(charset, errors="replace")
    except LookupError:
        html = page.body.decode("utf-8", errors="replace")
    parser = PageParser()
    parser.feed(html)
    parsed_final = urlparse(page.final_url)

    meta_description = parser.meta("description")
    viewport = parser.meta("viewport")
    robots_meta = parser.meta("robots")
    og_title = parser.meta("og:title")
    og_description = parser.meta("og:description")
    og_image = parser.meta("og:image")

    internal_links = 0
    external_links = 0
    empty_link_text = 0
    for link in parser.links:
        href = link["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        target = urlparse(urljoin(page.final_url, href))
        if target.hostname == parsed_final.hostname:
            internal_links += 1
        else:
            external_links += 1
        if not link["text"]:
            empty_link_text += 1

    images_with_alt = sum(1 for image in parser.images if "alt" in image and image.get("alt", "").strip())
    secure_headers = {
        "strict-transport-security": "HSTS",
        "content-security-policy": "CSP",
        "x-content-type-options": "X-Content-Type-Options",
        "x-frame-options": "X-Frame-Options",
        "referrer-policy": "Referrer-Policy",
        "permissions-policy": "Permissions-Policy",
    }
    present_headers = [label for header, label in secure_headers.items() if page.headers.get(header)]
    missing_headers = [label for header, label in secure_headers.items() if not page.headers.get(header)]
    is_https = parsed_final.scheme == "https"
    compressed = page.headers.get("content-encoding", "").lower() in {"gzip", "br", "deflate", "zstd"}

    recommendations: list[dict[str, str]] = []

    seo_points = 0
    if parser.title:
        seo_points += 18
        if not 20 <= len(parser.title) <= 65:
            _recommend(recommendations, "SEO", "media", "Ajusta el largo del título", "Procura que tenga entre 20 y 65 caracteres para que sea claro en buscadores.")
    else:
        _recommend(recommendations, "SEO", "alta", "Agrega un título", "La página no tiene una etiqueta <title> detectable.")
    if meta_description:
        seo_points += 17
        if not 70 <= len(meta_description) <= 170:
            _recommend(recommendations, "SEO", "media", "Mejora la meta descripción", "Una descripción de 70 a 170 caracteres suele comunicar mejor el contenido.")
    else:
        _recommend(recommendations, "SEO", "alta", "Agrega una meta descripción", "Ayuda a buscadores y personas a entender la página antes de abrirla.")
    if len(parser.h1s) == 1:
        seo_points += 15
    else:
        _recommend(recommendations, "SEO", "alta" if not parser.h1s else "media", "Usa un H1 principal", f"Se detectaron {len(parser.h1s)} encabezados H1; lo ideal para esta auditoría es uno.")
    if parser.canonical:
        seo_points += 12
    else:
        _recommend(recommendations, "SEO", "media", "Declara una URL canónica", "Evita señales duplicadas indicando la URL principal de la página.")
    seo_points += 10 if robots_exists else 0
    seo_points += 10 if sitemap_exists else 0
    seo_points += 10 if og_title and og_description else 0
    seo_points += 8 if page.status_code < 400 else 0
    if not robots_exists:
        _recommend(recommendations, "SEO", "media", "Publica robots.txt", "No se encontró un archivo robots.txt accesible en el dominio.")
    if not sitemap_exists:
        _recommend(recommendations, "SEO", "media", "Publica sitemap.xml", "No se encontró un sitemap.xml accesible en el dominio.")

    accessibility_points = 0
    if parser.html_lang:
        accessibility_points += 25
    else:
        _recommend(recommendations, "Accesibilidad", "alta", "Define el idioma del documento", "Agrega el atributo lang a la etiqueta <html>.")
    if viewport:
        accessibility_points += 20
    else:
        _recommend(recommendations, "Accesibilidad", "alta", "Configura el viewport móvil", "La página no declara una meta viewport para pantallas pequeñas.")
    if not parser.images or images_with_alt == len(parser.images):
        accessibility_points += 30
    else:
        missing_alt = len(parser.images) - images_with_alt
        _recommend(recommendations, "Accesibilidad", "alta", "Describe las imágenes", f"{missing_alt} de {len(parser.images)} imágenes no tienen texto alternativo útil.")
    if empty_link_text == 0:
        accessibility_points += 15
    else:
        _recommend(recommendations, "Accesibilidad", "media", "Da nombre a los enlaces", f"Se detectaron {empty_link_text} enlaces sin texto visible.")
    accessibility_points += 10 if parser.h1s else 0

    security_points = 20 if is_https else 0
    security_points += round((len(present_headers) / len(secure_headers)) * 75)
    security_points += 5 if not page.headers.get("server") and not page.headers.get("x-powered-by") else 0
    if not is_https:
        _recommend(recommendations, "Seguridad", "alta", "Activa HTTPS", "La URL final no utiliza una conexión cifrada.")
    if missing_headers:
        _recommend(recommendations, "Seguridad", "alta" if len(missing_headers) >= 4 else "media", "Refuerza las cabeceras de seguridad", f"Faltan: {', '.join(missing_headers)}.")

    performance_points = 100
    if page.latency_ms > 3000:
        performance_points -= 45
    elif page.latency_ms > 1500:
        performance_points -= 30
    elif page.latency_ms > 800:
        performance_points -= 15
    if len(page.body) > 1_500_000:
        performance_points -= 30
    elif len(page.body) > 750_000:
        performance_points -= 20
    elif len(page.body) > 350_000:
        performance_points -= 10
    performance_points -= min(20, len(page.redirects) * 5)
    if len(page.body) > 100_000 and not compressed:
        performance_points -= 10
        _recommend(recommendations, "Rendimiento", "media", "Activa compresión HTTP", "El HTML supera 100 KB y no informa gzip, Brotli u otra compresión.")
    if page.latency_ms > 800:
        _recommend(recommendations, "Rendimiento", "alta" if page.latency_ms > 1500 else "media", "Reduce el tiempo de respuesta", f"El servidor tardó {round(page.latency_ms)} ms en entregar el HTML.")
    if len(page.redirects) > 1:
        _recommend(recommendations, "Rendimiento", "media", "Reduce las redirecciones", f"Antes de llegar a la página hubo {len(page.redirects)} redirecciones.")

    scores = {
        "performance": _clamp(performance_points),
        "seo": _clamp(seo_points),
        "accessibility": _clamp(accessibility_points),
        "security": _clamp(security_points),
    }
    scores["overall"] = _clamp(sum(scores.values()) / 4)
    recommendations.sort(key=lambda item: {"alta": 0, "media": 1, "baja": 2}.get(item["severity"], 3))

    return {
        "scores": scores,
        "page": {
            "title": parser.title,
            "description": meta_description,
            "language": parser.html_lang,
            "canonical": parser.canonical,
            "robotsMeta": robots_meta,
            "h1Count": len(parser.h1s),
            "h1": parser.h1s[:5],
        },
        "http": {
            "requestedUrl": page.requested_url,
            "finalUrl": page.final_url,
            "statusCode": page.status_code,
            "latencyMs": page.latency_ms,
            "sizeBytes": len(page.body),
            "redirects": page.redirects,
            "contentType": page.headers.get("content-type", ""),
            "compressed": compressed,
        },
        "seo": {
            "robotsTxt": robots_exists,
            "sitemapXml": sitemap_exists,
            "openGraph": {"title": bool(og_title), "description": bool(og_description), "image": bool(og_image)},
        },
        "content": {
            "images": len(parser.images),
            "imagesWithAlt": images_with_alt,
            "internalLinks": internal_links,
            "externalLinks": external_links,
            "emptyLinkText": empty_link_text,
        },
        "security": {"https": is_https, "presentHeaders": present_headers, "missingHeaders": missing_headers},
        "technologies": _technologies(parser, html, page.headers),
        "recommendations": recommendations[:20],
        "scope": "Auditoría técnica del HTML inicial; no reemplaza Lighthouse ni una revisión manual de accesibilidad.",
    }


async def audit_website(raw_url: str) -> dict[str, Any]:
    page = await fetch_page(raw_url)
    origin = f"{urlparse(page.final_url).scheme}://{urlparse(page.final_url).netloc}"
    robots_exists = await resource_exists(urljoin(origin, "/robots.txt"))
    sitemap_exists = await resource_exists(urljoin(origin, "/sitemap.xml"))
    return build_report(page, robots_exists, sitemap_exists)

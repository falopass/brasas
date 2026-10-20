"""Guarda estática (QA-56): ninguna asignación a innerHTML/outerHTML ni llamada a
insertAdjacentHTML interpola datos con `${}` fuera de una plantilla etiquetada
`html`...`` (que escapa) o de `escapeHtml(...)`. Solo biblioteca estándar: un
escáner carácter a carácter que entiende comentarios, strings y plantillas
anidadas, suficiente para este patrón."""

import re
from pathlib import Path

from backend.settings import ROOT

JS_DIR = ROOT / "web" / "js"
_SINK = re.compile(r"\.(?:inner|outer)HTML\s*\+?=(?!=)|insertAdjacentHTML\s*\(")
_IDENT = re.compile(r"[A-Za-z0-9_$]")


def _hacia_atras(src, i):
    """Nombre de la etiqueta antes de un backtick y si viene de escapeHtml( ... ."""
    j = i - 1
    while j >= 0 and src[j].isspace():
        j -= 1
    k = j
    while k >= 0 and _IDENT.match(src[k]):
        k -= 1
    tag = src[k + 1 : j + 1]
    if tag:  # plantilla etiquetada: html`...`, css`...`, etc.
        return tag, False
    envuelta = False
    if j >= 0 and src[j] == "(":  # escapeHtml(`...`) como expresión completa
        m = j - 1
        while m >= 0 and _IDENT.match(src[m]):
            m -= 1
        envuelta = src[m + 1 : j] == "escapeHtml"
    return None, envuelta


def _cuerpo_escapea(src, i):
    """¿El cuerpo de `${ ... }` empieza con escapeHtml( ?"""
    while i < len(src) and src[i].isspace():
        i += 1
    return src.startswith("escapeHtml", i) and src[i + 10 : i + 12].lstrip().startswith("(")


def violaciones(path):
    """Líneas con `${}` inseguros en sinks de HTML del archivo dado."""
    src = Path(path).read_text(encoding="utf-8")
    linea = 1
    hallazgos = []
    stack = [("code", None)]
    en_sink = False
    i = 0
    while i < len(src):
        c = src[i]
        if c == "\n":
            linea += 1
            i += 1
            continue
        top, meta = stack[-1]
        if top == "tmpl":
            if c == "\\":
                i += 2
                continue
            if c == "`":
                stack.pop()
                i += 1
                continue
            if src.startswith("${", i):
                if en_sink and not any(t == "tmpl" and (m[0] == "html" or m[1]) for t, m in stack) and not _cuerpo_escapea(src, i + 2):
                    hallazgos.append(linea)
                stack.append(("interp", 1))
                i += 2
                continue
            i += 1
            continue
        # estados "code" e "interp": comentarios, strings y plantillas se comportan igual
        if src.startswith("//", i):
            i = src.find("\n", i)
            if i < 0:
                break
            continue
        if src.startswith("/*", i):
            fin = src.find("*/", i + 2)
            linea += src.count("\n", i, fin if fin >= 0 else len(src))
            i = fin + 2 if fin >= 0 else len(src)
            continue
        if c in "'\"":
            fin = i + 1
            while fin < len(src) and src[fin] != c:
                fin += 1 if src[fin] != "\\" else 2
            linea += src.count("\n", i, fin)
            i = fin + 1
            continue
        if c == "`":
            tag, envuelta = _hacia_atras(src, i)
            stack.append(("tmpl", (tag, envuelta)))
            i += 1
            continue
        if top == "interp":
            if c == "{":
                stack[-1] = ("interp", meta + 1)
            elif c == "}":
                if meta == 1:
                    stack.pop()
                else:
                    stack[-1] = ("interp", meta - 1)
            i += 1
            continue
        # code
        m = _SINK.match(src, i)
        if m:
            en_sink = True
            i = m.end()
            continue
        if c == ";":
            en_sink = False
        i += 1
    return hallazgos


def test_vistas_no_interpolan_sin_escapar():
    archivos = sorted(JS_DIR.rglob("*.js"))
    assert archivos, "no se encontró web/js"
    malos = {str(p.relative_to(ROOT)): violaciones(p) for p in archivos}
    malos = {k: v for k, v in malos.items() if v}
    assert not malos, "interpolaciones ${} sin escapar en sinks de HTML (usa html`...` o escapeHtml()): " + "; ".join(
        f"{k} líneas {v}" for k, v in malos.items()
    )

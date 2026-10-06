#!/usr/bin/env python3
"""Genera un feed .ics con los partidos de un equipo a partir de una página de competición de fbpa.es."""
import argparse, hashlib, re, sys, unicodedata
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

DATE_RE = re.compile(r"(\d{2}/\d{2}/\d{4})(?:\s+(\d{1,2}:\d{2}))?")
JORNADA_RE = re.compile(r"Jornada\s+(\d+)\s*-", re.I)
VENUE_ADDR_RE = re.compile(r"^(.*?)\s*\((.+)\)\s*$")
DURATION = timedelta(hours=2)

VTIMEZONE = [
    "BEGIN:VTIMEZONE", "TZID:Europe/Madrid",
    "BEGIN:DAYLIGHT", "TZOFFSETFROM:+0100", "TZOFFSETTO:+0200", "TZNAME:CEST",
    "DTSTART:19700329T020000", "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU", "END:DAYLIGHT",
    "BEGIN:STANDARD", "TZOFFSETFROM:+0200", "TZOFFSETTO:+0100", "TZNAME:CET",
    "DTSTART:19701025T030000", "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU", "END:STANDARD",
    "END:VTIMEZONE",
]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().upper()


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def cells(tr):
    return [clean(td.get_text(" ")) for td in tr.find_all(["td", "th"])]


def parse(html: str):
    soup = BeautifulSoup(html, "html.parser")
    venues, localities, matches = {}, {}, {}

    for table in soup.find_all("table"):
        rows = [cells(tr) for tr in table.find_all("tr")]
        header = [norm(c) for c in rows[0]] if rows else []

        # Tabla de equipos: Equipo | Localidad | ...
        if "LOCALIDAD" in header:
            for r in rows[1:]:
                if len(r) >= 2:
                    localities[norm(r[0])] = re.sub(r"\s*\(.*\)$", "", r[1])
            continue

        # Cualquier celda "PABELLÓN (dirección)" alimenta el mapa de direcciones
        for r in rows:
            for c in r:
                m = VENUE_ADDR_RE.match(c)
                if m and not DATE_RE.search(c):
                    venues[norm(m.group(1))] = clean(m.group(2))

        heading = table.find_previous(string=JORNADA_RE)
        if not heading:
            continue  # "Próximos partidos" / "Resultados de la jornada": ya cubiertos por las jornadas
        jornada = int(JORNADA_RE.search(heading).group(1))

        for r in rows:
            di = next((i for i, c in enumerate(r) if DATE_RE.fullmatch(c)), None)
            if di is None or di < 2:
                continue
            local, visit = r[0], r[di - 1]
            scores = [c for c in r[1:di - 1] if c.isdigit()]
            date_s, time_s = DATE_RE.fullmatch(r[di]).groups()
            campo = r[di + 1] if di + 1 < len(r) else ""
            m = VENUE_ADDR_RE.match(campo)
            if m:
                campo = clean(m.group(1))
            matches[(jornada, norm(local), norm(visit))] = dict(
                jornada=jornada, local=local, visit=visit, date=date_s, time=time_s,
                campo=campo, score="-".join(scores) if len(scores) == 2 else None,
            )
    return list(matches.values()), venues, localities


def esc(s: str) -> str:
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line: str) -> str:
    b, out = line.encode(), []
    while len(b) > 75:
        i = 75
        while b[i] & 0xC0 == 0x80:
            i -= 1
        out.append(b[:i].decode())
        b = b" " + b[i:]
    out.append(b.decode())
    return "\r\n".join(out)


def location(m, venues, localities):
    campo = m["campo"]
    if not campo or re.fullmatch(r"[a\s\-]*", campo, re.I):
        city = localities.get(norm(m["local"]), "")
        return f"Campo por confirmar ({m['local'].title()}{', ' + city if city else ''})"
    addr = venues.get(norm(campo))
    if addr:
        return f"{campo.title()}, {addr}"
    city = localities.get(norm(m["local"]))
    return f"{campo.title()}, {city}" if city else campo.title()


def build_ics(team, url, matches, venues, localities, cal_name):
    t = norm(team)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//fbpa-ics//ES", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", fold(f"X-WR-CALNAME:{esc(cal_name)}"), "X-WR-TIMEZONE:Europe/Madrid",
             "REFRESH-INTERVAL;VALUE=DURATION:PT6H", "X-PUBLISHED-TTL:PT6H", *VTIMEZONE]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    slug = re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")
    n = 0
    for m in sorted(matches, key=lambda x: x["jornada"]):
        if t not in (norm(m["local"]), norm(m["visit"])):
            continue
        if "DESCANSA" in (norm(m["local"]), norm(m["visit"])):
            continue
        home = norm(m["local"]) == t
        rival = m["visit"] if home else m["local"]
        title = f"🏀 {'vs' if home else '@'} {rival}" + (f" ({m['score']})" if m["score"] else "")
        desc = (f"Jornada {m['jornada']}\n{m['local']} vs {m['visit']}"
                + (f"\nResultado: {m['score']}" if m["score"] else "")
                + ("" if m["time"] else "\nHora por confirmar") + f"\n{url}")
        day = datetime.strptime(m["date"], "%d/%m/%Y")
        if m["time"]:
            start = datetime.strptime(f"{m['date']} {m['time']}", "%d/%m/%Y %H:%M")
            when = [f"DTSTART;TZID=Europe/Madrid:{start:%Y%m%dT%H%M%S}",
                    f"DTEND;TZID=Europe/Madrid:{start + DURATION:%Y%m%dT%H%M%S}"]
        else:
            when = [f"DTSTART;VALUE=DATE:{day:%Y%m%d}",
                    f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}"]
        lines += ["BEGIN:VEVENT", f"UID:{slug}-j{m['jornada']}@fbpa-ics", f"DTSTAMP:{stamp}", *when,
                  fold(f"SUMMARY:{esc(title)}"),
                  fold(f"LOCATION:{esc(location(m, venues, localities))}"),
                  fold(f"DESCRIPTION:{esc(desc)}"), "END:VEVENT"]
        n += 1
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n", n


def without_stamp(text: str) -> str:
    return "\n".join(l for l in text.splitlines() if not l.startswith("DTSTAMP:"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--team", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", default=None, help="Nombre del calendario")
    ap.add_argument("--html", help="Leer HTML de un fichero local (pruebas)")
    a = ap.parse_args()

    if a.html:
        html = Path(a.html).read_text(encoding="utf-8")
    else:
        r = requests.get(a.url, timeout=30, headers={"User-Agent": "Mozilla/5.0 (fbpa-ics)"})
        r.raise_for_status()
        r.encoding = r.apparent_encoding or "utf-8"
        html = r.text

    matches, venues, localities = parse(html)
    ics, n = build_ics(a.team, a.url, matches, venues, localities, a.name or a.team.title())
    if n == 0:
        sys.exit(f"ERROR: 0 partidos de '{a.team}' encontrados ({len(matches)} partidos en total). "
                 "¿Ha cambiado la estructura de la web? No se sobrescribe el feed.")

    out = Path(a.out)
    if out.exists() and without_stamp(out.read_text(encoding="utf-8")) == without_stamp(ics):
        print(f"Sin cambios ({n} partidos).")
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(ics, encoding="utf-8", newline="")
    print(f"Actualizado: {n} partidos -> {out} (sha {hashlib.sha1(ics.encode()).hexdigest()[:8]})")


if __name__ == "__main__":
    main()

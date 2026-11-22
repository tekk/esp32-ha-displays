"""Feature pictograms: hand-drawn outline SVGs on a 24×24 grid (stroke 1.5, round caps/joins, no fills).
Writes site/assets/img/features.svg (symbol sprite, ids "f-<icon>", stroke = currentColor) and, with --sheet,
build/pictograms-sheet.html (contact sheet at 16/24/48 px for review)."""
import json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCREEN = '<rect x="3" y="3" width="18" height="11.5" rx="1.5"/>'
HOUSING = '<path d="M3.5 5h17a1 1 0 0 1 1 1v5a1 1 0 0 1-1 1h-17a1 1 0 0 1-1-1V6a1 1 0 0 1 1-1z"/><path d="M9.5 5V3.5h5V5"/><path d="M6.5 8v1M10.17 8v1M13.83 8v1M17.5 8v1"/>'
CHIP = ('<rect x="6" y="4" width="12" height="16" rx="1.5"/>'
        '<path d="M3 8h3M3 12h3M3 16h3M18 8h3M18 12h3M18 16h3"/>')
RJ45 = '<path d="M3.5 4.5h17a1 1 0 0 1 1 1V16a1 1 0 0 1-1 1h-4v2.5a1 1 0 0 1-1 1h-7a1 1 0 0 1-1-1V17h-4a1 1 0 0 1-1-1V5.5a1 1 0 0 1 1-1z"/>'
JACK = '<path d="M13.5 10H4.5a2 2 0 0 0 0 4h9"/><rect x="13.5" y="7.5" width="6.5" height="9" rx="1.25"/><path d="M20 12h2"/>'

ICONS = {
    # storage
    'sd': '<path d="M8 3h7.5L18 5.5V10l-1 1v2l1 1v6a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z"/><path d="M9 5.5v3M11.5 5.5v3M14 5.5v3"/>',
    # memory
    'psram': CHIP + '<path d="M9.5 9h5M9.5 12h5M9.5 15h5"/>',
    'flash': CHIP + '<path d="M12.75 8.5 10.5 12h3l-2.25 3.5"/>',
    # display interfaces (screen + the bus that drives it)
    'disp-spi': SCREEN + '<path d="M3 20h3v-2.5h3V20h3v-2.5h3V20h3v-2.5h3"/>',                 # serial clock / data
    'disp-qspi': SCREEN + '<path d="M6 17v4M10 17v4M14 17v4M18 17v4"/>',                         # 4 data lanes
    'disp-rgb': SCREEN + '<circle cx="7" cy="19" r="1.75"/><circle cx="12" cy="19" r="1.75"/><circle cx="17" cy="19" r="1.75"/>',
    'disp-dsi': SCREEN + '<path d="M7 17v4M9.5 17v4M14.5 17v4M17 17v4"/>',                      # 2 differential lanes
    'disp-8080': SCREEN + '<rect x="4.5" y="17" width="15" height="4" rx="1"/><path d="M8.25 17v4M12 17v4M15.75 17v4"/>',   # wide parallel ribbon
    # touch
    'touch-cap': '<path d="M9.5 21v-3L7.4 15.4a1.45 1.45 0 0 1 2.1-2l1 1V10.5a1.5 1.5 0 0 1 3 0v3.75h2.25a2.25 2.25 0 0 1 2.25 2.25V21"/><path d="M9.17 7.67a4 4 0 0 1 5.66 0"/><path d="M7.05 5.55a7 7 0 0 1 9.9 0"/>',
    'touch-res': '<path d="M16 3.5 19.5 7 10 16.5l-4.25 1.25L7 13.5z"/><path d="M14 5.5 17.5 9"/><path d="M4 21h16"/>',
    # wireless
    'wifi': '<path d="M8.46 15.46a5 5 0 0 1 7.08 0"/><path d="M5.5 12.5a9.2 9.2 0 0 1 13 0"/><path d="M2.5 9.5a13.4 13.4 0 0 1 19 0"/><circle cx="12" cy="19" r="1"/>',
    'wifi6': '<path d="M6.17 16.17a4 4 0 0 1 5.66 0"/><path d="M3.4 13.4a8 8 0 0 1 11.2 0"/><circle cx="9" cy="19" r="1"/>'
             '<circle cx="18.5" cy="9" r="2.5"/><path d="M16 9c0-3.4 1.4-5.2 4-5.5"/>',
    'bt': '<path d="m7 7.5 10 9-5 4.5V3l5 4.5-10 9"/>',
    # usb
    'usb-c': '<rect x="2.5" y="8" width="19" height="8" rx="4"/><path d="M8 12h8"/>',
    'usb-a': '<rect x="3" y="7" width="18" height="10" rx="1"/><rect x="6" y="9.5" width="12" height="2.5" rx=".5"/>',
    # wired / industrial
    'rj45': RJ45 + '<path d="M7.5 4.5V8M10.5 4.5V8M13.5 4.5V8M16.5 4.5V8"/>',
    'poe': RJ45 + '<path d="M13 6.5 10.5 10.5h3.5L11.5 14.5"/>',
    'rs485': '<path d="M2.5 8c4.25 0 5.25 8 9.5 8s5.25-8 9.5-8"/><path d="M2.5 16c4.25 0 5.25-8 9.5-8s5.25 8 9.5 8"/>',   # twisted pair A/B
    'can': '<path d="M2.5 7h19M2.5 10.5h19"/><path d="M6 10.5V15M12 10.5V15M18 10.5V15"/><rect x="4" y="15" width="4" height="4" rx=".75"/><rect x="10" y="15" width="4" height="4" rx=".75"/><rect x="16" y="15" width="4" height="4" rx=".75"/>',
    # i/o
    'jst4': HOUSING + '<path d="M5 16h14l-2-2"/><path d="M19 20H5l2 2"/>',                # 4-pin housing + TX/RX
    'i2c': HOUSING + '<path d="M3 16h18M3 20h18M8 16v4M16 16v4"/>',
    'gpio': '<rect x="2.5" y="6.5" width="19" height="11" rx="1"/><circle cx="6.5" cy="10" r="1.1"/><circle cx="10" cy="10" r="1.1"/><circle cx="14" cy="10" r="1.1"/><circle cx="17.5" cy="10" r="1.1"/>'
            '<circle cx="6.5" cy="14" r="1.1"/><circle cx="10" cy="14" r="1.1"/><circle cx="14" cy="14" r="1.1"/><circle cx="17.5" cy="14" r="1.1"/>',
    'sensor': '<path d="M7.5 13.6V5.5a2 2 0 0 1 4 0v8.1a3.75 3.75 0 1 1-4 0z"/><path d="M9.5 9v7"/><path d="M18 9.5c-1.6 2.1-2.4 3.2-2.4 4.3a2.4 2.4 0 0 0 4.8 0c0-1.1-.8-2.2-2.4-4.3z"/>',
    # audio
    'speaker': '<path d="M3.5 9.5h3.5L11.5 5.5v13L7 14.5H3.5a.5.5 0 0 1-.5-.5v-4a.5.5 0 0 1 .5-.5z"/><path d="M15 9a4.2 4.2 0 0 1 0 6"/><path d="M17.75 6.25a8 8 0 0 1 0 11.5"/>',
    'mic': '<rect x="9" y="2.5" width="6" height="11.5" rx="3"/><path d="M6 11a6 6 0 0 0 12 0"/><path d="M12 17v4M9 21h6"/>',
    'jack-trs': JACK + '<path d="M7 10v4M10.25 10v4"/>',
    'jack-trrs': JACK + '<path d="M6.25 10v4M8.75 10v4M11.25 10v4"/>',
    # camera
    'camera': '<rect x="5.5" y="2.5" width="13" height="12" rx="1.5"/><circle cx="12" cy="8.5" r="3.5"/><circle cx="12" cy="8.5" r="1"/><path d="M9.5 14.5V21h5v-6.5"/><path d="M11 18h2"/>',
    # power
    'battery': '<rect x="2.5" y="7" width="16.5" height="10" rx="1.5"/><path d="M21.5 10.5v3"/><path d="M6.5 12h3.5M8.25 10.25v3.5M13 12h2.5"/>',
    # misc
    'rtc': '<circle cx="12" cy="12" r="8.5"/><path d="M12 7v5l3.25 2"/>',
    'rgbled': '<path d="M8 14V9.5a4 4 0 0 1 8 0V14"/><path d="M6.5 14h11"/><path d="M10 14v6.5M14 14v4.5"/><path d="M12 2v1.5M5.2 4.7l1.1 1.1M18.8 4.7l-1.1 1.1M3 10h1.5M19.5 10H21"/>',
    'relay': '<rect x="7.5" y="2.5" width="9" height="5" rx="1"/><path d="M12 7.5v5" stroke-dasharray="1.5 1.75"/><circle cx="7.5" cy="17" r="1.25"/><circle cx="17" cy="17" r="1.25"/><path d="M8.6 16.3 15.5 12"/><path d="M2.5 17h3.75M18.25 17h3.25"/>',
    'knob': '<circle cx="12" cy="14.5" r="5.5"/><path d="M12 10.5V13"/><path d="M5.64 8.14a9 9 0 0 1 12.72 0"/><path d="m18.36 8.14.1-2.6M18.36 8.14l-2.6.1"/>',
    'vibration': '<rect x="8" y="3.5" width="8" height="17" rx="1.5"/><path d="M11 17.5h2"/><path d="m4.5 7.5-1.5 1.5 1.5 1.5-1.5 1.5 1.5 1.5-1.5 1.5 1.5 1.5"/><path d="m19.5 7.5 1.5 1.5-1.5 1.5 1.5 1.5-1.5 1.5 1.5 1.5-1.5 1.5"/>',
    'buttons': '<rect x="4" y="4" width="16" height="16" rx="2"/><circle cx="12" cy="12" r="4"/><path d="M6.5 6.5h.01M17.5 6.5h.01M6.5 17.5h.01M17.5 17.5h.01"/>',
    'ir': '<path d="M5 15.5V11a3 3 0 0 1 6 0v4.5"/><path d="M3.5 15.5h9M6.5 15.5V20M9.5 15.5V18.5"/><path d="M14.5 8.5a4.5 4.5 0 0 1 0 6.5"/><path d="M17.5 6a8.5 8.5 0 0 1 0 11.5"/>',
    'imu': '<path d="M12 12V3.5M12 12l7.4 4.3M12 12l-7.4 4.3"/><path d="m10 5.5 2-2 2 2"/><path d="m16.6 17.7 2.8-1.4-.6-2.9"/><path d="m5.2 13.4-.6 2.9 2.8 1.4"/>',
    'case': '<path d="M12 3 20 7.5v9L12 21l-8-4.5v-9z"/><path d="m4 7.5 8 4.5 8-4.5M12 12v9"/>',
}
COLORS = {  # category → colour (all ≥ 4.5:1 on #0e0f11, hue-separated)
    'storage': '#4ade80', 'memory': '#fbbf24', 'display': '#60a5fa', 'touch': '#22d3ee', 'wireless': '#a78bfa',
    'usb': '#e2e8f0', 'wired': '#fb923c', 'io': '#e879f9', 'audio': '#f472b6', 'camera': '#f87171',
    'power': '#a3e635', 'misc': '#94a3b8',
}


def sprite():
    out = ['<svg xmlns="http://www.w3.org/2000/svg" style="display:none">',
           '<!-- generated by build/icons.py – outline pictograms, 24×24, stroke 1.5, currentColor -->']
    for k, body in ICONS.items():
        out.append(f'<symbol id="f-{k}" viewBox="0 0 24 24"><g fill="none" stroke="currentColor" stroke-width="1.5" '
                   f'stroke-linecap="round" stroke-linejoin="round">{body}</g></symbol>')
    out.append('</svg>')
    return '\n'.join(out) + '\n'


def main():
    s = sprite()
    p = os.path.join(ROOT, 'site/assets/img/features.svg')
    open(p, 'w').write(s)
    print('icons:', len(ICONS), '→', os.path.relpath(p, ROOT))
    if '--sheet' in sys.argv:
        sys.path.insert(0, os.path.join(ROOT, 'build'))
        from features import DEF
        cat_of = {v[2]: v[0] for v in DEF.values()}
        name_of = {v[2]: v[1] for v in DEF.values()}
        cells = []
        for k in ICONS:
            c = COLORS[cat_of.get(k, 'misc')]
            sv = lambda n: f'<svg width="{n}" height="{n}" style="color:{c}"><use href="#f-{k}"/></svg>'
            cells.append(f'<div class="c"><div class="r">{sv(16)}{sv(24)}{sv(48)}</div><b>{k}</b><i>{name_of.get(k, "")} · {cat_of.get(k, "misc")}</i></div>')
        legend = ''.join(f'<span><i style="background:{v}"></i>{k}</span>' for k, v in COLORS.items())
        html = f'''<!doctype html><meta charset="utf-8"><style>body{{background:#0e0f11;color:#e6e6e6;font:12px/1.3 sans-serif;margin:20px}}
.g{{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}}.c{{background:#16181b;border:1px solid #24272c;border-radius:8px;padding:10px}}
.r{{display:flex;align-items:flex-end;gap:14px;height:52px}}b{{display:block;margin-top:6px}}i{{color:#888;font-style:normal;font-size:11px}}
.lg span{{display:inline-flex;align-items:center;gap:5px;margin:0 12px 10px 0}}.lg i{{width:12px;height:12px;border-radius:3px;display:inline-block}}</style>
{s}<h3>Feature pictograms – 16 / 24 / 48 px</h3><div class="lg">{legend}</div><div class="g">{"".join(cells)}</div>'''
        open(os.path.join(ROOT, 'build/pictograms-sheet.html'), 'w').write(html)


if __name__ == '__main__':
    main()

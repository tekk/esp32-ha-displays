"""Derive a normalized `features` list per board (run after build_site.py; patches site/data/models.json).

Feature = {id, category, name, label, count?, connector?, source}
  - derived only from data we already store: normalized params, the vendor spec rows (specs_raw),
    community pin maps (data/curated/pinouts.json) and hand-verified connector facts (data/curated/features.json)
  - nothing is guessed: a feature is emitted only when a source states it; unclear → omitted
Icons: site/assets/img/features.svg (symbol id = "f-" + icon). Categories drive the colour (CSS)."""
import json, os, re
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, 'site')

# id: (category, short name used for the facet, icon)
DEF = {
    'disp-spi': ('display',  'SPI display',       'disp-spi'),
    'disp-qspi':('display',  'QSPI display',      'disp-qspi'),
    'disp-rgb': ('display',  'RGB display',       'disp-rgb'),
    'disp-dsi': ('display',  'MIPI-DSI display',  'disp-dsi'),
    'disp-8080':('display',  '8080 display',      'disp-8080'),
    'disp-epd': ('display',  'E-paper display',   'disp-epd'),
    'touch-cap':('input',    'Capacitive touch',  'touch-cap'),
    'touch-res':('input',    'Resistive touch',   'touch-res'),
    'psram':    ('psram',    'PSRAM',             'psram'),     # facet name gets the size: "PSRAM 8 MB"
    'flash':    ('flash',    'Flash',             'flash'),     # "Flash 16 MB"
    'sd':       ('storage',  'microSD slot',      'sd'),
    'wifi':     ('wifi',     'Wi-Fi',             'wifi'),      # "Wi-Fi 4" / "Wi-Fi 6"
    'bt':       ('bluetooth','Bluetooth',         'bt'),        # "Bluetooth 5" / "Bluetooth 4.2 + Classic"
    'thread':   ('radio',    'Thread',            'thread'),
    'zigbee':   ('radio',    'Zigbee',            'zigbee'),
    'matter':   ('radio',    'Matter',            'matter'),
    'lora':     ('radio',    'LoRa',              'lora'),
    'gps':      ('radio',    'GNSS / GPS',        'gps'),
    'nfc':      ('radio',    'NFC / RFID',        'nfc'),
    'ir':       ('radio',    'IR',                'ir'),
    'usb-c':    ('usb',      'USB-C',             'usb-c'),
    'usb-a':    ('usb',      'USB-A',             'usb-a'),
    'ethernet': ('wired',    'Ethernet',          'rj45'),
    'poe':      ('wired',    'PoE',               'poe'),
    'rs485':    ('wired',    'RS-485',            'rs485'),
    'can':      ('wired',    'CAN',               'can'),
    'uart':     ('io',       'Serial port',       'jst4'),
    'i2c':      ('io',       'I2C port',          'i2c'),
    'grove':    ('io',       'Grove port',        'grove'),
    'gpio':     ('io',       'GPIO',              'gpio'),
    'sensor':   ('io',       'Sensor port',       'sensor'),
    'relay':    ('io',       'Relay',             'relay'),
    'speaker':  ('audio',    'Speaker',           'speaker'),
    'mic':      ('audio',    'Microphone',        'mic'),
    'jack-trs': ('audio',    '3.5 mm jack',       'jack-trs'),
    'jack-trrs':('audio',    '3.5 mm TRRS jack',  'jack-trrs'),
    'buzzer':   ('audio',    'Buzzer',            'buzzer'),
    'camera':   ('camera',   'Camera',            'camera'),
    'battery':  ('power',    'Battery',           'battery'),
    'charger':  ('power',    'Battery charger',   'charger'),
    'dc-in':    ('power',    'Wide-range DC input','dc-in'),
    'rtc':      ('io',      'RTC',               'rtc'),
    'imu':      ('io',      'IMU',               'imu'),
    'als':      ('io',      'Light / proximity sensor', 'als'),
    'keyboard': ('input',      'Keyboard',          'keyboard'),
    'knob':     ('input',      'Rotary knob',       'knob'),
    'buttons':  ('input',      'Buttons',           'buttons'),
    'vibration':('input',      'Vibration motor',   'vibration'),
    'rgbled':   ('input',      'RGB LED',           'rgbled'),
    'case':     ('io',      'Enclosure',         'case'),
}
CATEGORY_NAMES = {'display': 'Display interface', 'input': 'Touch & controls', 'psram': 'PSRAM', 'flash': 'Flash', 'storage': 'Storage',
                  'wifi': 'Wi-Fi', 'bluetooth': 'Bluetooth', 'radio': 'Thread / Zigbee / Matter / other radios', 'usb': 'USB',
                  'wired': 'Wired / industrial', 'io': 'I/O ports & sensors', 'audio': 'Audio', 'camera': 'Camera', 'power': 'Power'}

# Radio capabilities of Espressif SoCs (official datasheets). Used ONLY to qualify a radio the board vendor states
# (Wi-Fi / Bluetooth present) with its version, and to list 802.15.4 protocols the SoC radio supports.
DS = 'https://www.espressif.com/sites/default/files/documentation/{}_datasheet_en.pdf'
SOC = {
    'ESP32':    dict(wifi='4', wband='2.4 GHz', wstd='802.11 b/g/n', bt='4.2', bdesc='Bluetooth 4.2 BR/EDR (Classic) + BLE', ds=DS.format('esp32')),
    'ESP32-S2': dict(wifi='4', wband='2.4 GHz', wstd='802.11 b/g/n', bt=None, ds=DS.format('esp32-s2')),
    'ESP32-S3': dict(wifi='4', wband='2.4 GHz', wstd='802.11 b/g/n', bt='5', bdesc='Bluetooth 5 (LE)', ds=DS.format('esp32-s3')),
    'ESP32-C3': dict(wifi='4', wband='2.4 GHz', wstd='802.11 b/g/n', bt='5', bdesc='Bluetooth 5 (LE)', ds=DS.format('esp32-c3')),
    'ESP32-C5': dict(wifi='6', wband='dual-band 2.4 + 5 GHz', wstd='802.11ax', bt='5', bdesc='Bluetooth 5 (LE)', r154=True, ds=DS.format('esp32-c5')),
    'ESP32-C6': dict(wifi='6', wband='2.4 GHz', wstd='802.11ax', bt='5.3', bdesc='Bluetooth 5.3 (LE)', r154=True, ds=DS.format('esp32-c6')),
    'ESP32-H2': dict(wifi=None, bt='5.3', bdesc='Bluetooth 5.3 (LE)', r154=True, ds=DS.format('esp32-h2')),
}


def soc_of(text):
    """'ESP32-S3R8' → 'ESP32-S3', 'ESP32-D0WDQ6-V3' / 'ESP32-PICO-D4' → 'ESP32'. Unknown chips (e.g. ESP32-S31) → None."""
    t = (text or '').upper()
    m = re.search(r'ESP32-(S2|S3|C3|C5|C6|H2)(?![0-9])', t)
    if m:
        return 'ESP32-' + m.group(1)
    if re.search(r'ESP32-(D0WD|PICO-D4|PICO-V3|WROOM-32|WROVER|U4WDH|D2WD|SOLO)|^ESP32$|ESP32(?![-\w])', t):
        return 'ESP32'
    return None


ORDER = list(DEF)
GENERIC = None  # set in main()
CONN_RE = re.compile(r'\b(MX|PH|SH|GH|HY|ZH|XH)\s?(\d\.\d+)(?:\s*mm)?[\s-]*(\d+)\s*P(?:in)?\b', re.I)
NEG = re.compile(r'^\s*(no|none|n/?a|-|—|without.*|non-touch.*|not included|optional.*)\s*$', re.I)
PERIPH_LIST = re.compile(r'LED PWM|MCPWM|RMT|TWAI|SDIO 3\.0', re.I)   # MCU peripheral lists, not board connectors


def mb(s):
    m = re.search(r'(\d+(?:\.\d+)?)\s*M(?:B|byte)?\b', s or '', re.I)
    return int(float(m.group(1))) if m else None


def conn(text):
    m = CONN_RE.search(text or '')
    return f'{m.group(1).upper()}{m.group(2)} {m.group(3)}P' if m else None


def derive(m, pinouts, curated):
    p = m['params']
    out = {}

    def add(fid, label, src, count=None, connector=None, value=None, name=None, basis=None):
        if fid in out:
            return
        cat, nm, icon = DEF[fid]
        f = {'id': fid, 'category': cat, 'name': name or nm, 'icon': icon, 'label': label, 'source': src}
        if value:
            f['value'] = str(value)
        if basis:
            f['basis'] = basis
        if count:
            f['count'] = count
        if connector:
            f['connector'] = connector
        out[fid] = f

    raw = [(r['label'].strip(), str(r.get('value') or '').strip(), r.get('source')) for r in m.get('specs_raw', [])]
    src_of = lambda pat: next((s for l, v, s in raw if re.search(pat, l + ' ' + v, re.I)), m['sources'][0] if m.get('sources') else None)
    # items from "port" rows (split lists), skipping MCU peripheral lists
    items = []
    for l, v, s in raw:
        if re.match(r'^(interfaces?|interface type|interface|expansion|i/o ports|additional (features|interfaces?)|storage expansion|storage support|'
                    r'connectivity|audio|power( options| supply)?|sd card.*|tf card.*|camera.*|usb|gpio|available (gpio|i/o)|relay output|operation( interface)?|ethernet|poe|rtc.*|battery)$', l, re.I):
            if PERIPH_LIST.search(v):
                continue
            for it in re.split(r'\s*(?:[,;、，]|\s\+\s|\n)\s*', v):
                if it and not NEG.match(it):
                    items.append((l, it, s))
    has = lambda pat: next(((l, it, s) for l, it, s in items if re.search(pat, it, re.I)), None)

    # storage
    h = has(r'\b(TF|micro ?SD|SD)\b.*(card|slot|interface)|^(TF|SD) card|MicroSD')
    if h or (p.get('sd') and not NEG.match(p['sd'])):
        det = p.get('sd') or ''
        extra = ' (SDIO 3.0)' if 'SDIO' in det else (' – up to 32 GB, FAT32' if re.search(r'32\s*GB', det + ' '.join(i[1] for i in items)) else '')
        add('sd', 'microSD (TF) card slot' + extra, h[2] if h else src_of(r'SD|TF'))
    # memory
    ps = mb(p.get('psram')) if p.get('psram') and not NEG.match(p['psram']) else None
    if ps:
        add('psram', f"{ps} MB PSRAM" + (' (in package)' if re.search('package', p['psram'], re.I) else '') + (' – Octal' if re.search('octal|OPI', p['psram'], re.I) else ' – Quad' if re.search('quad|QSPI', p['psram'], re.I) else ''),
            src_of(r'PSRAM'), value=ps, name=f'PSRAM {ps} MB')
    fl = mb(p.get('flash'))
    if fl:
        add('flash', f"{fl} MB flash" + (' (NOR)' if 'NOR' in (p.get('flash') or '') else ''), src_of(r'flash'), value=fl, name=f'Flash {fl} MB')
    # display interface
    di = (p.get('interface') or '')
    det = p.get('interface_detail') or ''
    if di == 'SPI':
        add('disp-spi', 'SPI display' + (' (4-wire)' if re.search(r'4[- ]?(wire|line|L)', det, re.I) else ''), src_of(r'SPI'))
    elif di == 'QSPI':
        add('disp-qspi', 'QSPI display', src_of(r'QSPI'))
    elif di == 'RGB':
        add('disp-rgb', 'RGB parallel display' + (' (24-bit)' if '24' in det else ''), src_of(r'RGB'))
    elif di == 'MIPI-DSI':
        add('disp-dsi', 'MIPI-DSI display' + (' (2-lane)' if '2-lane' in det else ''), src_of(r'MIPI'))
    elif di.startswith('8080'):
        add('disp-8080', '8080 parallel (MCU) display', src_of(r'8080'))
    # touch
    t = p.get('touch') or ''
    tr = ' '.join(v for l, v, s in raw if re.match(r'touch', l, re.I))
    opt = ' (optional)' if re.search(r'optional', tr, re.I) and not re.search(r'without touch \(optional', tr, re.I) else ''
    ic = re.sub(r'\s*\(.*', '', p.get('touch_ic') or '')
    if t == 'Capacitive':
        add('touch-cap', 'Capacitive touch' + (f' ({ic}' + (f', {p["touch_points"]} points' if p.get('touch_points') else '') + ')' if ic else '') + opt, src_of(r'touch'))
    elif t == 'Resistive':
        add('touch-res', 'Resistive touch' + (' (4-wire)' if '4-wire' in tr else '') + opt, src_of(r'touch'))
    # wireless – presence from the vendor, version from the SoC datasheet (main MCU or radio co-processor)
    w = ' '.join(str(p.get(k) or '') for k in ('wifi', 'connectivity', 'coprocessor')) + ' ' + ' '.join(v for l, v, s in raw if re.match(r'(wi-?fi|wireless|connectivity|co-?processor)', l, re.I))
    main_soc = soc_of(p.get('mcu') or '') or soc_of(p.get('mcu_family') or '')
    co = soc_of(p.get('coprocessor') or '') or (soc_of(w) if soc_of(w) in ('ESP32-C6', 'ESP32-C5') else None)
    rsoc = co if co and (main_soc is None or main_soc == co) else main_soc
    if co and str(p.get('mcu_family') or '').startswith('ESP32-P4'):
        rsoc = co
    via = f' via {co} co-processor' if co and rsoc == co and str(p.get('mcu_family') or '').startswith('ESP32-P4') else ''
    caps = SOC.get(rsoc) if rsoc else None
    wifi_yes = re.search(r'^yes|supported|wi-?fi|2\.4', p.get('wifi') or '', re.I) or re.search(r'wi-?fi', p.get('connectivity') or '', re.I)
    if wifi_yes and not re.match(r'^no', p.get('wifi') or '', re.I):
        if caps and caps.get('wifi'):
            v = caps['wifi']
            add('wifi', f"Wi-Fi {v} ({caps['wstd']}, {caps['wband']}){via} – version from the {rsoc} datasheet", src_of(r'wi-?fi'),
                value=v, name=f'Wi-Fi {v}', basis=caps['ds'])
        elif re.search(r'wi-?fi\s*6|wifi6', w, re.I):
            add('wifi', 'Wi-Fi 6' + (' (2.4 GHz)' if '2.4' in w else '') + ' – as stated by the vendor', src_of(r'wi-?fi'), value='6', name='Wi-Fi 6')
        else:
            add('wifi', 'Wi-Fi' + (' (2.4 GHz)' if '2.4' in w else ''), src_of(r'wi-?fi'))
    b = ' '.join(str(p.get(k) or '') for k in ('bt', 'connectivity')) + ' ' + ' '.join(v for l, v, s in raw if re.match(r'(bluetooth|wireless|connectivity)', l, re.I))
    bt_yes = re.search(r'^yes|supported|bluetooth|ble', (p.get('bt') or '') + ' ' + (p.get('connectivity') or ''), re.I) and not re.match(r'^no', p.get('bt') or '', re.I)
    if bt_yes:
        if caps and caps.get('bt'):
            v = caps['bt']
            add('bt', f"{caps['bdesc']}{via} – version from the {rsoc} datasheet", src_of(r'bluetooth|BLE'), value=v,
                name='Bluetooth ' + v + (' + Classic' if 'Classic' in caps['bdesc'] else ' LE'), basis=caps['ds'])
        else:
            ver = re.search(r'(?:BLE|Bluetooth)\s*(5(?:\.\d)?)', b, re.I)
            add('bt', ('Bluetooth ' + ver.group(1) + (' LE' if re.search(r'BLE|LE\b', b) else '') if ver else 'Bluetooth')
                + (' + Classic' if re.search('classic', b, re.I) else '') + (' – as stated by the vendor' if ver else ''), src_of(r'bluetooth|BLE'),
                value=ver.group(1) if ver else None, name=('Bluetooth ' + ver.group(1)) if ver else None)
    # 802.15.4 can come from the main SoC or any co-processor (e.g. ESP32-S3 + ESP32-H2 on LilyGO T-Panel)
    r154 = next((x for x in (rsoc, co, main_soc) if x and SOC.get(x, {}).get('r154')), None)
    if r154 and r154 != rsoc:
        caps = SOC[r154]
    if r154 and (wifi_yes or bt_yes or co == r154 or re.search(r'thread|zigbee|802\.15\.4', w, re.I)):
        who = f'{r154} co-processor' if r154 != main_soc else r154
        note = f'IEEE 802.15.4 radio of the {who} – SoC capability per the Espressif datasheet; needs firmware support'
        add('thread', f'Thread (802.15.4) – {note}', caps['ds'], basis=caps['ds'])
        add('zigbee', f'Zigbee (802.15.4) – {note}', caps['ds'], basis=caps['ds'])
        add('matter', f'Matter-capable radio (Wi-Fi / Thread) – {who} capability per the Espressif datasheet; firmware-dependent', caps['ds'], basis=caps['ds'])
    # USB (only where stated)
    u = p.get('usb') or ''
    if u:
        nc = len(re.findall(r'Type-C', u)); na = len(re.findall(r'Type-A', u))
        if nc:
            roles = re.findall(r'(USB-to-UART|UART|OTG HS|USB FS)\s*Type-C|Type-C\s*(UART)', u)
            add('usb-c', f'{nc}× USB-C' if nc > 1 else 'USB-C', src_of(r'USB'), nc)
            roles = [x for x in ['USB-to-UART' if 'UART' in u else '', 'USB 2.0 OTG HS' if re.search(r'OTG HS Type-C', u) else '', 'USB FS' if 'USB FS' in u else '',
                                 'USB OTG' if re.search(r'\bOTG\b', u) and 'OTG HS' not in u else '', 'USB-Serial/JTAG' if re.search(r'Serial/JTAG', u, re.I) else ''] if x]
            if roles:
                out['usb-c']['label'] += ' (' + ', '.join(roles) + ')'
        if na:
            add('usb-a', 'USB-A host' + (' (USB 2.0 OTG HS' + (', host mode via jumper' if 'jumper' in u else '') + ')' if 'OTG HS' in u else ''), src_of(r'USB'), na)
    # wired / industrial
    e = p.get('ethernet') or (has(r'RJ45|ethernet') or (None, '', None))[1]
    if e:
        sp = '1000' if re.search(r'1000|gigabit|1\s*G(bps)?\b', e, re.I) else '100' if '100' in e else None
        add('ethernet', 'Ethernet RJ45' + (f' {sp} Mbps' if sp else ''), src_of(r'RJ45|ethernet'), value='1G' if sp == '1000' else sp)
    if p.get('poe'):
        add('poe', 'PoE' + (' – module header (PoE module not included)' if 'not included' in p['poe'] else ''), src_of(r'PoE'))
    if p.get('rs485') or has(r'RS-?485'):
        add('rs485', 'RS-485', src_of(r'RS-?485'))
    if has(r'\bCAN\b'):
        add('can', 'CAN bus', src_of(r'\bCAN\b'))
    # I/O
    h = has(r'^(serial( port| interface)?|uart( serial)?( port)?)$')
    if h or re.search(r'UART', det):
        add('uart', 'Serial port (UART)', h[2] if h else src_of('UART'))
    h = has(r'^I2C')
    if h:
        add('i2c', 'I2C port', h[2])
    g = p.get('gpio') or ''
    h = has(r'GPIO|\bIO\b|I/O|IO port|header|pins$')
    if g:
        add('gpio', 'GPIO header ' + g.replace('40-pin header', '40-pin'), src_of(r'40-pin|GPIO'), 40 if '40-pin' in g else None, '2.54 mm pin header' if '2.54' in g else None)
    elif h:
        n = re.search(r'up to (\d+)', ' '.join(i[1] for i in items), re.I)
        add('gpio', f'GPIO expansion (up to {n.group(1)} I/O)' if n else 'GPIO / IO port expansion', h[2], int(n.group(1)) if n else None)
    h = has(r'DHT11|sensor')
    if h:
        add('sensor', 'DHT11 temperature / humidity sensor port' if 'DHT11' in h[1] else 'Sensor port', h[2])
    # audio
    a = (p.get('audio') or '') + ' ' + ' '.join(v for l, v, s in raw if re.match(r'(audio|additional features|expansion|speaker)', l, re.I))
    sp = re.search(r'yes', p.get('speaker') or '', re.I) or re.search(r'speaker', a, re.I)
    if sp and not m.get('curated_vendor') and not re.match(r'^no', p.get('speaker') or '', re.I):
        cn = conn(a)
        built = re.search(r'built-in speaker', a, re.I)
        drv = re.search(r'speaker driver|codec|amplifier', a, re.I)
        lab = 'Built-in speaker' if built else (('Speaker header' if 'header' in a else 'Speaker interface') + (f' ({cn}' + (', 8 Ω 2 W' if '8Ω 2W' in a else '') + ')' if cn else '')) if (cn or re.search(r'speaker (header|interface|connector)', a + ' ' + ' '.join(l for l, v, s in raw), re.I)) else 'Speaker output'
        if drv and not built and not cn:
            lab += ' (amplifier on board)'
        add('speaker', lab, src_of(r'speaker'), connector=cn)
    mc = re.search(r'(dual|two|2)\s*(built-in\s*)?microphones?', a, re.I)
    if mc:
        add('mic', '2× microphone', src_of(r'microphone'), 2)
    elif re.search(r'microphone', a, re.I):
        add('mic', 'Onboard microphone' if re.search(r'onboard microphone', a, re.I) else 'Microphone', src_of(r'microphone'), 1)
    if re.search(r'TRRS', a):
        add('jack-trrs', '3.5 mm TRRS jack (stereo out + mic in)', src_of('TRRS'))
    elif re.search(r'3\.5\s*mm', a, re.I):
        add('jack-trs', '3.5 mm stereo jack', src_of(r'3\.5'))
    # camera
    cam = p.get('camera') or ''
    if cam and m.get('curated_vendor'):
        add('camera', f'Camera: {cam}', src_of(r'camera|CSI'))
    elif cam:
        lab = 'MIPI-CSI camera connector' + (' (15-pin, 2-lane)' if '15-pin' in cam else ' (2-lane)' if '2-lane' in cam else '')
        if 'OV5647' in cam:
            lab = 'OV5647 5 MP camera (MIPI-CSI 2-lane)'
        if 'ISP' in cam:
            lab = 'MIPI-CSI camera interface with ISP'
        add('camera', lab, src_of(r'camera|CSI'))
    # power
    hb = next(((l, it, s_) for l, it, s_ in items if re.search(r'battery|lithium', it, re.I) and not re.search(r'RTC', l + it)), None)
    bt_ = p.get('battery') or (hb or (None, '', None))[1] or next((v for l, v, s in raw if re.match(r'power (options|supply)|power$', l, re.I) and re.search('lithium|battery', v, re.I)), '')
    if bt_:
        lab = '3.7 V Li-ion battery connector' if 'connector' in bt_ else 'Lithium battery interface' if 'interface' in bt_ else 'Lithium battery support'
        if re.search(r'charg', bt_, re.I) and not re.search('rechargeable', bt_, re.I):
            lab += ' (charging)'
        add('battery', lab, src_of(r'battery|lithium'))
    # misc
    r = p.get('rtc') or next((v for l, v, s in raw if re.match('rtc', l, re.I)), '')
    if r and not NEG.match(r):
        add('rtc', 'RTC' + (' with backup battery holder (rechargeable cell)' if 'holder' in r or 'header' in r else ''), src_of('RTC'))
    h = has(r'RGB-?LED|LED (colou?r )?(light )?strip')
    if h:
        add('rgbled', 'RGB LED strip' if 'strip' in h[1] else 'RGB LED interface', h[2])
    h = next(((l, v, s) for l, v, s in raw if re.match('relay', l, re.I)), None)
    if h:
        n = re.search(r'(\d+)-channel', h[1])
        add('relay', f'{n.group(1)}-channel relay output' if n else 'Relay output', h[2], int(n.group(1)) if n else None)
    if re.search(r'knob', ' '.join(v for l, v, s in raw if re.match(r'(operation|additional features|type)', l, re.I)) + ' ' + m['model'] + ' ' + m.get('title', ''), re.I):
        add('knob', 'Rotary knob (encoder)', src_of('knob'))
    if re.search(r'vibration', a, re.I):
        add('vibration', 'Vibration motor', src_of('vibration'))
    sh = p.get('shell') or ''
    if sh and re.search(r'yes|included|metal', sh, re.I):
        add('case', 'Metal enclosure' if 'metal' in sh.lower() else 'Enclosure / shell', src_of(r'shell|case'))
    # generic normalized params used by the curated vendor files (data/curated/boards/*.json); text = vendor wording
    src0 = m['sources'][0] if m.get('sources') else None
    P = lambda k: (p.get(k) or '').strip() if not NEG.match(p.get(k) or '') else ''
    if P('epaper') or re.search(r'e-?paper|e-?ink|EPD', p.get('panel') or '', re.I):
        add('disp-epd', 'E-paper display' + (f" ({P('epaper')})" if P('epaper') else ''), src_of(r'e-?ink|e-?paper|EPD'))
    for k, fid, lab in (('speaker', 'speaker', 'Speaker'), ('lora', 'lora', 'LoRa'), ('gps', 'gps', 'GNSS / GPS'), ('nfc', 'nfc', 'NFC / RFID'), ('ir', 'ir', 'IR'),
                        ('keyboard', 'keyboard', 'Keyboard'), ('encoder', 'knob', 'Rotary encoder'), ('buzzer', 'buzzer', 'Buzzer'),
                        ('imu', 'imu', 'IMU'), ('als', 'als', 'Light / proximity sensor'), ('charger', 'charger', 'Battery charger'),
                        ('dc_in', 'dc-in', 'DC input'), ('grove', 'grove', 'Grove port'), ('buttons', 'buttons', 'Buttons'),
                        ('rgbled', 'rgbled', 'RGB LED'), ('can', 'can', 'CAN bus'), ('mic', 'mic', 'Microphone'), ('jack', 'jack-trs', '3.5 mm jack'),
                        ('vibration', 'vibration', 'Vibration motor'), ('battery', 'battery', 'Battery'), ('rtc', 'rtc', 'RTC'),
                        ('relay', 'relay', 'Relay'), ('uart', 'uart', 'Serial port (UART)'), ('i2c', 'i2c', 'I2C port')):
        v = P(k)
        if v and GENERIC.get(m['model']):
            if fid == 'jack-trs' and 'TRRS' in v:
                fid = 'jack-trrs'
            n = re.search(r'(\d+)\s*[x×]', v)
            out.pop(fid, None)   # curated vendor wording beats the generic label
            add(fid, f'{lab}: {v}' if not v.lower().startswith(lab.lower().split()[0]) else v, src_of(re.escape(lab.split()[0])) or src0,
                count=int(n.group(1)) if n and int(n.group(1)) > 1 else None, connector=conn(v))
    # community pin maps (curated, sourced)
    for pin in pinouts:
        if not re.search(pin['match'], m['model']):
            continue
        for row in pin['rows']:
            txt = ' '.join(row)
            if re.search(r'RTC\b', row[0]) and 'rtc' not in out:
                add('rtc', 'RTC ' + re.sub(r'^RTC\s*', '', row[0]), pin['source'])
    # hand-verified connector facts override
    for c in curated:
        if re.search(c['match'], m['model']):
            for f in c['features']:
                cat, name, icon = DEF[f['id']]
                out[f['id']] = {'id': f['id'], 'category': cat, 'name': name, 'icon': icon, 'label': f['label'], 'source': c['source'],
                                **({'count': f['count']} if f.get('count') else {}), **({'connector': f['connector']} if f.get('connector') else {})}
    return sorted(out.values(), key=lambda f: ORDER.index(f['id']))


def main():
    mp = os.path.join(SITE, 'data/models.json')
    models = json.load(open(mp))
    pinouts = json.load(open(os.path.join(ROOT, 'data/curated/pinouts.json')))['pinouts']
    cur = json.load(open(os.path.join(ROOT, 'data/curated/features.json')))['entries']
    n = 0
    stats = {}
    global GENERIC
    GENERIC = {m['model']: True for m in models if m.get('curated_vendor')}
    for m in models:
        m['features'] = derive(m, pinouts, cur)
        n += bool(m['features'])
        for f in m['features']:
            stats[f['id']] = stats.get(f['id'], 0) + 1
    json.dump(models, open(mp, 'w'), ensure_ascii=False, separators=(',', ':'))
    json.dump({'models': len(models), 'with_features': n, 'by_feature': stats, 'categories': CATEGORY_NAMES,
               'definitions': {k: {'category': v[0], 'name': v[1], 'icon': v[2]} for k, v in DEF.items()}},
              open(os.path.join(ROOT, 'data/raw/feature_stats.json'), 'w'), indent=1)
    print(f'features: {n}/{len(models)} boards, {sum(stats.values())} features; ' + ', '.join(f'{k} {v}' for k, v in sorted(stats.items(), key=lambda x: -x[1])))


if __name__ == '__main__':
    main()

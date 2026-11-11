#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate RetroArch SDL2 autoconfigs from EmulationStation's es_input.cfg.

Why: the ES bindings are the ones already proven working on this box, while
RetroArch keeps its own database.  Instead of hand-writing (and guessing)
RetroArch configs, translate the ES entries 1:1.

Mapping rules (verified against RetroArch 1.9.0 autoconfig files):
  ES type="button" id=N                  -> input_<t>_btn = "N"
  ES type="hat" id=0 value=1/4/8/2       -> input_<t>_btn = "h0up/down/left/right"
  ES type="axis" id=N value=+1/-1        -> input_<t>_axis = "+N" / "-N"

The output file name MUST be "<deviceName>.cfg" - RetroArch looks the file up
by sanitised device name, which is why the earlier hyphenated names never
loaded.

usage: es2retroarch.py <es_input.cfg> <out_dir>
"""
import re
import sys
import os

if len(sys.argv) < 3:
    sys.exit('usage: es2retroarch.py <es_input.cfg> <out_dir>')
SRC = sys.argv[1]
OUTDIR = sys.argv[2]

# ES input name -> RetroArch binding suffix
BTN = {
    'a': 'a', 'b': 'b', 'x': 'x', 'y': 'y',
    'leftshoulder': 'l', 'rightshoulder': 'r',
    'select': 'select', 'start': 'start',
    'hotkeyenable': 'enable_hotkey',
    'leftthumb': 'l3', 'rightthumb': 'r3',
    # ES page keys have no RetroArch equivalent; L/R is the closest useful
    # binding (page flip in lists).
    'pageup': 'l', 'pagedown': 'r',
}
AX = {
    'up': 'up', 'down': 'down', 'left': 'left', 'right': 'right',
    'leftanalogup': 'l_y_minus', 'leftanalogdown': 'l_y_plus',
    'leftanalogleft': 'l_x_minus', 'leftanalogright': 'l_x_plus',
    'rightanalogup': 'r_y_minus', 'rightanalogdown': 'r_y_plus',
    'rightanalogleft': 'r_x_minus', 'rightanalogright': 'r_x_plus',
    'lefttrigger': 'l2', 'righttrigger': 'r2',
}
HATDIR = {'1': 'h0up', '4': 'h0down', '8': 'h0left', '2': 'h0right'}
# hat-type entries in ES carry the direction name itself
HATBTN = {'up': 'up', 'down': 'down', 'left': 'left', 'right': 'right'}

txt = open(SRC, 'r', errors='replace').read()
blocks = re.findall(r'<inputConfig\b([^>]*)>(.*?)</inputConfig>', txt, re.S)
print('inputConfig entries: %d' % len(blocks))

made = 0
for attrs, body in blocks:
    m = re.search(r'deviceName="([^"]*)"', attrs)
    if not m:
        continue
    name = m.group(1)
    guid = re.search(r'deviceGUID="([^"]*)"', attrs)
    guid = guid.group(1) if guid else ''

    lines = ['input_driver = "sdl2"',
             'input_device = "%s"' % name]
    if guid:
        # also match by VID/PID: GUID = bus(2)+0+vendor(2)+0+product(2)+0+version(2)+0,
        # all 16-bit little-endian hex words.
        try:
            b = bytes.fromhex(guid)
            vendor = b[4] | (b[5] << 8)
            product = b[8] | (b[9] << 8)
            lines.append('input_vendor_id = "%d"' % vendor)
            lines.append('input_product_id = "%d"' % product)
        except ValueError:
            pass

    for im in re.finditer(
            r'<input\s+name="([^"]+)"\s+type="(button|hat|axis)"\s+id="(\d+)"\s+value="(-?\d+)"', body):
        iname, itype, iid, ival = im.group(1), im.group(2), im.group(3), int(im.group(4))
        if itype == 'button':
            t = BTN.get(iname)
            if t:
                lines.append('input_%s_btn = "%s"' % (t, iid))
        elif itype == 'hat':
            t = HATBTN.get(iname) or BTN.get(iname)
            d = HATDIR.get(str(ival))
            if t and d:
                lines.append('input_%s_btn = "%s"' % (t, d))
        else:  # axis
            t = AX.get(iname)
            if t:
                sign = '+' if ival > 0 else '-'
                lines.append('input_%s_axis = "%s%s"' % (t, sign, iid))

    # RetroArch label fields keep the OSD readable
    for lab in ('a', 'b', 'x', 'y'):
        if any(l.startswith('input_%s_btn' % lab) for l in lines):
            lines.append('input_%s_btn_label = "%s"' % (lab, lab.upper()))

    path = os.path.join(OUTDIR, name + '.cfg')
    with open(path, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    print('  wrote %-46s (%d bindings)' % (name + '.cfg', len(lines) - 2))
    made += 1
print('done, %d config(s) in %s' % (made, OUTDIR))

"""Draw the Sofa Link pixel-art logo.

Writes assets/logo.svg (README), web/logo.svg (page header, no backdrop or
tagline) and web/icon.svg (tab icon). Pass a path to also write a PNG preview
of the README logo.
"""
import zlib, struct, sys
U = 4  # px per unit
W, H = 252, 62
rects = []
def r(x, y, w, h, c): rects.append((x, y, w, h, c))
BG, PANEL, BORDER, TEXT, MUTED, GREEN = '#0c1216', '#141e24', '#2b3b45', '#edf3f5', '#91a4ad', '#bdf179'
P = ['#bdf179', '#5ec8ff', '#ff6b8b', '#ffd166']
def mix(c, t):
    a = [int(c[i:i+2], 16) for i in (1, 3, 5)]; b = [int(BG[i:i+2], 16) for i in (1, 3, 5)]
    return '#' + ''.join('%02x' % round(b[k] + (a[k]-b[k])*t) for k in range(3))
F = {
 'B':["11110","10001","10001","11110","10001","10001","11110"],
 'R':["11110","10001","10001","11110","10100","10010","10001"],
 'O':["01110","10001","10001","10001","10001","10001","01110"],
 'W':["10001","10001","10001","10101","10101","10101","01010"],
 'S':["01111","10000","10000","01110","00001","00001","11110"],
 'E':["11111","10000","10000","11110","10000","10000","11111"],
 'C':["01110","10001","10000","10000","10000","10001","01110"],
 'U':["10001","10001","10001","10001","10001","10001","01110"],
 'H':["10001","10001","10001","11111","10001","10001","10001"],
 'I':["11111","00100","00100","00100","00100","00100","11111"],
 'N':["10001","11001","10101","10011","10001","10001","10001"],
 'A':["01110","10001","10001","11111","10001","10001","10001"],
 'F':["11111","10000","10000","11110","10000","10000","10000"],
 'L':["10000","10000","10000","10000","10000","10000","11111"],
 'K':["10001","10010","10100","11000","10100","10010","10001"],
 'M':["10001","11011","10101","10101","10001","10001","10001"],
 'Y':["10001","10001","01010","00100","00100","00100","00100"],
 'T':["11111","00100","00100","00100","00100","00100","00100"],
 'P':["11110","10001","10001","11110","10000","10000","10000"],
 '-':["00000","00000","00000","11111","00000","00000","00000"],
 ' ':["00000"]*7,
 '1':["00100","01100","00100","00100","01110"], '2':["11110","00001","01110","10000","11111"],
 '3':["11110","00001","00110","00001","11110"], '4':["10010","10010","11111","00010","00010"],
}
def text(s, x, y, s_, c, gap=1):
    for ch in s:
        g = F[ch]
        for j, row in enumerate(g):
            for i, b in enumerate(row):
                if b == '1': r(x+i*s_, y+j*s_, s_, s_, c)
        x += (len(g[0])+gap)*s_
    return x
# backdrop with stepped corners
r(2, 0, W-4, H, BG); r(1, 1, W-2, H-2, BG); r(0, 2, W, H-4, BG)
# browser window
wx, wy, ww, wh = 6, 3, 48, 46
r(wx, wy, ww, wh, BORDER)
r(wx+1, wy+1, ww-2, 5, PANEL)
for k, c in enumerate(['#ff5f57', '#febc2e', '#28c840']): r(wx+2+k*3, wy+3, 2, 2, c)
r(wx+12, wy+2, 16, 4, '#1c2a32'); r(wx+12, wy+5, 16, 1, GREEN)
sx, sy = wx+1, wy+6; qw, qh = 22, 18
quads = [(sx, sy), (sx+qw+2, sy), (sx, sy+qh+2), (sx+qw+2, sy+qh+2)]
r(sx, sy, ww-2, wh-7, BG)
for n, (qx, qy) in enumerate(quads):
    c = P[n]
    h = qh if n < 2 else wh-7-qh-2
    r(qx, qy, qw, h, mix(c, .16))
    hz = qy + 10
    r(qx, hz, qw, 1, mix(c, .45))              # horizon
    for k in range(1, qw-2, 4): r(qx+k+(n % 2)*2, hz+3, 2, 1, mix(c, .35))  # road dashes
    text(str(n+1), qx+2, qy+2, 1, c)
    cx = qx+12 - (n % 2)*3
    r(cx+2, hz-4, 3, 1, c); r(cx, hz-3, 7, 2, c); r(cx+5, hz-3, 1, 1, mix(c, .5))
    r(cx+1, hz-1, 2, 1, BORDER); r(cx+4, hz-1, 2, 1, BORDER)  # little racer
# couch, from behind, with four player heads
heads = [10, 21, 32, 43]
for n, hx in enumerate(heads):
    c = P[n]
    r(hx-1, 38, 7, 8, BG)                       # outline
    r(hx, 39, 5, 7, c); r(hx, 39, 1, 1, BG); r(hx+4, 39, 1, 1, BG)
    r(hx+1, 40, 3, 1, mix(c, .7))                # hair shine
COUCH, COUCH_D, COUCH_L = '#e0703f', '#a84a2a', '#f39a62'
r(2, 45, 56, 13, BG)                            # outline behind couch
r(4, 46, 52, 7, COUCH); r(4, 46, 52, 1, COUCH_L)
for k in (17, 30, 43): r(k, 47, 1, 6, COUCH_D)   # cushion seams
r(3, 49, 4, 8, COUCH_D); r(53, 49, 4, 8, COUCH_D)  # arms
r(3, 49, 4, 1, COUCH); r(53, 49, 4, 1, COUCH)
r(7, 53, 46, 4, COUCH_D)
r(6, 57, 2, 2, BORDER); r(52, 57, 2, 2, BORDER)  # legs
# wordmark
tx = 66
text('SOFA', tx, 4, 3, TEXT)
end = text('LINK', tx, 28, 3, GREEN)
text('COUCH MULTIPLAYER IN A BROWSER', tx, 53, 1, MUTED)
for n, c in enumerate(P): r(end+2+n*7, 44, 5, 5, c)   # player pips after LINK
# --- outputs
BACKDROP = 3      # the first rects are the rounded backdrop
TAGLINE = [t for t in rects if t[4] == MUTED]
def write(path, items, box, size_scale=U):
    x0, y0, w, h = box
    out = ['<svg xmlns="http://www.w3.org/2000/svg" viewBox="%d %d %d %d" width="%d" height="%d" shape-rendering="crispEdges" role="img" aria-label="Sofa Link">' % (x0, y0, w, h, w*size_scale, h*size_scale),
           '<title>Sofa Link</title>']
    out += ['<rect x="%d" y="%d" width="%d" height="%d" fill="%s"/>' % t for t in items]
    out.append('</svg>')
    open(path, 'w').write('\n'.join(out)+'\n')
write('assets/logo.svg', rects, (0, 0, W, H))
web = [t for t in rects[BACKDROP:] if t not in TAGLINE]
right = max(x+w for x, y, w, h, c in web) + 1
write('web/logo.svg', web, (1, 2, right-1, H-3), 1)
write('web/icon.svg', [t for t in rects[BACKDROP:] if t[0] < 60], (0, 0, 60, 62), 1)
# PNG preview, only when a path is given
if len(sys.argv) < 2: sys.exit()
S = U*2
img = [[(255, 255, 255, 0)]*(W*S) for _ in range(H*S)]
for x, y, w, h, c in rects:
    col = tuple(int(c[i:i+2], 16) for i in (1, 3, 5)) + (255,)
    for yy in range(max(0, y*S), min(H*S, (y+h)*S)):
        row = img[yy]
        for xx in range(max(0, x*S), min(W*S, (x+w)*S)): row[xx] = col
raw = b''.join(b'\0' + bytes(v for p in row for v in p) for row in img)
def chunk(t, d): return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t+d) & 0xffffffff)
png = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', W*S, H*S, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw, 9)) + chunk(b'IEND', b'')
open(sys.argv[1], 'wb').write(png)

import fitz
import sys

doc = fitz.open('file_118.pdf')
page = doc[0]

for block in page.get_text('dict').get('blocks', []):
    if block.get('type') != 0: continue
    for line in block.get('lines', []):
        text = ' '.join(s['text'] for s in line['spans']).strip()
        if not text: continue
        bbox = line['bbox']
        tl = text.lower()
        if 'wildan' in tl or 'diset' in tl or 'pemohon' in tl or 'diperiksa' in tl:
            cx = (bbox[0]+bbox[2])/2
            print(f"{text} x0:{bbox[0]:.1f} x1:{bbox[2]:.1f} cx:{cx:.1f} yt:{bbox[1]:.1f} yb:{bbox[3]:.1f}")

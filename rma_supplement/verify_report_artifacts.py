"""Render every report page, check extracted bounds, and verify immutable inputs."""
from pathlib import Path
import argparse
import hashlib
import json
import fitz
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'outputs/rma_supplement_report_20261007'
SRC = ROOT/'outputs/results_20261007_211507_31272'
QA = ROOT/'tmp/pdfs/rma_supplement_report_qa'


def main(visual_reviewed=False):
    QA.mkdir(parents=True, exist_ok=True)
    pdf = OUT/'SW39000_RMA补充实验数据报告_大图版.pdf'
    doc = fitz.open(pdf)
    assert len(doc) == 20
    alltext = ''
    for i, page in enumerate(doc):
        assert abs(page.rect.width-841.8898)<.1 and abs(page.rect.height-595.2756)<.1
        txt = page.get_text()
        assert '第 '+str(i+1)+' 页' in txt
        assert '\ufffd' not in txt
        alltext += txt
        for block in page.get_text('blocks'):
            if block[6] == 0:
                # CJK glyph ink can extend beyond the paragraph advance box.
                assert block[0] >= 24 and block[2] <= page.rect.width-24, (i+1,block)
                assert block[1] >= 20 and block[3] <= page.rect.height-9, (i+1,block)
        page.get_pixmap(matrix=fitz.Matrix(1.35,1.35), alpha=False).save(str(QA/f'page_{i+1:02}.png'))
    for g in range(41):
        assert f'g{g:04}' in alltext, g
    for begin in (0, 10):
        thumbw, thumbh = 560, 410
        sheet = Image.new('RGB', (thumbw*2,thumbh*5), 'white')
        pen = ImageDraw.Draw(sheet)
        for k in range(10):
            i=begin+k
            im=Image.open(QA/f'page_{i+1:02}.png')
            im.thumbnail((540,380))
            x=(k%2)*thumbw+10; y=(k//2)*thumbh+20
            sheet.paste(im,(x,y)); pen.text((x,y-16),f'Page {i+1}',fill='black')
        sheet.save(QA/f'contact_{begin+1:02}_{begin+10:02}.png')
    audit=json.loads((OUT/'audit.json').read_text(encoding='utf-8'))
    manifest={v['file']:v['sha256'] for v in audit['source_manifest']}
    actual={p.relative_to(SRC).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in SRC.rglob('*') if p.is_file()}
    assert actual == manifest, 'Original inputs changed'
    result=dict(pages=len(doc), figures=13, all_41_groups_present=True, text_bounds_valid=True,
                source_files_unchanged=len(actual), pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
                visual_review='passed: all 20 pages inspected' if visual_reviewed else 'pending', qa_directory=str(QA))
    (OUT/'qa_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--visual-reviewed',action='store_true',help='Record completed manual review of all rendered pages')
    main(ap.parse_args().visual_reviewed)

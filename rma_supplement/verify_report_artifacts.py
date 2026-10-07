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
ROUTE_SRC = ROOT/'results_route_20261007_223701_6654'
QA = ROOT/'tmp/pdfs/rma_supplement_report_qa'


def main(visual_reviewed=False):
    QA.mkdir(parents=True, exist_ok=True)
    pdf = OUT/'SW39000_RMA补充实验数据报告_大图版.pdf'
    doc = fitz.open(pdf)
    assert len(doc) == 34
    old_render_hashes={i:hashlib.sha256((QA/f'page_{i:02}.png').read_bytes()).hexdigest()
                       for i in range(2,21) if i!=16 and (QA/f'page_{i:02}.png').exists()}
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
    for g in range(64):
        assert f'R-g{g:04}' in alltext,g
    assert '尚未上机' not in alltext
    assert len(list((OUT/'图表').glob('图*.png')))==20
    for label in ('vn027164','vn027140','38.085','21.372','13.891','31.417'):
        assert label in alltext,label
    for begin in range(0,len(doc),10):
        n=min(10,len(doc)-begin)
        thumbw, thumbh = 560, 410
        sheet = Image.new('RGB', (thumbw*2,thumbh*((n+1)//2)), 'white')
        pen = ImageDraw.Draw(sheet)
        for k in range(n):
            i=begin+k
            im=Image.open(QA/f'page_{i+1:02}.png')
            im.thumbnail((540,380))
            x=(k%2)*thumbw+10; y=(k//2)*thumbh+20
            sheet.paste(im,(x,y)); pen.text((x,y-16),f'Page {i+1}',fill='black')
        sheet.save(QA/f'contact_{begin+1:02}_{begin+n:02}.png')
    audit=json.loads((OUT/'audit.json').read_text(encoding='utf-8'))
    manifest={v['file']:v['sha256'] for v in audit['source_manifest']}
    actual={p.relative_to(SRC).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in SRC.rglob('*') if p.is_file()}
    assert actual == manifest, 'Original inputs changed'
    route_audit=json.loads((OUT/'route_audit.json').read_text(encoding='utf-8'))
    route_manifest={v['file']:v['sha256'] for v in route_audit['source_manifest']}
    route_actual={p.relative_to(ROUTE_SRC).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in ROUTE_SRC.rglob('*') if p.is_file()}
    assert route_actual==route_manifest,'Route inputs changed'
    unchanged_pages=[i for i,h in old_render_hashes.items() if hashlib.sha256((QA/f'page_{i:02}.png').read_bytes()).hexdigest()==h]
    result=dict(pages=len(doc), figures=20, all_41_quick_and_64_route_groups_present=True, text_bounds_valid=True,
                source_files_unchanged=len(actual), pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
                route_source_files_unchanged=len(route_actual),original_unchanged_pages_render_match=unchanged_pages,
                visual_review='passed: changed pages inspected and unchanged pages compared' if visual_reviewed else 'pending',qa_directory=str(QA))
    (OUT/'qa_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('--visual-reviewed',action='store_true',help='Record completed manual review of all rendered pages')
    main(ap.parse_args().visual_reviewed)

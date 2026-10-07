from pathlib import Path
import json
import pdfplumber
from pypdf import PdfReader

root=Path(__file__).resolve().parents[3]
target=root/'outputs/rma_report_20261006/SW39000_RMA测试数据报告_大图版.pdf'
reader=PdfReader(target)
assert len(reader.pages)==17
texts=[p.extract_text() for p in reader.pages]
for i,text in enumerate(texts,1):
    assert len(text)>150, f'Unexpectedly empty page {i}'
    assert f'第 {i} 页' in text, f'Missing page number {i}'
    assert '\ufffd' not in text, f'Replacement character {i}'
alltext='\n'.join(texts)
for required in ['72576','1242','384','1698','102.0025','24.499247','14.999048','4.374042','98.480','3.965','4.355','SHA-256','vn024481']:
    assert required in alltext, required
with pdfplumber.open(target) as doc:
    for i,page in enumerate(doc.pages,1):
        assert abs(page.width-841.89)<.1 and abs(page.height-595.276)<.1
        for ch in page.chars:
            # ReportLab CJK paragraphs allow punctuation to hang slightly beyond
            # the 34 pt body margin; require at least 24 pt clear page margin.
            assert ch['x0']>=24 and ch['x1']<=page.width-24, (i,ch)
            assert ch['top']>=30 and ch['bottom']<page.height-7, (i,ch)
out={'pages':len(texts),'font_and_text_checks':'passed','page_bounds':'passed','required_measurements':'passed','bytes':target.stat().st_size}
Path(__file__).with_name('verification.json').write_text(json.dumps(out,indent=2),encoding='utf-8')
Path(__file__).with_name('report_text.txt').write_text(alltext,encoding='utf-8')
print(out)

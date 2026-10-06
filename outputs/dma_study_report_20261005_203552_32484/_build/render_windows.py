"""Native Word conversion followed by the packaged DOCX renderer's page QA."""
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import win32com.client
OUT=Path(__file__).resolve().parents[1]
SKILL=Path('C:/Users/lenovo/.codex/plugins/cache/openai-primary-runtime/documents/26.905.11957/skills/documents')
DEPS=Path('C:/Users/lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies')
os.environ['PATH']=str(next((DEPS/'native/poppler').rglob('pdftoppm.exe')).parent)+os.pathsep+os.environ.get('PATH','')
spec=importlib.util.spec_from_file_location('docx_renderer',SKILL/'render_docx.py')
renderer=importlib.util.module_from_spec(spec);spec.loader.exec_module(renderer)
def convert_word(doc_path,user_profile,convert_tmp_dir,stem,verbose):
    target=str(Path(convert_tmp_dir)/'word-render.pdf')
    app=win32com.client.DispatchEx('Word.Application');app.Visible=False;app.DisplayAlerts=0;opened=None
    try:
        opened=app.Documents.Open(str(Path(doc_path).resolve()),ReadOnly=True,AddToRecentFiles=False)
        opened.Repaginate();opened.ExportAsFixedFormat(target,17)
    finally:
        if opened is not None:opened.Close(False)
        app.Quit()
    return target,'Native Word PDF export on Windows.'
renderer.convert_to_pdf=convert_word
docx=OUT/'SW39000_DMA测试数据报告_大图版.docx';qa=OUT/'_qa_senior_final'
sys.argv=['render_docx.py',str(docx),'--output_dir',str(qa),'--dpi','150','--emit_pdf']
renderer.main();shutil.copy2(qa/(docx.stem+'.pdf'),OUT/(docx.stem+'.pdf'))

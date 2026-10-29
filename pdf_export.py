"""Isolated, bounded HTML-to-PDF rendering. No document URL resources are fetched."""
from pathlib import Path
import subprocess
import sys
import tempfile

CSS = '''
@page { size: A4; margin: 20mm 18mm 22mm;
  @bottom-right { content: counter(page) " / " counter(pages); font: 9pt sans-serif; color: #68736b; }
}
body { font: 10.5pt/1.6 "DejaVu Sans", "Droid Sans Fallback", sans-serif; color: #26342f; overflow-wrap: anywhere; }
.document-label { font-size: 9pt; color: #68736b; border-bottom: 1px solid #dce3dd; padding-bottom: 8pt; margin-bottom: 18pt; }
h1,h2,h3,h4,h5,h6 { line-height: 1.25; break-after: avoid; color: #244c42; }
h1 { font-size: 23pt; } h2 { font-size: 17pt; } h3 { font-size: 13pt; }
p,li { orphans: 3; widows: 3; } a { color: #285c51; } u { text-decoration: underline; }
pre,code { font-family: "DejaVu Sans Mono", monospace; font-size: 9pt; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; background: #f2f5ef; border: 1px solid #dce3dd; padding: 9pt; }
code { background: #f2f5ef; } blockquote { border-left: 3pt solid #c6d5c7; margin-left: 0; padding-left: 12pt; color: #52634f; }
table { border-collapse: collapse; width: 100%; table-layout: fixed; margin: 12pt 0; font-size: 9pt; }
th,td { border: 1px solid #dce3dd; padding: 6pt; overflow-wrap: anywhere; vertical-align: top; }
th { background: #edf3e9; text-align: left; } thead { display: table-header-group; }
hr { border: 0; border-top: 1px solid #dce3dd; margin: 16pt 0; }
'''


def generate(html):
    with tempfile.TemporaryDirectory(prefix='margin-pdf-') as directory:
        output = Path(directory)/'document.pdf'
        subprocess.run([sys.executable, str(Path(__file__).resolve()), str(output)],
                       input=html.encode('utf-8'), stdout=subprocess.DEVNULL,
                       stderr=subprocess.PIPE, timeout=45, check=True)
        content = output.read_bytes()
        if not content.startswith(b'%PDF-'):
            raise ValueError('The converter did not produce a PDF.')
        return content


def render_worker(output):
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (512*1024*1024, 512*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU, (30, 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64*1024*1024, 64*1024*1024))
    from weasyprint import HTML, CSS as Stylesheet
    from weasyprint.urls import URLFetcher

    class NoResources(URLFetcher):
        def fetch(self, url, headers=None):
            raise ValueError('Document resource fetching is disabled.')

    fetcher = NoResources()
    HTML(string=sys.stdin.read(), url_fetcher=fetcher).write_pdf(
        output, stylesheets=[Stylesheet(string=CSS, url_fetcher=fetcher)])


if __name__ == '__main__':
    render_worker(sys.argv[1])

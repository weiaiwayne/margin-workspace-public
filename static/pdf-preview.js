// Local rendering only: no document scripts, forms, links, or remote viewer service.
let current=null;
window.stopPdfPreview=()=>{if(current){current.stopped=true;current.render?.cancel();current.task?.destroy().catch(()=>{});current=null;}};
window.showPdfPreview=async(url,container)=>{
  window.stopPdfPreview();
  const session={stopped:false,task:null,render:null};current=session;
  const controls=document.createElement('div');controls.className='pdf-controls';
  const previous=document.createElement('button');previous.className='secondary';previous.textContent='← Previous page';previous.id='pdf-previous';
  const next=document.createElement('button');next.className='secondary';next.textContent='Next page →';next.id='pdf-next';
  const status=document.createElement('span');status.id='pdf-status';status.setAttribute('role','status');status.textContent='Loading PDF…';
  const canvas=document.createElement('canvas');canvas.id='pdf-canvas';canvas.setAttribute('role','img');canvas.setAttribute('aria-label','PDF page preview');
  const accessible=document.createElement('details');const summary=document.createElement('summary');summary.textContent='Page text';const pageText=document.createElement('pre');pageText.className='pdf-page-text';accessible.append(summary,pageText);
  controls.append(previous,status,next);container.append(controls,canvas,accessible);previous.disabled=next.disabled=true;
  try{
    const pdfjs=await import('./vendor/pdfjs/build/pdf.mjs');if(session.stopped)return;
    const assets=new URL('static/vendor/pdfjs/',document.baseURI);
    pdfjs.GlobalWorkerOptions.workerSrc=new URL('build/pdf.worker.mjs',assets).href;
    session.task=pdfjs.getDocument({url,isEvalSupported:false,enableXfa:false,useWasm:false,wasmUrl:new URL('wasm/',assets).href,cMapUrl:new URL('cmaps/',assets).href,cMapPacked:true,standardFontDataUrl:new URL('standard_fonts/',assets).href});
    const pdf=await session.task.promise;if(session.stopped)return;
    let number=1;
    async function render(){
      previous.disabled=next.disabled=true;status.textContent='Loading page '+number+'…';
      try{
        const page=await pdf.getPage(number);if(session.stopped)return;
        const natural=page.getViewport({scale:1});
        const scale=Math.min(2,Math.max(0.1,(container.clientWidth-4)/natural.width));
        // Bound raster size even for pathological page dimensions.
        const viewport=page.getViewport({scale:Math.min(scale,Math.sqrt(8000000/(natural.width*natural.height)))});
        canvas.width=Math.ceil(viewport.width);canvas.height=Math.ceil(viewport.height);
        session.render=page.render({canvasContext:canvas.getContext('2d'),viewport});await session.render.promise;if(session.stopped)return;
        const text=await page.getTextContent();if(session.stopped)return;
        pageText.textContent=text.items.map(item=>item.str+(item.hasEOL?'\n':' ')).join('');
        canvas.setAttribute('aria-label','PDF page '+number+' of '+pdf.numPages);status.textContent='Page '+number+' of '+pdf.numPages;
        previous.disabled=number<=1;next.disabled=number>=pdf.numPages;
      }catch(error){if(!session.stopped){status.textContent='Unable to render this page. Use Download to open the original PDF.';previous.disabled=number<=1;next.disabled=number>=pdf.numPages;}}
    }
    previous.onclick=()=>{number--;void render();};next.onclick=()=>{number++;void render();};
    await render();
  }catch(error){if(!session.stopped)status.textContent=error.name==='PasswordException'?'This PDF is password-protected. Download it to open with your PDF reader.':'Unable to preview this PDF. Use Download to open it.';}
};

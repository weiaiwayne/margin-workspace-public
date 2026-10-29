'use strict';
const $ = id => document.getElementById(id);
const mobileLayout = matchMedia('(max-width:900px)');
const state = {user:null,csrf:null,projects:[],project:null,files:[],folders:[],writable:null,fileKind:null,source:'',path:null,revision:null,comments:[],folder:null,onlyReviews:false,allThreads:false,quote:'',section:'',reply:null,drafts:new Map(),setup:null,load:0};
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const date = value => new Date(typeof value === 'number' ? value*1000 : value).toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'});
const initials = name => name.split(/\s+/).map(x=>x[0]).slice(0,2).join('').toUpperCase();
function toast(message,error=false){$('toast').textContent=message;$('toast').className='toast'+(error?' error-toast':'');clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').classList.add('hidden'),6000);}
async function api(path,body){const response=await fetch('api/'+path,{cache:'no-store',method:body===undefined?'GET':'POST',headers:body===undefined?{}:{'Content-Type':'application/json','X-CSRF-Token':state.csrf||''},body:body===undefined?undefined:JSON.stringify(body)});let result;try{result=await response.json();}catch{throw Error('The server is temporarily unavailable. Please try again.');}if(!response.ok){if(response.status===401 && !['login','activate'].includes(path))showAuth();const error=Error(result.error||'Request failed.');error.status=response.status;throw error;}return result;}
function on(id,event,handler){$(id).addEventListener(event,async e=>{try{await handler(e);}catch(error){toast(error.message,true);}});}
function showAuth(){setSidebar(false);window.stopPdfPreview();hideSelectionAction();if(!state.setup){$('auth-title').textContent='Welcome back.';$('auth-description').textContent='Sign in to pick up where you left off.';$('username-label').classList.remove('hidden');$('username').required=true;$('password').minLength=1;$('password').autocomplete='current-password';$('login-submit').textContent='Sign in';}state.user=null;$('workspace').classList.add('hidden');$('auth').classList.remove('hidden');}
function saveDraft(){if(state.path)state.drafts.set(state.project+':'+state.path,{body:$('comment-body').value,quote:state.quote,section:state.section,reply:state.reply});}
function setQuote(){const exists=!!state.quote;$('quote-preview').classList.toggle('hidden',!exists);$('quote-text').textContent=state.quote;$('compose-label').textContent=state.reply?'Reply to thread #'+state.reply:'Add your perspective';$('post-button').textContent=state.reply?'Post reply':'Post comment';}
function restoreDraft(){const d=state.drafts.get(state.project+':'+state.path)||{};$('comment-body').value=d.body||'';state.quote=d.quote||'';state.section=d.section||'';state.reply=d.reply||null;setQuote();}
async function enter(session){state.user=session.user;state.csrf=session.csrf;$('auth').classList.add('hidden');$('workspace').classList.remove('hidden');$('user-name').textContent=state.user.name;$('user-avatar').textContent=initials(state.user.name);$('user-role').textContent=state.user.admin?'Workspace administrator':'Collaborator';$('team-button').classList.toggle('hidden',!state.user.admin);const result=await api('projects');updateProjects(result);if(!state.projects.length){$('file-list').innerHTML='<div class="empty"><strong>Your workspace is ready.</strong>Ask your administrator to give you access to a project.</div>';$('file-count').textContent='0';return;}let hash=new URLSearchParams(location.hash.slice(1));const wanted=hash.get('project');state.project=state.projects.some(p=>p.id===wanted)?wanted:state.projects[0].id;$('project-select').value=state.project;await loadProject();if(hash.get('file'))await openDocument(hash.get('file'));}
async function loadProject(){
  const pid=state.project,sequence=(state.projectLoad||0)+1;state.projectLoad=sequence;state.projectLoading=true;state.projectReady=false;
  state.folder=null;state.onlyReviews=false;state.files=[];state.folders=[];state.writable=null;
  const p=state.projects.find(p=>p.id===pid);$('project-name').textContent=p?.name||'Workspace';
  $('search').value='';renderFolders();renderFiles();$('library').classList.add('hidden');$('reader').classList.add('hidden');
  $('workspace-status').textContent='Connecting '+(p?.name||'workspace')+' to its server folder…';
  $('storage-summary').textContent='Checking storage…';$('storage-meter').classList.add('hidden');$('storage-detail').textContent='';
  const current=()=>state.project===pid&&state.projectLoad===sequence&&!!state.user;
  try{
    if(!await waitForWorkspace(pid,current))return;
    if(!current())return;
    state.projectReady=true;renderFolders();showLibrary(false);
    const project=state.projects.find(p=>p.id===pid);
    $('workspace-status').textContent='Folder connected · '+(project.server_path||project.name);
  }catch(error){if(current())$('workspace-status').textContent=error.message;throw error;}
  finally{if(state.projectLoad===sequence)state.projectLoading=false;}
}
async function refreshFiles(){
  const project=state.project,user=state.user,sequence=(state.fileRequest||0)+1;
  state.fileRequest=sequence;
  const result=await api('files?project='+encodeURIComponent(project));
  if(state.project!==project||state.user!==user||state.fileRequest!==sequence)return;
  const changed=JSON.stringify([state.files,state.folders,state.writable])!==JSON.stringify([result.files,result.folders,result.writable_directory]);
  state.files=result.files;state.folders=result.folders||[];state.writable=result.writable_directory;
  if(changed){renderFolders();renderFiles();}
  void refreshStorage(project);
}
let workspaceRefreshPending=false;
async function refreshWorkspace(){
  if(!state.user||!state.project||document.hidden||state.projectLoading||!state.projectReady||workspaceRefreshPending)return;
  workspaceRefreshPending=true;
  try{await refreshFiles();await pollComments();}
  catch(error){/* A transient background failure must not discard a review draft. */}
  finally{workspaceRefreshPending=false;}
}
function chooseFolder(path){saveDraft();state.folder=path;state.onlyReviews=false;showLibrary();renderFolders();}
function folderLabel(path){return path==='.'?'Project root':path;}
function renderFolders(){
  const navigation=$('folders').closest('.sidebar-navigation'),scrollTop=navigation.scrollTop;
  $('folders').replaceChildren();
  for(const folder of [{path:'.'},...state.folders]){
    const button=document.createElement('button');button.classList.toggle('active',state.folder===folder.path);
    const count=state.files.filter(f=>f.folder===folder.path).length;
    button.innerHTML='<span aria-hidden="true">▱</span><span>'+escape(folderLabel(folder.path))+'</span><small>'+count+'</small>';
    button.onclick=()=>chooseFolder(folder.path);attachFolderMenu(button,folder.path);appendItemActions($('folders'),button,'sidebar-folder-entry','Actions for '+folderLabel(folder.path),(trigger,x,y)=>showFolderMenu(trigger,folder.path,x,y));
  }
  navigation.scrollTop=scrollTop;
  $('file-count').textContent=state.files.length;$('review-count').textContent=state.files.reduce((a,f)=>a+f.comments,0);
}
function renderFiles(){
  const query=$('search').value.toLowerCase();
  let files=state.files.filter(f=>(!state.folder||f.folder===state.folder)&&(!state.onlyReviews||f.comments>0)&&f.path.toLowerCase().includes(query));
  const sort=$('sort').value;files.sort((a,b)=>sort==='recent'?b.modified-a.modified:sort==='comments'?b.comments-a.comments:a.name.localeCompare(b.name));
  $('file-list').replaceChildren();
  for(const f of files){
    const button=document.createElement('button');button.className='file-row';button.title=f.path;
    const kind=f.kind||'md',label={md:'Markdown',txt:'Plain text',pdf:'PDF',file:'File'}[kind];
    button.innerHTML='<span class="file-cell"><span class="file-icon">'+kind.toUpperCase()+'</span><span class="file-name">'+escape(f.name)+'<small>'+label+' · '+(f.size<1024?f.size+' B':Math.ceil(f.size/1024)+' KB')+'</small></span></span><span class="folder-cell">'+escape(folderLabel(f.folder))+'</span><span class="date-cell">'+date(f.modified)+'</span><span class="discussion-cell">'+(f.comments?'<span class="discussion-count">◌ &nbsp;'+f.comments+' open</span>':'—')+'</span>';
    button.onclick=()=>openDocument(f.path).catch(e=>toast(e.message,true));attachFileMenu(button,f);appendItemActions($('file-list'),button,'file-entry','Actions for '+f.name,(trigger,x,y)=>showFileMenu(trigger,f,x,y));
  }
  const parent=state.folder||'.';
  const children=state.onlyReviews?[]:state.folders.filter(f=>(f.path.includes('/')?f.path.slice(0,f.path.lastIndexOf('/')):'.')===parent&&f.path.toLowerCase().includes(query));
  $('folder-grid').replaceChildren();
  for(const folder of children){const button=document.createElement('button');button.className='folder-card';button.textContent='▱ '+folder.path.split('/').pop();button.onclick=()=>chooseFolder(folder.path);attachFolderMenu(button,folder.path);appendItemActions($('folder-grid'),button,'folder-entry','Actions for '+folder.path.split('/').pop(),(trigger,x,y)=>showFolderMenu(trigger,folder.path,x,y));}
  if(!files.length)$('file-list').innerHTML='<div class="empty"><strong>'+(state.onlyReviews?'All caught up.':children.length?'Choose a folder above.':'No files here yet.')+'</strong>'+(state.onlyReviews?'No open discussions match this view.':'Upload files or create a document in the shared workspace.')+'</div>';
  $('result-count').textContent=files.length+' file'+(files.length===1?'':'s');
  $('library-title').textContent=state.onlyReviews?'Open discussions':state.folder?folderLabel(state.folder):'All documents';
  $('library-description').textContent=state.onlyReviews?'The conversations waiting for your perspective.':'Browse project documents and organize shared files. Use the ··· menu or right-click for actions.';
  $('all-documents').classList.toggle('active',!state.onlyReviews&&!state.folder);$('open-reviews').classList.toggle('active',state.onlyReviews);
  $('folder-up').classList.toggle('hidden',!state.folder);
  for(const id of ['upload-button','new-folder','new-md','new-txt'])$(id).disabled=!state.writable||(id==='upload-button'&&uploadPending)||(['new-md','new-txt'].includes(id)&&documentCreating);
  $('upload-destination').textContent=state.writable?'Uploads and new documents go to '+writeFolder()+' · Uploads use available workspace storage':'This project is read-only.';
}
function joinPath(folder,name){return folder==='.'?name:folder+'/'+name;}
function writeFolder(){if(state.writable==='.')return state.folder||'.';return state.folder&&(state.folder===state.writable||state.folder.startsWith(state.writable+'/'))?state.folder:state.writable;}
function fileURL(endpoint,path=state.path){return 'api/'+endpoint+'?project='+encodeURIComponent(state.project)+'&path='+encodeURIComponent(path);}
function showLibrary(updateHash=true){if(!leaveDocumentEditor())return;window.stopPdfPreview();$('file-preview').replaceChildren();hideSelectionAction();saveDraft();state.path=null;state.load++;$('reader').classList.add('hidden');$('library').classList.remove('hidden');setSidebar(false);renderFiles();if(updateHash)history.replaceState(null,'','#project='+encodeURIComponent(state.project));void refreshWorkspace();}
async function openDocument(path){
  if(!leaveDocumentEditor())return;
  hideSelectionAction();saveDraft();const seq=++state.load;
  let file=state.files.find(f=>f.path===path);
  if(!file){await refreshFiles();file=state.files.find(f=>f.path===path);}
  if(!file)throw Error('This file was moved or is no longer available. Refresh the workspace.');
  const kind=file.kind||'md',reviewable=['md','txt'].includes(kind)&&file.size<=2*1024*1024;
  const result=reviewable?await api('document?project='+encodeURIComponent(state.project)+'&path='+encodeURIComponent(path)):null;
  if(seq!==state.load)return;
  state.path=path;state.fileKind=reviewable?kind:'file';state.source=result?.source||'';state.revision=result?.revision||null;state.comments=result?.comments||[];state.allThreads=false;state.lastComments=null;
  $('library').classList.add('hidden');$('reader').classList.remove('hidden');setComments(reviewable&&!mobileLayout.matches);setSidebar(false);
  const titleEditable=file.writable&&reviewable;
  $('document-title').classList.toggle('hidden',!titleEditable);$('document-title').value=file.name;$('document-name').classList.toggle('hidden',titleEditable);
  $('document-name').textContent=file.name;$('document-date').textContent='Updated '+date(file.modified);$('document-type').textContent={md:'MARKDOWN DOCUMENT',txt:'TEXT DOCUMENT',pdf:'PDF DOCUMENT',file:'SHARED FILE'}[kind];
  $('document').innerHTML=result?.html||'';$('document').classList.toggle('hidden',!reviewable);
  window.stopPdfPreview();$('file-preview').replaceChildren();$('file-preview').classList.toggle('hidden',reviewable);
  $('reader').classList.toggle('file-only',!reviewable);
  $('download-file').href=fileURL('download');$('edit-file').classList.toggle('hidden',!(file.editable??file.writable)||!reviewable);
  for(const id of ['rename-file','trash-file'])$(id).classList.toggle('hidden',!file.writable);
  $('version-history').classList.toggle('hidden',!reviewable);
  for(const id of ['comments-toggle','export-button'])$(id).classList.toggle('hidden',!reviewable);
  document.querySelector('.agent-handoff').classList.toggle('hidden',!reviewable);
  if(!reviewable){
    if(kind==='pdf'){
      void window.showPdfPreview(fileURL('pdf'),$('file-preview'));
    }else{const note=document.createElement('p');note.textContent='Preview is not available for this file type. Use Download to save a copy.';$('file-preview').append(note);}
  }
  $('changed-banner').classList.add('hidden');$('document').parentElement.scrollTop=0;restoreDraft();renderComments();if(result)renderExport(result.export);
  history.replaceState(null,'','#project='+encodeURIComponent(state.project)+'&file='+encodeURIComponent(path));document.title=file.name+' · Margin';
}
function renderExport(result){
  const root=result.project_root||state.projects.find(p=>p.id===state.project)?.server_path||'.';
  $('agent-prompt').value='Work in the project folder `'+root+'`. Read the latest revised document `'+state.path+'` and its review file `'+result.file+'`. The document contains direct human edits; use that saved version as the starting point and preserve those edits. Apply the open comments to the document and, where requested, to the implementation. Verify quoted passages against the current document because earlier comments may refer to an older version. Preserve resolved review history. Do not modify the generated review file. If either file is unreadable, stop and report the exact path and error; an unreadable review means the comment count is unknown, not zero. Use the local agent identity assigned to this workspace and ensure the workspace root, including .reviews, is within your sandbox access. Do not change permissions or request access to unrelated workspaces. Report the changes made, the comments addressed, and any unresolved questions. Document SHA-256 at this handoff: '+result.revision+'.';
  $('export-state').textContent=result.dirty?'● Feedback not yet saved to project':result.exported?'✓ Saved to project · '+date(result.exported):'Comments are saved in this workspace.';
  $('export-button').title='Export to '+result.file;
}
function renderComments(){const fingerprint=JSON.stringify([state.comments,state.allThreads,state.revision]);if(fingerprint===state.lastComments)return;state.lastComments=fingerprint;$('threads').replaceChildren();const roots=state.comments.filter(c=>c.parent_id===null);const open=roots.filter(c=>!c.resolved);$('comment-count').textContent=open.length;$('filter-open').classList.toggle('active',!state.allThreads);$('filter-all').classList.toggle('active',state.allThreads);const visible=state.allThreads?roots:open;for(const c of visible){const card=document.createElement('div');card.className='thread'+(c.resolved?' resolved':'');card.dataset.commentId=c.id;card.tabIndex=0;card.setAttribute('aria-label','Comment by '+c.name+(c.quote?'. Show quoted passage':''));card.addEventListener('click',event=>{if(!event.target.closest('button,a'))revealPassage(c);});card.addEventListener('keydown',event=>{if(event.target===card&&['Enter',' '].includes(event.key)){event.preventDefault();revealPassage(c);}});card.innerHTML='<div class="thread-head"><span class="avatar">'+escape(initials(c.name))+'</span><span><strong>'+escape(c.name)+'</strong><time>'+date(c.created)+'</time></span>'+(c.resolved?'<span class="thread-status">✓ Resolved</span>':'')+'</div>'+(c.quote?'<blockquote class="thread-quote">'+escape(c.quote)+'</blockquote>':'')+(c.revision!==state.revision?'<p class="stale">Source changed since this comment. Check the passage.</p>':'')+'<p class="thread-body">'+escape(c.body)+'</p>';for(const reply of state.comments.filter(r=>r.parent_id===c.id)){const part=document.createElement('div');part.className='reply';part.innerHTML='<small><strong>'+escape(reply.name)+'</strong> · '+date(reply.created)+'</small><p>'+escape(reply.body)+'</p>';card.append(part);}const actions=document.createElement('div');actions.className='thread-actions';if(!c.resolved){const reply=document.createElement('button');reply.textContent='↳ Reply';reply.onclick=()=>{state.reply=c.id;state.quote=c.quote;state.section=c.section;setQuote();$('comment-body').focus();$('comment-form').scrollIntoView({block:'nearest'});};actions.append(reply);}const resolve=document.createElement('button');resolve.textContent=c.resolved?'Reopen thread':'✓ Resolve';resolve.onclick=async()=>{resolve.disabled=true;try{await api('comments/'+c.id+'/resolve',{resolved:!c.resolved});await pollComments();}catch(e){toast(e.message,true);}finally{resolve.disabled=false;}};actions.append(resolve);card.append(actions);$('threads').append(card);}if(!visible.length)$('threads').innerHTML='<div class="empty"><strong>'+(roots.length?'All caught up.':'Room for your thoughts.')+'</strong>'+(roots.length?'No open threads on this document.':'Be the first to start a conversation.')+'</div>';const file=state.files.find(f=>f.path===state.path);if(file)file.comments=open.length;renderFolders();}
async function pollComments(){if(!state.user||!state.path||!['md','txt'].includes(state.fileKind)||document.hidden)return;const project=state.project,path=state.path;const result=await api('comments?project='+encodeURIComponent(project)+'&path='+encodeURIComponent(path));if(project!==state.project||path!==state.path)return;state.comments=result.comments;$('changed-banner').classList.toggle('hidden',result.revision===state.revision);renderComments();renderExport(result.export);}
function openModal(title,html){$('modal-title').textContent=title;$('modal-content').innerHTML=html;$('modal').showModal();}
function inviteLink(token){return location.origin+location.pathname+'#setup='+token;}
function showInvite(token){let area=$('invite-result');if(!area){area=document.createElement('div');area.id='invite-result';$('modal-content').prepend(area);}area.className='invite-output';area.replaceChildren();const p=document.createElement('p');p.textContent='Share this private, one-time setup link directly with your colleague. It expires in 3 days.';const input=document.createElement('input');input.value=inviteLink(token);input.readOnly=true;input.setAttribute('aria-label','One-time account setup link');const copy=document.createElement('button');copy.className='secondary';copy.textContent='Copy setup link';copy.onclick=async()=>{try{await navigator.clipboard.writeText(input.value);copy.textContent='Copied';}catch{input.select();toast('Select and copy the setup link.');}};area.append(p,input,copy);}
async function team(){const result=await api('users');openModal('People & access','<p class="modal-note">Invite trusted collaborators. Each person can read, edit documents and comment on the projects you choose.</p><div id="team-list"></div><hr class="modal-divider"><h3>Invite a colleague</h3><form id="invite-form" class="modal-form"><label>Full name<input name="name" required maxlength="100" autocomplete="off"></label><label>Username<input name="username" required minlength="3" maxlength="48" pattern="[a-zA-Z0-9][a-zA-Z0-9._-]{2,47}" autocomplete="off"></label><fieldset><legend>Project access</legend>'+state.projects.filter(p=>!p.private).map(p=>'<label><input type="checkbox" name="project" value="'+escape(p.id)+'" checked>'+escape(p.name)+'</label>').join('')+'</fieldset><button class="primary">Create invitation</button></form>');for(const user of result.users){const row=document.createElement('div');row.className='user-row';row.innerHTML='<span><strong>'+escape(user.name)+'</strong><small>@'+escape(user.username)+' · '+(user.admin?'Administrator':!user.active?'Disabled':user.activated?'Collaborator':'Invitation pending')+'</small></span>';const actions=document.createElement('span');actions.className='user-actions';if(user.id!==state.user.id){const reset=document.createElement('button');reset.textContent=user.active?'Reset access':'Reactivate';reset.onclick=async()=>{if(!confirm('Reset sign-in for '+user.name+'? Existing sessions will end.'))return;try{const r=await api('users/'+user.id,{action:'reset'});showInvite(r.token);}catch(e){toast(e.message,true);}};actions.append(reset);if(user.active){const access=document.createElement('button');access.textContent='Projects';access.onclick=()=>{const box=document.createElement('form');box.className='modal-form';box.innerHTML='<fieldset><legend>Access for '+escape(user.name)+'</legend>'+state.projects.filter(p=>!p.private).map(p=>'<label><input type="checkbox" name="project" value="'+escape(p.id)+'" '+(user.projects.includes(p.id)?'checked':'')+'>'+escape(p.name)+'</label>').join('')+'</fieldset><button class="secondary">Save access</button>';box.onsubmit=async e=>{e.preventDefault();try{await api('users/'+user.id,{action:'access',projects:[...box.querySelectorAll('input:checked')].map(x=>x.value)});user.projects=[...box.querySelectorAll('input:checked')].map(x=>x.value);box.remove();toast('Project access updated.');}catch(error){toast(error.message,true);}};row.after(box);};actions.append(access);const disable=document.createElement('button');disable.textContent='Disable';disable.onclick=async()=>{if(!confirm('Remove '+user.name+'’s access and end their sessions?'))return;try{await api('users/'+user.id,{action:'disable'});$('modal').close();await team();}catch(e){toast(e.message,true);}};actions.append(disable);}}row.append(actions);$('team-list').append(row);}$('invite-form').onsubmit=async e=>{e.preventDefault();const form=e.currentTarget;const button=form.querySelector('button');button.disabled=true;try{const r=await api('users',{name:form.elements.name.value,username:form.elements.username.value,projects:[...form.querySelectorAll('input[name="project"]:checked')].map(x=>x.value)});form.reset();showInvite(r.token);toast('Invitation created for '+r.username+'.');}catch(error){toast(error.message,true);}finally{button.disabled=false;}};}
on('login-form','submit',async e=>{e.preventDefault();$('auth-error').textContent='';$('login-submit').disabled=true;try{const result=await api(state.setup?'activate':'login',state.setup?{token:state.setup,password:$('password').value}:{username:$('username').value,password:$('password').value});state.setup=null;$('password').value='';await enter(result);}catch(error){$('auth-error').textContent=error.message;}finally{$('login-submit').disabled=false;}});
on('project-select','change',async()=>{if(!leaveDocumentEditor()){$('project-select').value=state.project;return;}saveDraft();state.path=null;state.project=$('project-select').value;history.replaceState(null,'','#project='+encodeURIComponent(state.project));await loadProject();});
on('all-documents','click',()=>{state.folder=null;state.onlyReviews=false;showLibrary();renderFolders();});
on('open-reviews','click',()=>{state.folder=null;state.onlyReviews=true;showLibrary();renderFolders();});
on('search','input',renderFiles);on('sort','change',renderFiles);
on('back-button','click',()=>{showLibrary();document.title='Margin · Document workspace';});
on('menu-button','click',()=>setSidebar(!$('sidebar').classList.contains('visible')));
on('close-sidebar','click',()=>setSidebar(false,true));
on('sidebar-backdrop','click',()=>setSidebar(false,true));
mobileLayout.addEventListener('change',()=>{setSidebar(false);if(mobileLayout.matches)setComments(false);});
on('refresh-button','click',async()=>{if(!state.projectReady){await loadProject();return;}await refreshFiles();if(state.path)await pollComments();toast('Workspace refreshed.');});
on('reload-document','click',async()=>{if(state.path){await openDocument(state.path);toast('Latest document loaded.');}});
on('comments-toggle','click',()=>setComments($('reader').classList.contains('no-comments')));
on('close-comments','click',()=>{setComments(false);$('comments-toggle').focus();});
on('save-comments-mobile','click',()=>$('export-button').click());
on('document-more','click',()=>{const button=$('document-more'),rect=button.getBoundingClientRect();const actions=[];for(const [id,label] of [['download-file','Download'],['rename-file','Rename…'],['version-history','History'],['reload-document','Reload document'],['export-button','Save comments to project'],['trash-file','Move to Trash']]){const target=$(id);if(!target.classList.contains('hidden')&&!target.disabled)actions.push([label,()=>target.click(),id==='trash-file']);}if(state.path?.toLowerCase().endsWith('.md'))actions.push(['Download as PDF',()=>downloadMarkdownPdf(state.path)]);showItemMenu(button,'Document actions',actions,rect.left,rect.bottom);});
on('filter-open','click',()=>{state.allThreads=false;renderComments();});on('filter-all','click',()=>{state.allThreads=true;renderComments();});
on('clear-quote','click',()=>{state.quote='';state.section='';state.reply=null;setQuote();});
on('comment-body','input',saveDraft);
on('comment-form','submit',async e=>{e.preventDefault();await saveDocumentEdits();if(documentDirty())throw Error('Save the remaining document edits before posting this comment.');if(!$('comment-body').value.trim()){toast('Write a comment first.',true);return;}const pid=state.project,path=state.path;$('post-button').disabled=true;try{await api('comments',{project:pid,path,revision:state.revision,body:$('comment-body').value,quote:state.quote,section:state.section,parent_id:state.reply});state.drafts.delete(pid+':'+path);if(state.project===pid&&state.path===path){$('comment-body').value='';state.quote='';state.section='';state.reply=null;setQuote();await pollComments();}toast('Comment posted.');}finally{$('post-button').disabled=false;}});
on('copy-agent-prompt','click',async()=>{
  if($('comment-body').value.trim())throw Error('Post your draft comment before copying the agent prompt.');
  let handoffProject,handoffPath;
  $('copy-agent-prompt').disabled=true;
  try{await saveDocumentEdits();if(documentDirty())throw Error('New edits are still unsaved. Save again before copying the prompt.');handoffProject=state.project;handoffPath=state.path;await api('export',{project:handoffProject,path:handoffPath});await pollComments();
    if(state.project!==handoffProject||state.path!==handoffPath)throw Error('The document changed while preparing the handoff. Copy again from the document you want to share.');
    if(documentDirty()||$('comment-body').value.trim())throw Error('There are new unsaved edits or a draft comment. Save and post them before copying.');
    try{await navigator.clipboard.writeText($('agent-prompt').value);toast('Latest document and comments saved. Agent prompt copied.');}
    catch{$('agent-prompt').focus();$('agent-prompt').select();toast('Latest document and comments saved. Select and copy the prompt.');}
  }finally{$('copy-agent-prompt').disabled=false;}
});
on('export-button','click',async()=>{$('export-button').disabled=true;try{await saveDocumentEdits();if(documentDirty())throw Error('Save your remaining edits before exporting comments.');const result=await api('export',{project:state.project,path:state.path});await pollComments();toast('Saved to '+result.file);}finally{$('export-button').disabled=false;}});
on('team-button','click',team);on('close-modal','click',closeDialog);
on('account-button','click',()=>{openModal('Your account','<p class="modal-note">'+escape(state.user.name)+' · @'+escape(state.user.username)+'</p><form id="password-form" class="modal-form"><label>Current password<input name="current" type="password" autocomplete="current-password" required></label><label>New password · at least 12 characters<input name="password" type="password" minlength="12" maxlength="256" autocomplete="new-password" required></label><button class="primary">Change password</button></form><hr class="modal-divider"><button id="logout-button" class="secondary">Sign out</button>');$('password-form').onsubmit=async e=>{e.preventDefault();try{const result=await api('password',{current:e.currentTarget.elements.current.value,password:e.currentTarget.elements.password.value});state.csrf=result.csrf;$('modal').close();toast('Password changed. Other sessions have been signed out.');}catch(error){toast(error.message,true);}};$('logout-button').onclick=async()=>{if(!leaveDocumentEditor())return;try{await api('logout',{});$('modal').close();showAuth();location.hash='';location.reload();}catch(error){toast(error.message,true);}};});
// Keep a selection separate from the draft until Add comment is chosen.
let pendingSelection=null;
function hideSelectionAction(){pendingSelection=null;$('selection-comment').classList.add('hidden');}
function selectionSection(node){
  node=node.nodeType===Node.ELEMENT_NODE?node:node.parentElement;
  while(node&&node!==$('document')){
    if(/^H[1-6]$/.test(node.tagName))return node.textContent.slice(0,500);
    let previous=node.previousElementSibling;
    while(previous){if(/^H[1-6]$/.test(previous.tagName))return previous.textContent.slice(0,500);previous=previous.previousElementSibling;}
    node=node.parentElement;
  }
  return '';
}
function captureSelection(event){
  if(document.activeElement===$('selection-comment'))return;
  const area=$('document-source');
  if(documentEditing&&area&&document.activeElement===area&&area.selectionStart!==area.selectionEnd){const quote=area.value.slice(area.selectionStart,area.selectionEnd).trim();if(quote&&quote.length<=3000){pendingSelection={quote,section:'',project:state.project,path:state.path};const rect=area.getBoundingClientRect();$('selection-comment').style.left=Math.min(rect.right-150,window.innerWidth-170)+'px';$('selection-comment').style.top=Math.max(80,rect.top+12)+'px';$('selection-comment').classList.remove('hidden');if(event?.type==='contextmenu')event.preventDefault();return;}}
  const selection=window.getSelection(),article=$('document');
  if(!state.user||!state.path||$('reader').classList.contains('hidden')||!selection||selection.isCollapsed||!article.contains(selection.anchorNode)||!article.contains(selection.focusNode)){hideSelectionAction();return;}
  const quote=selection.toString().trim();
  if(!quote||quote.length>3000){hideSelectionAction();return;}
  const range=selection.getRangeAt(0),rect=range.getBoundingClientRect();
  pendingSelection={quote,section:selectionSection(range.startContainer),project:state.project,path:state.path};
  const button=$('selection-comment');button.classList.remove('hidden');
  const context=event?.type==='contextmenu';
  const x=context?event.clientX:rect.right, y=context?event.clientY:rect.bottom+8;
  button.style.left=Math.max(8,Math.min(x,window.innerWidth-button.offsetWidth-8))+'px';
  button.style.top=Math.max(8,Math.min(y,window.innerHeight-button.offsetHeight-8))+'px';
  if(context)event.preventDefault();
}
$('selection-comment').addEventListener('pointerdown',event=>event.preventDefault());
on('selection-comment','click',()=>{
  const selected=pendingSelection;
  if(!selected||selected.path!==state.path||selected.project!==state.project){hideSelectionAction();return;}
  state.quote=selected.quote;state.section=selected.section;state.reply=null;
  setQuote();saveDraft();hideSelectionAction();setComments(true);
  $('comment-body').focus();$('comment-form').scrollIntoView({block:'nearest'});
});
document.addEventListener('selectionchange',()=>captureSelection());
$('document').addEventListener('contextmenu',captureSelection);
document.addEventListener('pointerdown',event=>{if(!event.target.closest('#selection-comment'))hideSelectionAction();});
document.addEventListener('keydown',event=>{if(event.key==='Escape')hideSelectionAction();});
document.addEventListener('scroll',()=>{if(pendingSelection)captureSelection();},true);
window.addEventListener('resize',hideSelectionAction);
function revealPassage(comment){
  if(documentEditing){if(mobileLayout.matches)setComments(false);if(!window.MarginEditor.selectQuote(comment.quote))toast('This passage could not be located in the current draft.');return;}
  const article=$('document');
  for(const mark of article.querySelectorAll('mark.comment-highlight'))mark.replaceWith(...mark.childNodes);
  article.normalize();
  if(!comment.quote){toast('This comment applies to the whole document.');return;}
  // Normalize rendered whitespace while retaining offsets into the original text nodes.
  const walker=document.createTreeWalker(article,NodeFilter.SHOW_TEXT),nodes=[];
  let raw='',node;
  while((node=walker.nextNode())){nodes.push({node,start:raw.length,end:raw.length+node.length});raw+=node.data;}
  let text='',offsets=[];
  for(let i=0;i<raw.length;i++){
    const char=/\s/.test(raw[i])?' ':raw[i];
    if(char===' '&&text.endsWith(' '))continue;
    text+=char;offsets.push(i);
  }
  const quote=comment.quote.replace(/\s+/g,' ').trim(),matches=[];
  if(!quote){toast('This comment has no quoted passage.');return;}
  for(let at=text.indexOf(quote);at!==-1;at=text.indexOf(quote,at+1))matches.push(at);
  let candidates=matches;
  if(matches.length>1&&comment.section)candidates=matches.filter(at=>{
    const entry=nodes.find(n=>n.start<=offsets[at]&&n.end>offsets[at]);
    return entry&&selectionSection(entry.node)===comment.section;
  });
  if(candidates.length!==1){toast(candidates.length?'This passage appears more than once. Use the quoted text to identify it.':'The quoted passage could not be located in this version of the document.');return;}
  const at=candidates[0],start=offsets[at],end=offsets[at+quote.length-1]+1;
  const marks=[];
  for(const entry of nodes){
    const from=Math.max(start,entry.start)-entry.start,to=Math.min(end,entry.end)-entry.start;
    if(from>=to)continue;
    const range=document.createRange();range.setStart(entry.node,from);range.setEnd(entry.node,to);
    const mark=document.createElement('mark');mark.className='comment-highlight';range.surroundContents(mark);marks.push(mark);
  }
  if(mobileLayout.matches)setComments(false);
  marks[0]?.scrollIntoView({block:'center',behavior:'smooth'});
  for(const thread of $('threads').children)thread.classList.toggle('active-thread',thread.dataset.commentId===String(comment.id));
}
$('document').addEventListener('click',event=>{if(documentEditing)return;const anchor=event.target.closest('a');if(!anchor)return;const href=anchor.getAttribute('href')||'';if(href.startsWith('#')){event.preventDefault();const target=[...$('document').querySelectorAll('[id]')].find(n=>n.id===decodeURIComponent(href.slice(1)));target?.scrollIntoView();return;}if(/^(https?:|mailto:)/i.test(href)){anchor.target='_blank';anchor.rel='noopener noreferrer';return;}event.preventDefault();try{const dir=state.path.split('/').slice(0,-1).join('/');const url=new URL(href,'https://project.invalid/'+dir+'/');const path=decodeURIComponent(url.pathname.slice(1));if(!/\.(md|txt|pdf)$/i.test(path)){toast('Open a Markdown, text or PDF document.');return;}openDocument(path).catch(e=>toast(e.message,true));}catch{toast('This link cannot be opened.',true);}});
document.addEventListener('keydown',e=>{if(e.key==='/'&&!['INPUT','TEXTAREA'].includes(document.activeElement.tagName)&&!$('library').classList.contains('hidden')){e.preventDefault();$('search').focus();}});
// Refresh the filesystem as well as comments, including restored/background tabs.
setInterval(refreshWorkspace,8000);
window.addEventListener('pageshow',refreshWorkspace);
window.addEventListener('focus',refreshWorkspace);
document.addEventListener('visibilitychange',()=>{if(!document.hidden)refreshWorkspace();});
window.addEventListener('beforeunload',e=>{saveDraft();if(titleDirty()||documentDirty()||editorDirty||[...state.drafts.values()].some(d=>d.body?.trim())){e.preventDefault();e.returnValue='';}});
let editorDirty=false,uploadPending=false;
function closeDialog(){if(editorDirty&&!confirm('Discard the unsaved document text?'))return;editorDirty=false;$('modal').close();}
$('modal').addEventListener('cancel',event=>{event.preventDefault();closeDialog();});
function formDialog(title,content,submit){
  openModal(title,'<form id="workspace-form" class="modal-form">'+content+'<p id="workspace-error" class="error" role="alert"></p><button class="primary" type="submit">Save</button></form>');
  $('workspace-form').onsubmit=async event=>{event.preventDefault();const button=event.currentTarget.querySelector('button[type="submit"]');button.disabled=true;$('workspace-error').textContent='';try{await submit(event.currentTarget);editorDirty=false;$('modal').close();}catch(error){$('workspace-error').textContent=error.message;}finally{button.disabled=false;}};
}
function parentNote(folder){return '<p class="modal-note">Folder: '+escape(folder)+'</p>';}
on('folder-up','click',()=>{if(!state.folder)return;const index=state.folder.lastIndexOf('/');if(index<0){state.folder=null;showLibrary();renderFolders();}else chooseFolder(state.folder.slice(0,index));});
on('new-folder','click',()=>{
  const pid=state.project,folder=writeFolder();
  formDialog('New folder',parentNote(folder)+'<label>Folder name<input name="name" required maxlength="150" placeholder="e.g. Research notes"></label>',async form=>{
    const result=await api('folders',{project:pid,path:joinPath(folder,form.elements.name.value)});await refreshFiles();if(state.project===pid)chooseFolder(result.path);toast('Folder created.');
  });
});
function renameFolder(old){
  if(!leaveDocumentEditor())return;
  const pid=state.project,parent=old.includes('/')?old.slice(0,old.lastIndexOf('/')):'.';
  formDialog('Rename folder',parentNote(parent)+'<label>Folder name<input name="name" required maxlength="150" value="'+escape(old.split('/').pop())+'"></label><p class="modal-note">Comments follow the renamed folder. Previously exported reviews remain at their original paths; save reviews again after renaming.</p>',async form=>{
    const result=await api('folders/rename',{project:pid,path:old,new_path:joinPath(parent,form.elements.name.value)});
    for(const [key,draft] of [...state.drafts])if(key.startsWith(pid+':'+old+'/')){state.drafts.set(pid+':'+result.path+key.slice((pid+':'+old).length),draft);state.drafts.delete(key);}
    await refreshFiles();if(state.project===pid)chooseFolder(result.path);toast('Folder renamed.');
  });
}
let documentCreating=false;
async function newDocument(extension){
  if(documentCreating||!state.writable)return;
  if(!leaveDocumentEditor())return;
  const pid=state.project,folder=writeFolder();documentCreating=true;renderFiles();
  try{
    let path;
    for(let number=1;number<=100;number++){
      const candidate=joinPath(folder,'Untitled document'+(number===1?'':' '+number)+'.'+extension);
      if(state.files.some(file=>file.path===candidate))continue;
      try{await api('text',{project:pid,path:candidate,content:''});path=candidate;break;}
      catch(error){if(error.status!==409)throw error;}
    }
    if(!path)throw Error('Too many untitled documents in this folder. Rename a document and try again.');
    if(state.project!==pid){toast('Blank document created in '+folder+'.');return;}
    await refreshFiles();await openDocument(path);startDocumentEditor();window.MarginEditor.focus();
    toast('Start writing. Click the title above to name your document.');
  }finally{documentCreating=false;renderFiles();}
}
on('new-md','click',()=>newDocument('md'));on('new-txt','click',()=>newDocument('txt'));
on('edit-file','click',startDocumentEditor);
on('upload-button','click',()=>$('file-upload').click());
async function uploadFiles(files){
  if(!files.length||!state.writable)return;
  if(uploadPending){toast('Wait for the current upload to finish.');return;}
  uploadPending=true;
  const pid=state.project,folder=writeFolder();const failures=[];let done=0;
  $('upload-button').disabled=true;
  try{
    for(const file of files){
      $('upload-status').textContent='Uploading '+file.name+'…';
      try{
        const storage=await api('storage?project='+encodeURIComponent(pid));
        if(!storage.enabled||file.size>storage.available_bytes)throw Error('not enough workspace storage ('+formatStorageBytes(storage.available_bytes||0)+' available)');
        const form=new FormData();form.append('project',pid);form.append('folder',folder);form.append('file',file);
        const response=await fetch('api/upload?project='+encodeURIComponent(pid),{method:'POST',headers:{'X-CSRF-Token':state.csrf},body:form});
        const result=await response.json().catch(()=>({error:'Upload failed. Check the file size and connection.'}));
        if(!response.ok)throw Error(result.error||'Upload failed');done++;
      }catch(error){failures.push(file.name+': '+error.message);}
    }
    await refreshFiles();$('upload-status').textContent=done+' file(s) uploaded to '+folder+(failures.length?'. '+failures.join(' · '):'.');
    if(!failures.length&&state.project===pid)chooseFolder(folder);
  }finally{uploadPending=false;$('file-upload').value='';$('upload-button').disabled=!state.writable;}
}
on('file-upload','change',event=>uploadFiles([...event.target.files]));
$('library').addEventListener('dragover',event=>{if(event.dataTransfer.types.includes('Files')){event.preventDefault();$('library').classList.add('drop-active');}});
$('library').addEventListener('dragleave',event=>{if(!$('library').contains(event.relatedTarget))$('library').classList.remove('drop-active');});
$('library').addEventListener('drop',event=>{event.preventDefault();$('library').classList.remove('drop-active');uploadFiles([...event.dataTransfer.files]).catch(error=>toast(error.message,true));});


function updateProjects(result){
  state.projects=result.projects;
  $('project-select').replaceChildren(...state.projects.map(p=>new Option(p.name+(p.private?' · Private':''),p.id)));
  if(state.project)$('project-select').value=state.project;
  $('manage-workspaces').classList.toggle('hidden',!result.can_manage_workspaces);
}
async function waitForWorkspace(pid,current){
  for(let attempt=0;attempt<60;attempt++){
    if(!current())return false;
    try{
      const catalog=await api('projects');if(!current())return false;updateProjects(catalog);
      const project=state.projects.find(p=>p.id===pid);
      if(!project){const error=Error('Workspace is no longer available.');error.status=404;throw error;}
      if(project.error){const error=Error(project.error);error.status=400;throw error;}
      if(!project.pending){await refreshFiles();return current();}
    }catch(error){
      if(!current())return false;
      if(error.status&&![502,503,504].includes(error.status))throw error;
    }
    await new Promise(resolve=>setTimeout(resolve,2000));
  }
  throw Error('The folder is taking longer to connect. Click Refresh workspace to retry.');
}
async function manageWorkspaces(){
  updateProjects(await api('projects'));
  openModal('Workspaces','<p class="modal-note">Your personal workspaces are visible only to you. Collaborators keep access only to the shared workspaces assigned to them.</p><div id="workspace-catalog"></div><hr class="modal-divider"><form id="workspace-create-form" class="modal-form"><label>Workspace name<input id="workspace-name" required maxlength="100" placeholder="e.g. Research project"></label><label>Folder choice<select id="workspace-mode"><option value="existing">Connect an existing server folder</option><option value="new">Create a new server folder</option></select></label><label>Absolute folder path<input id="workspace-path" maxlength="1000" placeholder="/root/my-project"></label><p class="modal-note" id="workspace-mode-help">Existing Markdown and text documents can be edited and reviewed. Uploads and new files go into its workspace subfolder; review exports go into .reviews.</p><button type="button" id="browse-server" class="secondary">Browse server folders</button><div id="server-browser" class="server-browser hidden"><div id="server-browser-path"></div><button type="button" id="server-parent" class="text-button">← Parent folder</button><button type="button" id="use-server-folder" class="secondary">Use this folder</button><div id="server-folders"></div></div><p id="workspace-create-error" class="error" role="alert"></p><button id="create-workspace-submit" class="primary" type="submit">Create private workspace</button></form>');
  for(const project of state.projects){
    const row=document.createElement('div');row.className='workspace-entry';
    const label=document.createElement('div');const title=document.createElement('strong');title.textContent=project.name+(project.private?' · Private':' · Shared');const path=document.createElement('small');path.textContent=project.server_path||'';label.append(title,path);
    const open=document.createElement('button');open.className='secondary';open.textContent=project.pending?'Connecting…':'Open';open.disabled=project.pending;
    open.onclick=async()=>{try{if(!leaveDocumentEditor())return;saveDraft();state.path=null;state.project=project.id;$('project-select').value=project.id;$('modal').close();history.replaceState(null,'','#project='+encodeURIComponent(project.id));await loadProject();}catch(error){toast(error.message,true);}};
    row.append(label,open);$('workspace-catalog').append(row);
  }
  let browsed='/',parent=null;
  async function browse(path){
    try{
      const result=await api('server-folders?path='+encodeURIComponent(path));browsed=result.path;parent=result.parent;
      $('server-browser').classList.remove('hidden');$('server-browser-path').textContent=browsed;$('server-parent').disabled=!parent;$('use-server-folder').disabled=browsed==='/';$('server-folders').replaceChildren();
      for(const folder of result.folders){const button=document.createElement('button');button.type='button';button.className='server-folder';button.textContent='▱ '+folder.name;button.onclick=()=>browse(folder.path);$('server-folders').append(button);}
      if(!result.folders.length)$('server-folders').textContent='No visible subfolders.';
    }catch(error){$('workspace-create-error').textContent=error.message;}
  }
  $('browse-server').onclick=()=>browse('/');$('server-parent').onclick=()=>browse(parent);
  $('use-server-folder').onclick=()=>{$('workspace-path').value=browsed;$('server-browser').classList.add('hidden');};
  $('workspace-mode').onchange=()=>{
    const isNew=$('workspace-mode').value==='new';$('workspace-path').required=!isNew;
    $('workspace-path').placeholder=isNew?'Leave blank to create under /srv/margin-projects':'/root/my-project';
    $('workspace-mode-help').textContent=isNew?'A new folder is editable throughout. Leave the path blank to choose a folder name from the workspace name, or enter a new folder path under an existing parent.':'Existing Markdown and text documents can be edited and reviewed. Uploads and new files go into its workspace subfolder; review exports go into .reviews.';
  };
  $('workspace-mode').onchange();
  $('workspace-create-form').onsubmit=async event=>{
    event.preventDefault();if(!leaveDocumentEditor())return;$('create-workspace-submit').disabled=true;$('workspace-create-error').textContent='';
    try{
      const result=await api('workspaces',{name:$('workspace-name').value,mode:$('workspace-mode').value,path:$('workspace-path').value});
      $('modal').close();saveDraft();state.path=null;updateProjects({projects:[...state.projects,{...result,private:true}],can_manage_workspaces:true});state.project=result.id;$('project-select').value=result.id;
      history.replaceState(null,'','#project='+encodeURIComponent(result.id));await loadProject();if(state.project===result.id&&state.projectReady)toast('Private workspace connected.');
    }catch(error){if($('modal').open)$('workspace-create-error').textContent=error.message;else{$('workspace-status').textContent=error.message;toast(error.message,true);}}
    finally{if($('create-workspace-submit'))$('create-workspace-submit').disabled=false;}
  };
}
on('manage-workspaces','click',manageWorkspaces);

(async()=>{const params=new URLSearchParams(location.hash.slice(1));if(params.has('setup')){state.setup=params.get('setup');history.replaceState(null,'',location.pathname);$('auth-title').textContent='Make yourself at home.';$('auth-description').textContent='Choose a password to activate your account.';$('username-label').classList.add('hidden');$('username').required=false;$('password').minLength=12;$('password').autocomplete='new-password';$('password').placeholder='At least 12 characters';$('login-submit').textContent='Set password & enter';$('auth-note').textContent='Your setup link is private and can only be used once.';return;}try{const result=await api('session');if(result.user)await enter(result);else showAuth();}catch(error){$('auth-error').textContent=error.message;}})();

let documentEditing=false,documentRaw=false,documentSaving=null;
function documentDirty(){return documentEditing&&window.MarginEditor.source()!==state.source;}
function editorStatus(){ $('document-save-state').textContent=(documentDirty()||titleDirty())?'Unsaved changes':'All changes saved';for(const name of ['bold','italic','underline','strike'])document.querySelector('[data-format='+name+']').setAttribute('aria-pressed',String(window.MarginEditor.active(name))); }
function leaveDocumentEditor(){
  if(documentSaving||titleSaving){toast('Wait for the document to finish saving.');return false;}
  if((documentDirty()||titleDirty())&&!confirm('Leave this document and discard unsaved edits? Use Save document to keep them.'))return false;
  if(documentEditing){window.MarginEditor.destroy();if($('document-source'))$('document-source').readOnly=true;$('document').querySelectorAll('[contenteditable]').forEach(node=>node.contentEditable='false');documentEditing=false;$('editor-toolbar').classList.add('hidden');$('edit-file').disabled=false;$('document').classList.remove('editing');}
  return true;
}
function mountDocumentEditor(content,raw=false){
  const result=window.MarginEditor.mount($('document'),content,state.fileKind,raw,editorStatus);
  documentRaw=result.raw;$('format-controls').classList.toggle('hidden',state.fileKind!=='md');
  $('source-mode').classList.toggle('hidden',state.fileKind==='txt');$('source-mode').textContent=result.unsupported?'Source mode':documentRaw?'Formatted editor':'Markdown source';$('source-mode').disabled=result.unsupported;
  $('editor-notice').textContent=result.unsupported?'This document uses extended Markdown. Formatting buttons insert Markdown while source editing preserves the original syntax.':state.fileKind==='txt'?'Plain text stays plain text. Save before leaving this document.':'Markdown formatting is saved to the original .md file. Earlier versions are available in History.';
  editorStatus();
}
function startDocumentEditor(){
  if(documentEditing)return;if(mobileLayout.matches)setComments(false);documentEditing=true;hideSelectionAction();$('document').classList.add('editing');$('editor-toolbar').classList.remove('hidden');$('edit-file').disabled=true;
  mountDocumentEditor(state.source);$('document').scrollIntoView({block:'start'});
}
async function saveDocumentEdits(){
  if(documentSaving)return documentSaving;
  await saveDocumentTitle();
  if(!documentDirty())return;
  const content=window.MarginEditor.source(),pid=state.project,path=state.path,revision=state.revision;
  $('save-document').disabled=true;$('document-save-state').textContent='Saving…';
  documentSaving=(async()=>{
    try{const result=await api('text',{project:pid,path,revision,content});state.source=content;state.revision=result.revision;
      // Edits typed during the request remain a new unsaved draft.
      if(window.MarginEditor.source()===content)window.MarginEditor.markSaved(content);
      editorStatus();await pollComments();void refreshStorage(pid);
    }catch(error){$('document-save-state').textContent='Not saved — '+error.message;throw error;}
    finally{$('save-document').disabled=false;documentSaving=null;}
  })();
  return documentSaving;
}
on('save-document','click',async()=>{await saveDocumentEdits();toast('Document saved.');});
on('finish-editing','click',async()=>{await saveDocumentEdits();if(documentDirty()){toast('New edits are still unsaved. Save again before finishing.');return;}await openDocument(state.path);});
on('source-mode','click',()=>{const content=window.MarginEditor.source();mountDocumentEditor(content,!documentRaw);});
$('format-controls').addEventListener('mousedown',event=>{if(event.target.closest('button'))event.preventDefault();});
$('format-controls').addEventListener('click',event=>{const button=event.target.closest('[data-format]');if(!button)return;let value;
  if(button.dataset.format==='link'){value=prompt('Link URL (https://, http:// or mailto:). Leave empty to remove.');if(value===null)return;if(value&&!/^(https?:\/\/|mailto:)/i.test(value)){toast('Use an HTTP, HTTPS or email link.',true);return;}}
  window.MarginEditor.command(button.dataset.format,value);
});
on('block-style','change',()=>window.MarginEditor.command($('block-style').value==='paragraph'?'paragraph':'heading',$('block-style').value));
document.addEventListener('keydown',event=>{if(documentEditing&&(event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();saveDocumentEdits().catch(e=>toast(e.message,true));}});
on('version-history','click',async()=>{
  const result=await api('versions?project='+encodeURIComponent(state.project)+'&path='+encodeURIComponent(state.path));
  openModal('Document history','<p class="modal-note">Versions saved before earlier edits. Restoring opens a draft; click Save document to apply it.</p><div id="versions-list"></div>');
  if(!result.versions.length)$('versions-list').textContent='No earlier versions yet.';
  for(const version of result.versions){const button=document.createElement('button');button.className='history-row';button.textContent=new Date(version.created).toLocaleString()+' · Before edit by '+version.name;button.onclick=async()=>{try{if(documentDirty()&&!confirm('Replace your unsaved draft with this earlier version?'))return;const old=await api('versions/'+version.id);$('modal').close();if(!documentEditing)startDocumentEditor();mountDocumentEditor(old.content,true);editorStatus();}catch(e){toast(e.message,true);}};$('versions-list').append(button);}
});
function renameFile(old=state.path){
  if(!leaveDocumentEditor())return;
  const pid=state.project,parent=old.includes('/')?old.slice(0,old.lastIndexOf('/')):'.';
  formDialog('Rename file',parentNote(parent)+'<label>File name<input name="name" required maxlength="150" value="'+escape(old.split('/').pop())+'"></label><p class="modal-note">Keep the file extension. Comments and history follow the renamed file.</p>',async form=>{
    const result=await api('files/rename',{project:pid,path:old,new_path:joinPath(parent,form.elements.name.value)});
    const key=pid+':'+old;if(state.drafts.has(key)){state.drafts.set(pid+':'+result.path,state.drafts.get(key));state.drafts.delete(key);}
    await refreshFiles();await openDocument(result.path);toast('File renamed.');
  });
}
on('rename-file','click',()=>renameFile());
async function trashItem(path){
  if(!confirm('Move “'+path+'” to Trash? Its contents and comments can be restored.'))return;
  if(!leaveDocumentEditor())return;
  await api('trash',{project:state.project,path});state.folder=null;showLibrary();await refreshFiles();toast('Moved to Trash.');
}
on('trash-file','click',()=>trashItem(state.path));
on('view-trash','click',async()=>{
  const pid=state.project,result=await api('trash?project='+encodeURIComponent(pid));
  openModal('Trash','<p class="modal-note">Files, folders and their comments stay here until restored. They still count toward workspace storage.</p><div id="trash-list"></div>');
  if(!result.items.length)$('trash-list').textContent='Trash is empty.';
  for(const item of result.items){const row=document.createElement('div');row.className='trash-row';const name=document.createElement('span');name.textContent=item.path;const restore=document.createElement('button');restore.className='secondary';restore.textContent='Restore';restore.onclick=async()=>{try{await api('trash/restore',{project:pid,id:item.id});row.remove();await refreshFiles();toast('Restored '+item.path);}catch(e){toast(e.message,true);}};row.append(name,restore);$('trash-list').append(row);}
});

let titleSaving=null;
function titleDirty(){return !!state.path&&!$('document-title').classList.contains('hidden')&&$('document-title').value!==state.path.split('/').pop();}
async function saveDocumentTitle(){
  if(titleSaving)return titleSaving;
  if(!titleDirty())return;
  const pid=state.project,old=state.path,extension='.'+state.fileKind;
  let name=$('document-title').value.trim();
  if(!name||/[\/\\]/.test(name))throw Error('Enter a document title without slashes.');
  if(!name.toLowerCase().endsWith(extension))name+=extension;
  const parent=old.includes('/')?old.slice(0,old.lastIndexOf('/')):'.',next=joinPath(parent,name);
  if(next===old){$('document-title').value=name;editorStatus();return;}
  titleSaving=Promise.resolve().then(async()=>{
    $('document-title').disabled=true;
    try{
      const result=await api('files/rename',{project:pid,path:old,new_path:next});
      const key=pid+':'+old;if(state.drafts.has(key)){state.drafts.set(pid+':'+result.path,state.drafts.get(key));state.drafts.delete(key);}
      if(pendingSelection?.project===pid&&pendingSelection.path===old)pendingSelection.path=result.path;
      state.path=result.path;$('document-title').value=name;$('document-name').textContent=name;document.title=name+' · Margin';
      history.replaceState(null,'','#project='+encodeURIComponent(pid)+'&file='+encodeURIComponent(result.path));$('download-file').href=fileURL('download');
      await refreshFiles();await pollComments();editorStatus();
    }catch(error){$('document-save-state').textContent='Title not saved — '+error.message;throw error;}
    finally{$('document-title').disabled=false;titleSaving=null;}
  });
  return titleSaving;
}
on('document-title','input',editorStatus);
on('document-title','change',saveDocumentTitle);
on('document-title','keydown',async event=>{
  if(event.key==='Enter'){event.preventDefault();await saveDocumentTitle();if(documentEditing)window.MarginEditor.focus();else $('document-title').blur();}
  if(event.key==='Escape'){$('document-title').value=state.path.split('/').pop();editorStatus();$('document-title').blur();}
});

let folderMenuTrigger=null;
function hideFolderMenu(){ $('folder-context-menu').classList.add('hidden'); }
function attachFolderMenu(button,path){
  button.dataset.folderPath=path;button.setAttribute('aria-haspopup','menu');
  const open=event=>{event.preventDefault();showFolderMenu(button,path,event.clientX,event.clientY);};
  button.addEventListener('contextmenu',open);
  button.addEventListener('keydown',event=>{if(event.key==='ContextMenu'||(event.shiftKey&&event.key==='F10')){event.preventDefault();const rect=button.getBoundingClientRect();showFolderMenu(button,path,rect.left+12,rect.bottom);}});
}
function showFolderMenu(button,path,x,y){
  const actions=[['Open folder',()=>chooseFolder(path)]];
  const writable=path!=='.'&&state.writable&&(state.writable==='.'||path.startsWith(state.writable+'/'));
  if(writable)actions.push(['Rename…',()=>renameFolder(path)],['Move to Trash',()=>trashItem(path),true]);
  showItemMenu(button,'Folder actions',actions,x,y);
}
function attachFileMenu(button,file){
  button.dataset.filePath=file.path;button.setAttribute('aria-haspopup','menu');
  button.addEventListener('contextmenu',event=>{event.preventDefault();showFileMenu(button,file,event.clientX,event.clientY);});
  button.addEventListener('keydown',event=>{if(event.key==='ContextMenu'||(event.shiftKey&&event.key==='F10')){event.preventDefault();const rect=button.getBoundingClientRect();showFileMenu(button,file,rect.left+12,rect.bottom);}});
}
function showFileMenu(button,file,x,y){
  const actions=[['Open',()=>openDocument(file.path)]];
  if((file.editable??file.writable)&&['md','txt'].includes(file.kind)&&file.size<=2*1024*1024)actions.push(['Edit document',async()=>{await openDocument(file.path);if(state.path===file.path)startDocumentEditor();}]);
  if(file.writable)actions.push(['Rename…',()=>renameFile(file.path)]);
  actions.push(['Download',()=>{const link=document.createElement('a');link.href=fileURL('download',file.path);link.download=file.name;document.body.append(link);link.click();link.remove();}]);
  if(file.kind==='md')actions.push(['Download as PDF',()=>downloadMarkdownPdf(file.path)]);
  if(file.writable)actions.push(['Move to Trash',()=>trashItem(file.path),true]);
  showItemMenu(button,'File actions',actions,x,y);
}
function showItemMenu(button,label,actions,x,y){
  hideSelectionAction();folderMenuTrigger=button;const menu=$('folder-context-menu'),pid=state.project;menu.replaceChildren();menu.setAttribute('aria-label',label);
  for(const [label,callback,danger] of actions){const item=document.createElement('button');item.type='button';item.setAttribute('role','menuitem');item.textContent=label;item.classList.toggle('danger',!!danger);item.onclick=async()=>{hideFolderMenu();if(state.project!==pid)return;try{await callback();}catch(error){toast(error.message,true);}};menu.append(item);}
  menu.classList.remove('hidden');menu.style.left=Math.max(8,Math.min(x,innerWidth-menu.offsetWidth-8))+'px';menu.style.top=Math.max(8,Math.min(y,innerHeight-menu.offsetHeight-8))+'px';menu.querySelector('button').focus({preventScroll:true});
}
document.addEventListener('pointerdown',event=>{if(!event.target.closest('#folder-context-menu'))hideFolderMenu();});
for(const eventName of ['wheel','touchmove'])document.addEventListener(eventName,event=>{if(!event.target.closest('#folder-context-menu'))hideFolderMenu();},{passive:true});window.addEventListener('resize',hideFolderMenu);
$('folder-context-menu').addEventListener('keydown',event=>{
  const items=[...$('folder-context-menu').querySelectorAll('button')],index=items.indexOf(document.activeElement);
  if(event.key==='Escape'){event.preventDefault();hideFolderMenu();folderMenuTrigger?.focus();}
  if(event.key==='Tab')hideFolderMenu();
  if(['ArrowDown','ArrowUp','Home','End'].includes(event.key)){event.preventDefault();const next=event.key==='Home'?0:event.key==='End'?items.length-1:(index+(event.key==='ArrowDown'?1:-1)+items.length)%items.length;items[next].focus();}
});

function formatStorageBytes(bytes){
  if(bytes<1024)return bytes+' B';
  const units=['KiB','MiB','GiB','TiB'];let amount=bytes/1024,index=0;
  while(amount>=1024&&index<units.length-1){amount/=1024;index++;}
  return amount.toLocaleString(undefined,{maximumFractionDigits:amount<10?1:0})+' '+units[index];
}
async function refreshStorage(pid=state.project){
  if(!pid||!state.user)return;
  const sequence=(state.storageRequest||0)+1;state.storageRequest=sequence;
  try{
    const usage=await api('storage?project='+encodeURIComponent(pid));
    if(pid!==state.project||sequence!==state.storageRequest)return;
    $('storage-meter').classList.toggle('hidden',!usage.enabled);
    if(!usage.enabled){$('storage-summary').textContent='No upload storage configured';$('storage-detail').textContent='';return;}
    document.querySelector('.storage-status strong').textContent=state.writable==='.'?'Workspace storage':'Uploads & created files';
    $('storage-summary').textContent=formatStorageBytes(usage.used_bytes)+' of '+formatStorageBytes(usage.limit_bytes)+' used';
    $('storage-meter').max=Math.max(1,usage.limit_bytes);$('storage-meter').value=usage.used_bytes;
    $('storage-meter').setAttribute('aria-valuetext',$('storage-summary').textContent);
    $('storage-detail').textContent=formatStorageBytes(usage.available_bytes)+' available'+(usage.trash_bytes?' · '+formatStorageBytes(usage.trash_bytes)+' in Trash':'');
    $('storage-meter').classList.toggle('near-limit',usage.used_bytes>=usage.limit_bytes*0.9);
  }catch(error){if(pid===state.project&&sequence===state.storageRequest){$('storage-summary').textContent='Storage status unavailable';$('storage-detail').textContent='Refresh to retry.';$('storage-meter').classList.add('hidden');}}
}

for(const button of document.querySelectorAll("[data-open-privacy]")){button.addEventListener("click",()=>openModal("Privacy in Margin",$("privacy-content").innerHTML));}

function appendItemActions(container,button,className,label,open){
  const row=document.createElement('div');row.className=className;
  const more=document.createElement('button');more.type='button';more.className='item-menu-button';more.textContent='···';more.setAttribute('aria-label',label);more.setAttribute('aria-haspopup','menu');
  more.onclick=event=>{event.stopPropagation();const rect=more.getBoundingClientRect();open(more,rect.left,rect.bottom);};
  row.append(button,more);container.append(row);
}
function setSidebar(open,restoreFocus=false){
  open=!!open&&mobileLayout.matches;
  $('sidebar').classList.toggle('visible',open);$('sidebar-backdrop').classList.toggle('hidden',!open);
  $('menu-button').setAttribute('aria-expanded',String(open));$('menu-button').setAttribute('aria-label',open?'Close navigation':'Open navigation');
  document.querySelector('.main').inert=open;
  if(open){$('sidebar').setAttribute('role','dialog');$('sidebar').setAttribute('aria-modal','true');$('sidebar').setAttribute('aria-label','Workspace navigation');$('close-sidebar').focus({preventScroll:true});}
  else{$('sidebar').removeAttribute('role');$('sidebar').removeAttribute('aria-modal');$('sidebar').removeAttribute('aria-label');if(restoreFocus)$('menu-button').focus();}
}
function setComments(open){$('reader').classList.toggle('no-comments',!open);$('comments-toggle').setAttribute('aria-expanded',String(!!open));}
document.addEventListener('keydown',event=>{
  if(!mobileLayout.matches||!$('sidebar').classList.contains('visible')||$('modal').open||!$('folder-context-menu').classList.contains('hidden'))return;
  if(event.key==='Escape'){event.preventDefault();setSidebar(false,true);}
  if(event.key==='Tab'){
    const items=[...$('sidebar').querySelectorAll('a,button,select,[tabindex="0"]')].filter(el=>!el.disabled&&el.getClientRects().length);
    const first=items[0],last=items.at(-1);
    if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus();}
    else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus();}
  }
});

let pdfDownloadPending=false;
async function downloadMarkdownPdf(path){
  if(pdfDownloadPending){toast('A PDF is already being prepared.');return;}
  const pid=state.project;let revision=null;
  pdfDownloadPending=true;
  try{
    if(state.path===path){await saveDocumentEdits();if(documentDirty()||titleDirty())throw Error('Save the remaining edits before downloading the PDF.');path=state.path;revision=state.revision;}
    if(state.project!==pid)throw Error('The workspace changed. Choose the document again.');
    toast('Preparing PDF…');
    const query=new URLSearchParams({project:pid,path});if(revision)query.set('revision',revision);
    const response=await fetch('api/markdown-pdf?'+query,{cache:'no-store'});
    if(!response.ok){const result=await response.json().catch(()=>({error:'PDF download failed. Please try again.'}));throw Error(result.error);}
    const blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');
    link.href=url;link.download=path.split('/').pop().replace(/\.md$/i,'.pdf');document.body.append(link);link.click();link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),60000);toast('PDF download ready.');
  }finally{pdfDownloadPending=false;}
}

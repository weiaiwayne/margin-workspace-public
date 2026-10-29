import {Editor} from '@tiptap/core';
import StarterKit from '@tiptap/starter-kit';
import {Markdown} from '@tiptap/markdown';
import {TableKit} from '@tiptap/extension-table';
import TaskList from '@tiptap/extension-task-list';
import TaskItem from '@tiptap/extension-task-item';
import Image from '@tiptap/extension-image';
import Underline from '@tiptap/extension-underline';
const MarkdownUnderline=Underline.extend({
  renderMarkdown(node,helpers){return '<u>'+helpers.renderChildren(node)+'</u>';},
  markdownTokenizer:{name:'underline',level:'inline',start:src=>src.indexOf('<u>'),tokenize(src,_tokens,lexer){const match=/^<u>([\s\S]+?)<\/u>/.exec(src);if(!match)return;return {type:'underline',raw:match[0],tokens:lexer.inlineTokens(match[1])};}}
});
// Keep image syntax without loading remote tracking images or local relative URLs.
const SafeImage=Image.extend({renderHTML({node}){return ['span',{'class':'editor-image','data-image-src':node.attrs.src},'Image: '+(node.attrs.alt||node.attrs.src)];}});
let editor=null,area=null,original='',changed=false,notify=()=>{},rawHistory=[],rawIndex=0;
function snapshot(){return {value:area.value,start:area.selectionStart,end:area.selectionEnd};}
function recordRaw(){const next=snapshot();if(rawHistory[rawIndex]?.value!==next.value){rawHistory=rawHistory.slice(0,rawIndex+1);rawHistory.push(next);while(rawHistory.length>100||(rawHistory.length>2&&rawHistory.reduce((n,x)=>n+x.value.length,0)>4*1024*1024))rawHistory.shift();rawIndex=rawHistory.length-1;}changed=area.value!==original;notify();}
function rawCommand(name,value){
  if(name==='undo'||name==='redo'){rawIndex=Math.max(0,Math.min(rawHistory.length-1,rawIndex+(name==='undo'?-1:1)));const s=rawHistory[rawIndex];area.value=s.value;area.setSelectionRange(s.start,s.end);changed=area.value!==original;area.focus();notify();return;}
  let from=area.selectionStart,to=area.selectionEnd,text=area.value.slice(from,to),replacement,selectFrom,selectTo;
  rawHistory[rawIndex]=snapshot();
  const marks={bold:['**','**'],italic:['*','*'],underline:['<u>','</u>'],strike:['~~','~~']};
  if(marks[name]){const [left,right]=marks[name];
    if(from>=left.length&&area.value.slice(from-left.length,from)===left&&area.value.slice(to,to+right.length)===right){from-=left.length;to+=right.length;replacement=text;selectFrom=from;selectTo=from+text.length;}
    else{const content=text||'text';replacement=left+content+right;selectFrom=from+left.length;selectTo=selectFrom+content.length;}
  }else if(name==='link'){if(!value)return;replacement='['+(text||'link text')+']('+value+')';selectFrom=from+1;selectTo=selectFrom+(text||'link text').length;}
  else if(name==='table'){replacement='\n\n| Column 1 | Column 2 |\n| --- | --- |\n|  |  |\n\n';}
  else{from=from===0?0:area.value.lastIndexOf('\n',from-1)+1;const end=area.value.indexOf('\n',Math.max(from,to-(to>from?1:0)));to=end<0?area.value.length:end;text=area.value.slice(from,to);
    if(name==='code')replacement='```\n'+text+'\n```';
    else{const lines=text.split('\n');const prefix={bullet:'- ',number:'1. ',task:'- [ ] ',quote:'> ',heading:'#'.repeat(Number(value)||1)+' ',paragraph:''}[name];if(prefix===undefined)return;
      replacement=lines.map((line,index)=>name==='heading'||name==='paragraph'?prefix+line.replace(/^ {0,3}#{1,6}\s+/,''):name==='number'?(index+1)+'. '+line.replace(/^\d+\.\s+/,''):line.startsWith(prefix)?line.slice(prefix.length):prefix+line).join('\n');}
  }
  area.setRangeText(replacement,from,to,'select');if(selectFrom!==undefined)area.setSelectionRange(selectFrom,selectTo);area.focus();recordRaw();
}
function destroy(){editor?.destroy();editor=null;area=null;changed=false;}
function source(){return changed?(area?area.value:editor.getMarkdown()):original;}
function unsupported(text){text=text.replace(/<\/?u>/g,'');return /<!--|<\/?[A-Za-z][^>]*>|^\s*\$\$/m.test(text)||/(^---\s*\n[\s\S]*?\n---\s*$)|(^\s*<[^>]+>)|(^\s*\[\^)|(^\s*\*[[][^\]]+\]:)|(^\s*:::)|(\{[#.][^}]+\})/m.test(text)||/\[\^[^\]]+\]/.test(text);}
window.MarginEditor={
  mount(element,text,kind,sourceMode,onChange){
    destroy();original=text;notify=onChange;rawHistory=[];rawIndex=0;const raw=kind==='txt'||sourceMode||unsupported(text);
    element.replaceChildren();
    if(raw){area=document.createElement('textarea');area.id='document-source';area.className='document-source'+(kind==='txt'?' plain-document':'');area.value=text;area.spellcheck=true;area.setAttribute('aria-label',kind==='txt'?'Edit text document':'Edit Markdown source');element.append(area);rawHistory=[snapshot()];area.addEventListener('input',recordRaw);area.addEventListener('keydown',event=>{if(kind!=='md'||!(event.ctrlKey||event.metaKey))return;const key=event.key.toLowerCase(),command={b:'bold',i:'italic',u:'underline',z:event.shiftKey?'redo':'undo',y:'redo'}[key];if(command){event.preventDefault();rawCommand(command);}});}
    else editor=new Editor({element,injectCSS:false,extensions:[StarterKit.configure({underline:false,link:{openOnClick:false,autolink:false}}),MarkdownUnderline,Markdown,TableKit,TaskList,TaskItem.configure({nested:true}),SafeImage],content:text,contentType:'markdown',editorProps:{attributes:{'aria-label':'Edit document','role':'textbox','aria-multiline':'true',spellcheck:'true'}},onUpdate(){changed=true;notify();},onSelectionUpdate(){notify();}});
    return {raw,unsupported:kind==='md'&&!sourceMode&&raw};
  },destroy,source,focus(){if(area)area.focus();else editor?.commands.focus('end');},active(name){return editor?.isActive(name)||false;},dirty:()=>changed,markSaved(text){original=text;changed=false;},
  command(name,value){if(area){rawCommand(name,value);return;}if(!editor)return;const selection=window.getSelection();if(selection?.anchorNode&&editor.view.dom.contains(selection.anchorNode)&&editor.view.dom.contains(selection.focusNode)){const anchor=editor.view.posAtDOM(selection.anchorNode,selection.anchorOffset),head=editor.view.posAtDOM(selection.focusNode,selection.focusOffset);editor.commands.setTextSelection({from:Math.min(anchor,head),to:Math.max(anchor,head)});}const chain=editor.chain().focus();const commands={bold:()=>chain.toggleBold(),italic:()=>chain.toggleItalic(),underline:()=>chain.toggleUnderline(),strike:()=>chain.toggleStrike(),bullet:()=>chain.toggleBulletList(),number:()=>chain.toggleOrderedList(),task:()=>chain.toggleTaskList(),quote:()=>chain.toggleBlockquote(),code:()=>chain.toggleCodeBlock(),undo:()=>chain.undo(),redo:()=>chain.redo(),paragraph:()=>chain.setParagraph(),heading:()=>chain.setHeading({level:Number(value)}),table:()=>chain.insertTable({rows:3,cols:3,withHeaderRow:true}),link:()=>value?chain.extendMarkRange('link').setLink({href:value}):chain.unsetLink()};commands[name]?.().run();},
  selectQuote(quote){
    if(area){const at=area.value.indexOf(quote);if(at<0)return false;area.focus();area.setSelectionRange(at,at+quote.length);return true;}
    if(!editor)return false;
    let text='',positions=[];
    editor.state.doc.descendants((node,pos)=>{
      if(node.isBlock&&text&&!text.endsWith(' ')){text+=' ';positions.push(pos);}
      if(node.isText)for(let i=0;i<node.text.length;i++){
        const c=/\s/.test(node.text[i])?' ':node.text[i];if(c===' '&&text.endsWith(' '))continue;text+=c;positions.push(pos+i);
      }
    });
    const normalized=quote.trim().replace(/\s+/g,' '),at=text.indexOf(normalized);
    if(!normalized||at<0||text.indexOf(normalized,at+1)>=0)return false;
    editor.chain().focus().setTextSelection({from:positions[at],to:positions[at+normalized.length-1]+1}).scrollIntoView().run();return true;
  }
};

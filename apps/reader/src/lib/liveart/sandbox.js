// Iframe document. The sandbox attribute is set by the parent, not here.
// The draw is parsed as a real function. CSP blocks eval, so new Function is not available.
import { CANVAS_METHODS, CANVAS_PROPS, CSP, HOST, MATH_NAMES, SANDBOX } from "./spec.js";
import { UI_COLORS as UI_FALLBACK, makeUI } from "./ui04.js";

export { CSP, SANDBOX };

function embed(draw) {
  return String(draw).replace(/<\/(script)/gi, "<\\/$1");
}

export function srcdoc(draw) {
  const methods = JSON.stringify(CANVAS_METHODS);
  const props = JSON.stringify(CANVAS_PROPS);
  const math = JSON.stringify(MATH_NAMES);
  return `<!DOCTYPE html><html><head><meta http-equiv="Content-Security-Policy" content="${CSP}"><style>html,body{margin:0;background:#f4efe5;overflow:hidden}canvas{display:block;width:100%;height:100%}</style></head><body><canvas id="c" width="${HOST.canvas_w}" height="${HOST.canvas_h}"></canvas><script>(function(RealMath){var parentWin=window.parent;var canvas=document.getElementById("c");var dpr=RealMath.min(2,window.devicePixelRatio||1);canvas.width=${HOST.canvas_w}*dpr;canvas.height=${HOST.canvas_h}*dpr;var raw=canvas.getContext("2d");raw.scale(dpr,dpr);var ctx=Object.create(null);var methods=${methods};var props=${props};var i;for(i=0;i<methods.length;i++){(function(name){ctx[name]=function(){return raw[name].apply(raw,arguments);};})(methods[i]);}for(i=0;i<props.length;i++){(function(name){Object.defineProperty(ctx,name,{enumerable:true,get:function(){return raw[name];},set:function(v){raw[name]=v;}});})(props[i]);}var mathNames=${math};var SafeMath=Object.create(null);for(i=0;i<mathNames.length;i++)SafeMath[mathNames[i]]=RealMath[mathNames[i]];var Math=SafeMath;${embed(draw)};window.addEventListener("message",function(ev){if(ev.source!==parentWin)return;var data=ev.data;if(!data||data.type!=="rrm-params")return;var state=Object.create(null);var incoming=data.state||{};var key;for(key in incoming){if(Object.prototype.hasOwnProperty.call(incoming,key))state[key]=incoming[key];}try{draw(ctx,state,Number(data.t)||0);var pix=sample(raw);parentWin.postMessage({type:"rrm-live",ok:pix>0,reason:pix>0?"frame":"blank",pixels:pix},"*");}catch(err){parentWin.postMessage({type:"rrm-live",ok:false,reason:"throw"},"*");}});parentWin.postMessage({type:"rrm-live",ok:true,reason:"ready"},"*");function sample(context){try{var data=context.getImageData(0,0,canvas.width,canvas.height).data;var n=0,p;for(p=3;p<data.length;p+=64)if(data[p]>8)n++;return n;}catch(e){return 1;}}})(Math);</script></body></html>`;
}

// rrm-widget/0.4 (RRM-90). The canvas takes the size the host measured (CSS px) times dpr (R4).
// makeUI runs in its own script with the real Math; the draw keeps the SafeMath subset.
// The host sends rrm-init {w, h, dpr, colors, font?} once (font: an ArrayBuffer for FontFace, R3),
// then rrm-params {state, t}. Each frame answers with what the host paints: readouts, say,
// regime marks on controls, drag handles, pick and tip boxes, and the layout report.
function spec04(widget) {
  const { draw, ...rest } = widget;
  return JSON.stringify(rest).replace(/<\/(script)/gi, "<\\/$1");
}

export function srcdoc04(widget) {
  const methods = JSON.stringify(CANVAS_METHODS);
  const props = JSON.stringify(CANVAS_PROPS);
  const math = JSON.stringify(MATH_NAMES);
  // A production build renames makeUI (minifier): bind the source to the name the guest uses (RRM-98).
  const helpers = embed(makeUI.toString());
  return `<!DOCTYPE html><html><head><meta http-equiv="Content-Security-Policy" content="${CSP}"><style>html,body{margin:0;background:transparent;overflow:hidden}canvas{display:block}</style></head><body><canvas id="c"></canvas><script>var makeUI=(${helpers});</script><script>(function(RealMath){var parentWin=window.parent;var canvas=document.getElementById("c");var raw=canvas.getContext("2d");var W=${spec04(widget)};var size={w:${HOST.canvas_w},h:${HOST.canvas_h},dpr:1},colors=null,mute=false;var mk=makeUI;var allowed=${methods};var props=${props};var i;var mathNames=${math};var SafeMath=Object.create(null);for(i=0;i<mathNames.length;i++)SafeMath[mathNames[i]]=RealMath[mathNames[i]];var Math=SafeMath;${embed(widget.draw)};function fit(){canvas.width=RealMath.round(size.w*size.dpr);canvas.height=RealMath.round(size.h*size.dpr);canvas.style.width=size.w+"px";canvas.style.height=size.h+"px";}fit();window.addEventListener("message",function(ev){if(ev.source!==parentWin)return;var data=ev.data;if(!data)return;if(data.type==="rrm-init"){size={w:+data.w||size.w,h:+data.h||size.h,dpr:RealMath.min(3,+data.dpr||1)};colors=data.colors||null;mute=!!data.mute;fit();if(data.font&&typeof FontFace==="function"){try{var ff=new FontFace("RRM UI",data.font,{weight:"400 700"});ff.load().then(function(f){document.fonts.add(f);parentWin.postMessage({type:"rrm-live",ok:true,reason:"font"},"*");},function(){});}catch(e){}}return;}if(data.type!=="rrm-params")return;var state=Object.create(null);var incoming=data.state||{};var key;for(key in incoming){if(Object.prototype.hasOwnProperty.call(incoming,key))state[key]=incoming[key];}state.w=size.w;state.h=size.h;try{raw.setTransform(size.dpr,0,0,size.dpr,0,0);raw.clearRect(0,0,size.w,size.h);var M=mk(raw,W,{w:size.w,h:size.h,scale:size.dpr,mute:mute,colors:colors||${JSON.stringify(UI_FALLBACK)},v04:true});raw.fillStyle=M.ui.c.bg;raw.fillRect(0,0,size.w,size.h);raw.save();draw(M.gctx,state,Number(data.t)||0,M.ui);raw.restore();var r=M.flush();var pix=sample(raw);parentWin.postMessage({type:"rrm-live",ok:pix>0,reason:pix>0?"frame":"blank",pixels:pix,frame:{readouts:r.readouts,say:r.say,cmarks:r.cmarks,handles:r.handles,picks:r.picks,tips:r.tips,report:r.report}},"*");}catch(err){parentWin.postMessage({type:"rrm-live",ok:false,reason:"throw"},"*");}});parentWin.postMessage({type:"rrm-live",ok:true,reason:"ready"},"*");function sample(context){try{var d=context.getImageData(0,0,canvas.width,canvas.height).data;var n=0,p;for(p=3;p<d.length;p+=64)if(d[p]>8)n++;return n;}catch(e){return 1;}}})(Math);</script></body></html>`;
}

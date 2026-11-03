// Iframe document. The sandbox attribute is set by the parent, not here.
// The draw is parsed as a real function. CSP blocks eval, so new Function is not available.
import { CANVAS_METHODS, CANVAS_PROPS, CSP, HOST, MATH_NAMES, SANDBOX } from "./spec.js";

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

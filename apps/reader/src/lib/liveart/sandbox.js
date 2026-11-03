// Iframe document. The sandbox attribute is set by the parent, not here.
// The draw is parsed as a real function. CSP blocks eval, so new Function is not available.
import { CANVAS_METHODS, CANVAS_PROPS, CSP, HOST, MATH_NAMES, SANDBOX } from "./spec.js";

export { CSP, SANDBOX };

function embed(draw) {
  return String(draw).replace(/<\/(script)/gi, "<\\/$1");
}

const BOOT = `function bootUi(meta,raw,state){var frame={readouts:{},say:"",handles:[],picks:[],tips:[],report:{marks_out:[],dropped:[]}};var labels=0;var c={bg:"#f6f3ec",ink:"#1d1a16",ink2:"#5c564c",ink3:"#8a8175",rule:"#e4d6c4",rule2:"#d9d0c3",soft:"#f3efe6",track:"#e7e1d6",ref:"#8a8175",hl:"#c4512c",c1:"#1f4b99",c2:"#c4512c",c3:"#2e7d32",c4:"#8e44ad"};function area(id){var list=meta.areas&&meta.areas.length?meta.areas:[{id:"main",rect:[0,0,1,1]}];var spec=list[0],i,W=state.w||640,H=state.h||360;for(i=0;i<list.length;i++)if(list[i].id===id)spec=list[i];var rect=spec.rect||[0,0,1,1];var x=rect[0]*W+10,y=rect[1]*H+10,w=Math.max(8,rect[2]*W-20),h=Math.max(8,rect[3]*H-28);var xs=spec.x||{},ys=spec.y||{};function mx(v){var lo=+xs.min||0,hi=xs.max==null?lo+1:+xs.max,span=hi===lo?1:hi-lo;return x+((+v||0)-lo)/span*w;}function my(v){var lo=+ys.min||0,hi=ys.max==null?lo+1:+ys.max,span=hi===lo?1:hi-lo;return y+h-((+v||0)-lo)/span*h;}return {x:x,y:y,w:w,h:h,x1:x+w,y1:y+h,X:mx,Y:my};}return {c:c,lw:{hair:1,line:1.5,bold:2.5},mute:false,frame:frame,area:area,axes:function(id){var b=area(id);raw.strokeStyle=c.rule;raw.lineWidth=1;raw.beginPath();raw.moveTo(b.x,b.y);raw.lineTo(b.x,b.y1);raw.lineTo(b.x1,b.y1);raw.stroke();},clip:function(){},unclip:function(){},label:function(text,x,y){if(labels>=3){frame.report.dropped.push(String(text));return;}labels++;raw.fillStyle=c.ink;raw.font="12px sans-serif";raw.fillText(String(text).slice(0,18),x,y);},mark:function(){},readout:function(id,v){frame.readouts[id]=v;},say:function(id){frame.say=String(id||"");},fmt:function(v,d){var n=+v;if(n!==n)return "";return n.toFixed(d||0);},font:function(){return "12px sans-serif";},handle:function(id,x,y){frame.handles.push({id:id,x:x,y:y});raw.beginPath();raw.arc(x,y,6.5,0,6.2832);raw.fill();},pick:function(){},tip:function(){},mix:function(color){return color;}};}`;

export function srcdoc(draw, widget) {
  const methods = JSON.stringify(CANVAS_METHODS);
  const props = JSON.stringify(CANVAS_PROPS);
  const math = JSON.stringify(MATH_NAMES);
  const v04 = Boolean(widget && widget.version === "rrm-widget/0.4");
  const meta = v04
    ? JSON.stringify({ areas: widget.areas || [], readouts: widget.readouts || [], marks: widget.marks || [] }).replace(/</g, "\\u003c")
    : "";
  const prelude = v04 ? BOOT : "";
  const run = v04
    ? `var ui=bootUi(${meta},raw,state);draw(ctx,state,Number(data.t)||0,ui);var pix=sample(raw);parentWin.postMessage({type:"rrm-live",ok:pix>0,reason:pix>0?"frame":"blank",pixels:pix,frame:ui.frame},"*");`
    : `draw(ctx,state,Number(data.t)||0);var pix=sample(raw);parentWin.postMessage({type:"rrm-live",ok:pix>0,reason:pix>0?"frame":"blank",pixels:pix},"*");`;
  return `<!DOCTYPE html><html><head><meta http-equiv="Content-Security-Policy" content="${CSP}"><style>html,body{margin:0;background:#f4efe5;overflow:hidden}canvas{display:block;width:100%;height:100%}</style></head><body><canvas id="c" width="${HOST.canvas_w}" height="${HOST.canvas_h}"></canvas><script>(function(RealMath){var parentWin=window.parent;var canvas=document.getElementById("c");var dpr=RealMath.min(2,window.devicePixelRatio||1);canvas.width=${HOST.canvas_w}*dpr;canvas.height=${HOST.canvas_h}*dpr;var raw=canvas.getContext("2d");raw.scale(dpr,dpr);var ctx=Object.create(null);var methods=${methods};var props=${props};var i;for(i=0;i<methods.length;i++){(function(name){ctx[name]=function(){return raw[name].apply(raw,arguments);};})(methods[i]);}for(i=0;i<props.length;i++){(function(name){Object.defineProperty(ctx,name,{enumerable:true,get:function(){return raw[name];},set:function(v){raw[name]=v;}});})(props[i]);}var mathNames=${math};var SafeMath=Object.create(null);for(i=0;i<mathNames.length;i++)SafeMath[mathNames[i]]=RealMath[mathNames[i]];var Math=SafeMath;${prelude}${embed(draw)};window.addEventListener("message",function(ev){if(ev.source!==parentWin)return;var data=ev.data;if(!data||data.type!=="rrm-params")return;var state=Object.create(null);var incoming=data.state||{};var key;for(key in incoming){if(Object.prototype.hasOwnProperty.call(incoming,key))state[key]=incoming[key];}try{${run}}catch(err){parentWin.postMessage({type:"rrm-live",ok:false,reason:"throw"},"*");}});parentWin.postMessage({type:"rrm-live",ok:true,reason:"ready"},"*");function sample(context){try{var data=context.getImageData(0,0,canvas.width,canvas.height).data;var n=0,p;for(p=3;p<data.length;p+=64)if(data[p]>8)n++;return n;}catch(e){return 1;}}})(Math);</script></body></html>`;
}

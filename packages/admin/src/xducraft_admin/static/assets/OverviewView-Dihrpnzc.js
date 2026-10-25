import{aF as ne,M as R,J as h,K as E,L as _,aH as le,aI as ie,d as O,X as D,o as s,n as c,$ as y,Z as u,a1 as de,R as se,a3 as ce,cw as ue,a7 as ve,T as fe,q as V,a4 as me,P as pe,Q as ge,b0 as be,H as he,af as _e,ag as ye,F as Q,a2 as ke,an as G,bF as xe,r as I,p as we,v as Ce,b as m,h as i,w as n,u as o,B as A,c as p,g as N,C as J,b$ as q,f as x,N as F,t as b,x as U,bO as W,cx as ze,cy as Re,E as X,a8 as Z}from"./index-D7jJeIkb.js";import{R as Se,E as K}from"./RefreshOutline-B8EeCjG8.js";import{T as Y}from"./Tag-D_NJVMjz.js";import{u as Be,A as ee,_ as Pe}from"./_plugin-vue_export-helper-Cq19G-ca.js";let re=!1;function $e(){if(ne&&window.CSS&&!re&&(re=!0,"registerProperty"in window?.CSS))try{CSS.registerProperty({name:"--n-color-start",syntax:"<color>",inherits:!1,initialValue:"#0000"}),CSS.registerProperty({name:"--n-color-end",syntax:"<color>",inherits:!1,initialValue:"#0000"})}catch{}}var Ee=R([h("list",`
 --n-merged-border-color: var(--n-border-color);
 --n-merged-color: var(--n-color);
 --n-merged-color-hover: var(--n-color-hover);
 margin: 0;
 font-size: var(--n-font-size);
 transition:
 background-color .3s var(--n-bezier),
 color .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 padding: 0;
 list-style-type: none;
 color: var(--n-text-color);
 background-color: var(--n-merged-color);
 `,[E("show-divider",[h("list-item",[R("&:not(:last-child)",[_("divider",`
 background-color: var(--n-merged-border-color);
 `)])])]),E("clickable",[h("list-item",`
 cursor: pointer;
 `)]),E("bordered",`
 border: 1px solid var(--n-merged-border-color);
 border-radius: var(--n-border-radius);
 `),E("hoverable",[h("list-item",`
 border-radius: var(--n-border-radius);
 `,[R("&:hover",`
 background-color: var(--n-merged-color-hover);
 `,[_("divider",`
 background-color: transparent;
 `)])])]),E("bordered, hoverable",[h("list-item",`
 padding: 12px 20px;
 `),_("header, footer",`
 padding: 12px 20px;
 `)]),_("header, footer",`
 padding: 12px 0;
 box-sizing: border-box;
 transition: border-color .3s var(--n-bezier);
 `,[R("&:not(:last-child)",`
 border-bottom: 1px solid var(--n-merged-border-color);
 `)]),h("list-item",`
 position: relative;
 padding: 12px 0; 
 box-sizing: border-box;
 display: flex;
 flex-wrap: nowrap;
 align-items: center;
 transition:
 background-color .3s var(--n-bezier),
 border-color .3s var(--n-bezier);
 `,[_("prefix",`
 margin-right: 20px;
 flex: 0;
 `),_("suffix",`
 margin-left: 20px;
 flex: 0;
 `),_("main",`
 flex: 1;
 `),_("divider",`
 height: 1px;
 position: absolute;
 bottom: 0;
 left: 0;
 right: 0;
 background-color: transparent;
 transition: background-color .3s var(--n-bezier);
 pointer-events: none;
 `)])]),le(h("list",`
 --n-merged-color-hover: var(--n-color-hover-modal);
 --n-merged-color: var(--n-color-modal);
 --n-merged-border-color: var(--n-border-color-modal);
 `)),ie(h("list",`
 --n-merged-color-hover: var(--n-color-hover-popover);
 --n-merged-color: var(--n-color-popover);
 --n-merged-border-color: var(--n-border-color-popover);
 `))]);const Ve={...D.props,size:{type:String,default:"medium"},bordered:Boolean,clickable:Boolean,hoverable:Boolean,showDivider:{type:Boolean,default:!0}},ae=pe("n-list");var oe=O({name:"List",props:Ve,slots:Object,setup(r){const{mergedClsPrefixRef:e,inlineThemeDisabled:l,mergedRtlRef:v}=se(r),d=ce("List",v,e),g=D("List","-list",Ee,ue,r,e);ve(ae,{showDividerRef:fe(r,"showDivider"),mergedClsPrefixRef:e});const w=V(()=>{const{common:{cubicBezierEaseInOut:C},self:{fontSize:z,textColor:f,color:t,colorModal:a,colorPopover:S,borderColor:H,borderColorModal:B,borderColorPopover:P,borderRadius:j,colorHover:M,colorHoverModal:L,colorHoverPopover:$}}=g.value;return{"--n-font-size":z,"--n-bezier":C,"--n-text-color":f,"--n-color":t,"--n-border-radius":j,"--n-border-color":H,"--n-border-color-modal":B,"--n-border-color-popover":P,"--n-color-modal":a,"--n-color-popover":S,"--n-color-hover":M,"--n-color-hover-modal":L,"--n-color-hover-popover":$}}),k=l?me("list",void 0,w,r):void 0;return{mergedClsPrefix:e,rtlEnabled:d,cssVars:l?void 0:w,themeClass:k?.themeClass,onRender:k?.onRender}},render(){const{$slots:r,mergedClsPrefix:e,onRender:l}=this;return l?.(),s(),c("ul",{class:y([`${e}-list`,this.rtlEnabled&&`${e}-list--rtl`,this.bordered&&`${e}-list--bordered`,this.showDivider&&`${e}-list--show-divider`,this.hoverable&&`${e}-list--hoverable`,this.clickable&&`${e}-list--clickable`,this.themeClass]),style:de(this.cssVars)},[r.header?(s(),c("div",{key:0,class:y(`${e}-list__header`)},[u(()=>r.header())],2)):u(()=>null),u(()=>r.default?.()),r.footer?(s(),c("div",{key:2,class:y(`${e}-list__footer`)},[u(()=>r.footer())],2)):u(()=>null)],6)}}),te=O({name:"ListItem",slots:Object,setup(){const r=ge(ae,null);return r||be("list-item","`n-list-item` must be placed in `n-list`."),{showDivider:r.showDividerRef,mergedClsPrefix:r.mergedClsPrefixRef}},render(){const{$slots:r,mergedClsPrefix:e}=this;return s(),c("li",{class:y(`${e}-list-item`)},[r.prefix?(s(),c("div",{key:0,class:y(`${e}-list-item__prefix`)},[u(()=>r.prefix())],2)):u(()=>null),r.default?(s(),c("div",{key:2,class:y(`${e}-list-item__main`)},[u(()=>r.default())],2)):u(()=>null),r.suffix?(s(),c("div",{key:4,class:y(`${e}-list-item__suffix`)},[u(()=>r.suffix())],2)):u(()=>null),u(()=>this.showDivider&&(s(),c("div",{class:y(`${e}-list-item__divider`)},null,2)))],2)}});function je(r){const{heightSmall:e,heightMedium:l,heightLarge:v,borderRadius:d}=r;return{color:"#eee",colorEnd:"#ddd",borderRadius:d,heightSmall:e,heightMedium:l,heightLarge:v}}const Le={common:he,self:je};var Ie=R([h("skeleton",`
 height: 1em;
 width: 100%;
 transition:
 --n-color-start .3s var(--n-bezier),
 --n-color-end .3s var(--n-bezier),
 background-color .3s var(--n-bezier);
 animation: 2s skeleton-loading infinite cubic-bezier(0.36, 0, 0.64, 1);
 background-color: var(--n-color-start);
 `),R("@keyframes skeleton-loading",`
 0% {
 background: var(--n-color-start);
 }
 40% {
 background: var(--n-color-end);
 }
 80% {
 background: var(--n-color-start);
 }
 100% {
 background: var(--n-color-start);
 }
 `)]);const Ne={...D.props,text:Boolean,round:Boolean,circle:Boolean,height:[String,Number],width:[String,Number],size:String,repeat:{type:Number,default:1},animated:{type:Boolean,default:!0},sharp:{type:Boolean,default:!0}};var Oe=O({name:"Skeleton",inheritAttrs:!1,props:Ne,setup(r){$e();const{mergedClsPrefixRef:e,mergedComponentPropsRef:l}=se(r),v=V(()=>r.size||l?.value?.Skeleton?.size),d=D("Skeleton","-skeleton",Ie,Le,r,e);return{mergedClsPrefix:e,style:V(()=>{const g=d.value,{common:{cubicBezierEaseInOut:w}}=g,k=g.self,{color:C,colorEnd:z,borderRadius:f}=k;let t;const{circle:a,sharp:S,round:H,width:B,height:P,text:j,animated:M}=r,L=v.value;L!==void 0&&(t=k[ke("height",L)]);const $=a?B??P??t:B,T=(a?B??P:P)??t;return{display:j?"inline-block":"",verticalAlign:j?"-0.125em":"",borderRadius:a?"50%":H?"4096px":S?"":f,width:typeof $=="number"?G($):$,height:typeof T=="number"?G(T):T,animation:M?"":"none","--n-bezier":w,"--n-color-start":C,"--n-color-end":z}})}},render(){const{repeat:r,style:e,mergedClsPrefix:l,$attrs:v}=this,d=_e("div",ye({class:`${l}-skeleton`,style:e},v));return r>1?(s(),c(Q,{key:1},[u(()=>xe(r,null).map(g=>[d,`
`]))],64)):d}});const De={class:"page system-page"},He={class:"page-intro"},Me={key:3,class:"system-grid"},Te={class:"bot-info"},Ae={class:"bot-avatar"},qe={class:"bot-id"},Fe={key:0,class:"muted"},Ke=O({__name:"OverviewView",setup(r){const e=I(null),l=I(null),v=I(!1),d=I("");let g=0;we(()=>{g++});const w=Be(),k=V(()=>new Set((l.value?.plugins??[]).filter(f=>!f.managed).map(f=>f.id))),C=V(()=>e.value?.plugins.filter(f=>k.value.has(f.id))??[]);async function z(){const f=++g;d.value="",v.value=!0;const[t,a]=await Promise.allSettled([X("/api/overview"),X("/api/plugins")]);f===g&&(t.status==="fulfilled"&&(e.value=t.value,Z.connectedBots=t.value.bots.filter(S=>S.connected).length,Z.restartRequired=t.value.restart_required),a.status==="fulfilled"&&(l.value=a.value),(t.status==="rejected"||a.status==="rejected")&&(d.value=t.status==="rejected"?t.reason instanceof Error?t.reason.message:"读取系统状态失败":"系统服务目录暂时不可用；为避免混入业务插件，暂不显示服务列表。",w.error(d.value)),v.value=!1)}return Ce(z),(f,t)=>(s(),c("main",De,[m("div",He,[t[1]||(t[1]=m("div",null,[m("h1",{class:"page-heading"},"系统"),m("p",{class:"page-subtitle"},"账号连接与基础服务")],-1)),i(o(A),{secondary:"",loading:v.value,onClick:z},{icon:n(()=>[i(o(F),{component:o(Se)},null,8,["component"])]),default:n(()=>[t[0]||(t[0]=x("刷新",-1))]),_:1},8,["loading"])]),d.value?(s(),p(o(ee),{key:0,type:"error",class:"page-alert"},{default:n(()=>[x(b(d.value)+"；"+b(e.value?"已保留上次成功读取的主机状态。":"当前状态尚未确认。"),1)]),_:1})):N("",!0),e.value?.restart_required?(s(),p(o(ee),{key:1,type:"warning",class:"page-alert"},{default:n(()=>[...t[2]||(t[2]=[x("有启动参数已经保存，需要在合适时间手动重启后生效。",-1)])]),_:1})):N("",!0),v.value&&!e.value?(s(),p(o(Oe),{key:2,text:"",repeat:6})):e.value?(s(),c("div",Me,[i(o(J),{title:"Bot 连接"},{default:n(()=>[e.value.bots.length?(s(),p(o(oe),{key:1},{default:n(()=>[(s(!0),c(Q,null,U(e.value.bots,a=>(s(),p(o(te),{key:a.bot_id},{default:n(()=>[i(o(q),{justify:"space-between",align:"center"},{default:n(()=>[m("div",Te,[m("div",Ae,b(Array.from(a.nickname||"Bot").slice(0,1).join("")),1),m("div",null,[m("strong",null,b(a.nickname||"昵称暂不可用"),1),m("span",qe,"QQ "+b(a.bot_id),1)])]),i(o(Y),{type:a.connected?"success":"warning",bordered:!1,round:""},{default:n(()=>[x(b(a.connected?"已连接":"未连接"),1)]),_:2},1032,["type"])]),_:2},1024)]),_:2},1024))),128))]),_:1})):(s(),p(o(K),{key:0,description:"当前没有 Bot 连接"}))]),_:1}),i(o(J),{title:"基础服务"},{default:n(()=>[l.value&&!C.value.length?(s(),p(o(K),{key:0,description:"没有单独报告的基础服务"})):l.value?(s(),p(o(oe),{key:2},{default:n(()=>[(s(!0),c(Q,null,U(C.value,a=>(s(),p(o(te),{key:a.id},{default:n(()=>[i(o(q),{justify:"space-between",align:"center"},{default:n(()=>[m("span",null,b(a.name),1),i(o(Y),{type:a.loaded?"success":"error",bordered:!1,round:""},{default:n(()=>[x(b(a.loaded?"运行中":"不可用"),1)]),_:2},1032,["type"])]),_:2},1024),a.reason?(s(),c("div",Fe,b(a.reason),1)):N("",!0)]),_:2},1024))),128))]),_:1})):(s(),p(o(K),{key:1,description:"服务目录尚未确认"}))]),_:1})])):N("",!0),i(o(q),{class:"system-actions"},{default:n(()=>[i(o(W),{to:"/groups"},{default:n(()=>[i(o(A),{type:"primary"},{icon:n(()=>[i(o(F),{component:o(ze)},null,8,["component"])]),default:n(()=>[t[3]||(t[3]=x("管理群聊",-1))]),_:1})]),_:1}),i(o(W),{to:"/plugins"},{default:n(()=>[i(o(A),null,{icon:n(()=>[i(o(F),{component:o(Re)},null,8,["component"])]),default:n(()=>[t[4]||(t[4]=x("管理插件",-1))]),_:1})]),_:1})]),_:1})]))}}),We=Pe(Ke,[["__scopeId","data-v-caa09fbe"]]);export{We as default};

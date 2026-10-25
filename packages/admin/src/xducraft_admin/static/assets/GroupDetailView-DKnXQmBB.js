import{H as Ue,_ as Me,I as Re,J as j,K as E,L as F,M as U,O as we,P as Le,Q as Oe,R as ye,S as Ie,r as I,T as Ce,U as Pe,V as Se,W as te,d as ae,X as ue,Y as je,o as l,n as R,b as B,Z as Y,$ as H,a0 as Ve,a1 as De,q as $,a2 as ie,a3 as Te,a4 as Ae,c as D,a5 as Ke,a6 as Qe,a7 as We,p as Ye,s as fe,F as ee,h as k,w as u,u as n,B as G,g as O,x as ge,t as M,y as _e,z as Je,E as se,a8 as he,G as Xe,f as z,N as oe,a9 as Ze,a as eo}from"./index-D7jJeIkb.js";import{R as ze,E as me}from"./RefreshOutline-B8EeCjG8.js";import{T as xe}from"./Tag-D_NJVMjz.js";import{A as ke,_ as oo}from"./_plugin-vue_export-helper-Cq19G-ca.js";import{S as $e}from"./Spin-O0CzrVPJ.js";import{G as to}from"./GroupIdentity-DzZ73IJb.js";import{P as ao,a as Be,S as ro}from"./PluginSettingsModal-D-9g-8bM.js";import"./FormItem-CFPSDT0w.js";import"./Input-BbRwQ7B7.js";function no(t){const{borderColor:e,primaryColor:r,baseColor:s,textColorDisabled:h,inputColorDisabled:m,textColor2:c,opacityDisabled:i,borderRadius:b,fontSizeSmall:x,fontSizeMedium:C,fontSizeLarge:S,heightSmall:_,heightMedium:v,heightLarge:y,lineHeight:V}=t;return{...Me,labelLineHeight:V,buttonHeightSmall:_,buttonHeightMedium:v,buttonHeightLarge:y,fontSizeSmall:x,fontSizeMedium:C,fontSizeLarge:S,boxShadow:`inset 0 0 0 1px ${e}`,boxShadowActive:`inset 0 0 0 1px ${r}`,boxShadowFocus:`inset 0 0 0 1px ${r}, 0 0 0 2px ${Re(r,{alpha:.2})}`,boxShadowHover:`inset 0 0 0 1px ${r}`,boxShadowDisabled:`inset 0 0 0 1px ${e}`,color:s,colorDisabled:m,colorActive:"#0000",textColor:c,textColorDisabled:h,dotColorActive:r,dotColorDisabled:e,buttonBorderColor:e,buttonBorderColorActive:r,buttonBorderColorHover:e,buttonColor:s,buttonColorActive:s,buttonTextColor:c,buttonTextColorActive:r,buttonTextColorHover:r,opacityDisabled:i,buttonBoxShadowFocus:`inset 0 0 0 1px ${r}, 0 0 0 2px ${Re(r,{alpha:.3})}`,buttonBoxShadowHover:"inset 0 0 0 1px #0000",buttonBoxShadow:"inset 0 0 0 1px #0000",buttonBorderRadius:b}}const Ne={common:Ue,self:no};var lo=j("radio",`
 line-height: var(--n-label-line-height);
 outline: none;
 position: relative;
 user-select: none;
 -webkit-user-select: none;
 display: inline-flex;
 align-items: flex-start;
 flex-wrap: nowrap;
 font-size: var(--n-font-size);
 word-break: break-word;
`,[E("checked",[F("dot",`
 background-color: var(--n-color-active);
 `)]),F("dot-wrapper",`
 position: relative;
 flex-shrink: 0;
 flex-grow: 0;
 width: var(--n-radio-size);
 `),j("radio-input",`
 position: absolute;
 border: 0;
 width: 0;
 height: 0;
 opacity: 0;
 margin: 0;
 `),F("dot",`
 position: absolute;
 top: 50%;
 left: 0;
 transform: translateY(-50%);
 height: var(--n-radio-size);
 width: var(--n-radio-size);
 background: var(--n-color);
 box-shadow: var(--n-box-shadow);
 border-radius: 50%;
 transition:
 background-color .3s var(--n-bezier),
 box-shadow .3s var(--n-bezier);
 `,[U("&::before",`
 content: "";
 opacity: 0;
 position: absolute;
 left: 4px;
 top: 4px;
 height: calc(100% - 8px);
 width: calc(100% - 8px);
 border-radius: 50%;
 transform: scale(.8);
 background: var(--n-dot-color-active);
 transition: 
 opacity .3s var(--n-bezier),
 background-color .3s var(--n-bezier),
 transform .3s var(--n-bezier);
 `),E("checked",{boxShadow:"var(--n-box-shadow-active)"},[U("&::before",`
 opacity: 1;
 transform: scale(1);
 `)])]),F("label",`
 color: var(--n-text-color);
 padding: var(--n-label-padding);
 font-weight: var(--n-label-font-weight);
 display: inline-block;
 transition: color .3s var(--n-bezier);
 `),we("disabled",`
 cursor: pointer;
 `,[U("&:hover",[F("dot",{boxShadow:"var(--n-box-shadow-hover)"})]),E("focus",[U("&:not(:active)",[F("dot",{boxShadow:"var(--n-box-shadow-focus)"})])])]),E("disabled",`
 cursor: not-allowed;
 `,[F("dot",{boxShadow:"var(--n-box-shadow-disabled)",backgroundColor:"var(--n-color-disabled)"},[U("&::before",{backgroundColor:"var(--n-dot-color-disabled)"}),E("checked",`
 opacity: 1;
 `)]),F("label",{color:"var(--n-text-color-disabled)"}),j("radio-input",`
 cursor: not-allowed;
 `)])]);const Ee={name:String,value:{type:[String,Number,Boolean],default:"on"},checked:{type:Boolean,default:void 0},defaultChecked:Boolean,disabled:{type:Boolean,default:void 0},label:String,size:String,onUpdateChecked:[Function,Array],"onUpdate:checked":[Function,Array],checkedValue:{type:Boolean,default:void 0}},He=Le("n-radio-group");function qe(t){const e=Oe(He,null),{mergedClsPrefixRef:r,mergedComponentPropsRef:s}=ye(t),h=Ie(t,{mergedSize(w){const{size:d}=t;if(d!==void 0)return d;if(e){const{mergedSizeRef:{value:P}}=e;if(P!==void 0)return P}if(w)return w.mergedSize.value;const f=s?.value?.Radio?.size;return f||"medium"},mergedDisabled(w){return!!(t.disabled||e?.disabledRef.value||w?.disabled.value)}}),{mergedSizeRef:m,mergedDisabledRef:c}=h,i=I(null),b=I(null),x=I(t.defaultChecked),C=Ce(t,"checked"),S=Pe(C,x),_=Se(()=>e?e.valueRef.value===t.value:S.value),v=Se(()=>{const{name:w}=t;if(w!==void 0)return w;if(e)return e.nameRef.value}),y=I(!1);function V(){if(e){const{doUpdateValue:w}=e,{value:d}=t;te(w,d)}else{const{onUpdateChecked:w,"onUpdate:checked":d}=t,{nTriggerFormInput:f,nTriggerFormChange:P}=h;w&&te(w,!0),d&&te(d,!0),f(),P(),x.value=!0}}function T(){c.value||_.value||V()}function p(){T(),i.value&&(i.value.checked=_.value)}function q(){y.value=!1}function A(){y.value=!0}return{mergedClsPrefix:e?e.mergedClsPrefixRef:r,inputRef:i,labelRef:b,mergedName:v,mergedDisabled:c,renderSafeChecked:_,focus:y,mergedSize:m,handleRadioInputChange:p,handleRadioInputBlur:q,handleRadioInputFocus:A}}const so=["value","name","checked","disabled","onChange","onFocus","onBlur"],io={...ue.props,...Ee};var uo=ae({name:"Radio",props:io,setup(t){const e=qe(t),r=ue("Radio","-radio",lo,Ne,t,e.mergedClsPrefix),s=$(()=>{const{mergedSize:{value:x}}=e,{common:{cubicBezierEaseInOut:C},self:{boxShadow:S,boxShadowActive:_,boxShadowDisabled:v,boxShadowFocus:y,boxShadowHover:V,color:T,colorDisabled:p,colorActive:q,textColor:A,textColorDisabled:w,dotColorActive:d,dotColorDisabled:f,labelPadding:P,labelLineHeight:K,labelFontWeight:Q,[ie("fontSize",x)]:J,[ie("radioSize",x)]:W}}=r.value;return{"--n-bezier":C,"--n-label-line-height":K,"--n-label-font-weight":Q,"--n-box-shadow":S,"--n-box-shadow-active":_,"--n-box-shadow-disabled":v,"--n-box-shadow-focus":y,"--n-box-shadow-hover":V,"--n-color":T,"--n-color-active":q,"--n-color-disabled":p,"--n-dot-color-active":d,"--n-dot-color-disabled":f,"--n-font-size":J,"--n-radio-size":W,"--n-text-color":A,"--n-text-color-disabled":w,"--n-label-padding":P}}),{inlineThemeDisabled:h,mergedClsPrefixRef:m,mergedRtlRef:c}=ye(t),i=Te("Radio",c,m),b=h?Ae("radio",$(()=>e.mergedSize.value[0]),s,t):void 0;return Object.assign(e,{rtlEnabled:i,cssVars:h?void 0:s,themeClass:b?.themeClass,onRender:b?.onRender})},render(){const{$slots:t,mergedClsPrefix:e,onRender:r,label:s}=this;return r?.(),(()=>{const h=je("f8c6901d8cd45c02");return l(),R("label",{class:H([`${e}-radio`,this.themeClass,this.rtlEnabled&&`${e}-radio--rtl`,this.mergedDisabled&&`${e}-radio--disabled`,this.renderSafeChecked&&`${e}-radio--checked`,this.focus&&`${e}-radio--focus`]),style:De(this.cssVars)},[B("div",{class:H(`${e}-radio__dot-wrapper`)},[h[0]||(h[0]=Y(" ",-1)),B("div",{class:H([`${e}-radio__dot`,this.renderSafeChecked&&`${e}-radio__dot--checked`])},null,2),B("input",{ref:"inputRef",type:"radio",class:H(`${e}-radio-input`),value:this.value,name:this.mergedName,checked:this.renderSafeChecked,disabled:this.mergedDisabled,onChange:this.handleRadioInputChange,onFocus:this.handleRadioInputFocus,onBlur:this.handleRadioInputBlur},null,42,so)],2),Y(()=>Ve(t.default,m=>!m&&!s?null:(l(),R("div",{ref:"labelRef",class:H(`${e}-radio__label`)},[Y(()=>m||s)],2))))],6)})()}});const co=["value","name","checked","disabled","onChange","onFocus","onBlur"];var bo=ae({name:"RadioButton",props:Ee,setup:qe,render(){const{mergedClsPrefix:t}=this;return l(),R("label",{class:H([`${t}-radio-button`,this.mergedDisabled&&`${t}-radio-button--disabled`,this.renderSafeChecked&&`${t}-radio-button--checked`,this.focus&&[`${t}-radio-button--focus`]])},[B("input",{ref:"inputRef",type:"radio",class:H(`${t}-radio-input`),value:this.value,name:this.mergedName,checked:this.renderSafeChecked,disabled:this.mergedDisabled,onChange:this.handleRadioInputChange,onFocus:this.handleRadioInputFocus,onBlur:this.handleRadioInputBlur},null,42,co),B("div",{class:H(`${t}-radio-button__state-border`)},null,2),Y(()=>Ve(this.$slots.default,e=>!e&&!this.label?null:(l(),R("div",{ref:"labelRef",class:H(`${t}-radio__label`)},[Y(()=>e||this.label)],2))))],2)}}),vo=j("radio-group",`
 display: inline-block;
 font-size: var(--n-font-size);
`,[F("splitor",`
 display: inline-block;
 vertical-align: bottom;
 width: 1px;
 transition:
 background-color .3s var(--n-bezier),
 opacity .3s var(--n-bezier);
 background: var(--n-button-border-color);
 `,[E("checked",{backgroundColor:"var(--n-button-border-color-active)"}),E("disabled",{opacity:"var(--n-opacity-disabled)"})]),E("button-group",`
 white-space: nowrap;
 height: var(--n-height);
 line-height: var(--n-height);
 `,[j("radio-button",{height:"var(--n-height)",lineHeight:"var(--n-height)"}),F("splitor",{height:"var(--n-height)"})]),j("radio-button",`
 vertical-align: bottom;
 outline: none;
 position: relative;
 user-select: none;
 -webkit-user-select: none;
 display: inline-block;
 box-sizing: border-box;
 padding-left: 14px;
 padding-right: 14px;
 white-space: nowrap;
 transition:
 background-color .3s var(--n-bezier),
 opacity .3s var(--n-bezier),
 border-color .3s var(--n-bezier),
 color .3s var(--n-bezier);
 background: var(--n-button-color);
 color: var(--n-button-text-color);
 border-top: 1px solid var(--n-button-border-color);
 border-bottom: 1px solid var(--n-button-border-color);
 `,[j("radio-input",`
 pointer-events: none;
 position: absolute;
 border: 0;
 border-radius: inherit;
 left: 0;
 right: 0;
 top: 0;
 bottom: 0;
 opacity: 0;
 z-index: 1;
 `),F("state-border",`
 z-index: 1;
 pointer-events: none;
 position: absolute;
 box-shadow: var(--n-button-box-shadow);
 transition: box-shadow .3s var(--n-bezier);
 left: -1px;
 bottom: -1px;
 right: -1px;
 top: -1px;
 `),U("&:first-child",`
 border-top-left-radius: var(--n-button-border-radius);
 border-bottom-left-radius: var(--n-button-border-radius);
 border-left: 1px solid var(--n-button-border-color);
 `,[F("state-border",`
 border-top-left-radius: var(--n-button-border-radius);
 border-bottom-left-radius: var(--n-button-border-radius);
 `)]),U("&:last-child",`
 border-top-right-radius: var(--n-button-border-radius);
 border-bottom-right-radius: var(--n-button-border-radius);
 border-right: 1px solid var(--n-button-border-color);
 `,[F("state-border",`
 border-top-right-radius: var(--n-button-border-radius);
 border-bottom-right-radius: var(--n-button-border-radius);
 `)]),we("disabled",`
 cursor: pointer;
 `,[U("&:hover",[F("state-border",`
 transition: box-shadow .3s var(--n-bezier);
 box-shadow: var(--n-button-box-shadow-hover);
 `),we("checked",{color:"var(--n-button-text-color-hover)"})]),E("focus",[U("&:not(:active)",[F("state-border",{boxShadow:"var(--n-button-box-shadow-focus)"})])])]),E("checked",`
 background: var(--n-button-color-active);
 color: var(--n-button-text-color-active);
 border-color: var(--n-button-border-color-active);
 `),E("disabled",`
 cursor: not-allowed;
 opacity: var(--n-opacity-disabled);
 `)])]);const po=["onFocusin","onFocusout"];function fo(t,e,r){const s=[];let h=!1;for(let m=0;m<t.length;++m){const c=t[m],i=c.type?.name;i==="RadioButton"&&(h=!0);const b=c.props;if(i!=="RadioButton"){s.push(c);continue}if(m===0)s.push(c);else{const x=s[s.length-1].props,C=e===x.value,S=x.disabled,_=e===b.value,v=b.disabled,y=(C?2:0)+(S?0:1),V=(_?2:0)+(v?0:1),T={[`${r}-radio-group__splitor--disabled`]:S,[`${r}-radio-group__splitor--checked`]:C},p={[`${r}-radio-group__splitor--disabled`]:v,[`${r}-radio-group__splitor--checked`]:_},q=y<V?p:T;s.push((l(),R("div",{key:1,class:H([`${r}-radio-group__splitor`,q])},null,2)),c)}}return{children:s,isButtonGroup:h}}const go={...ue.props,name:String,options:Array,labelField:{type:String,default:"label"},valueField:{type:String,default:"value"},value:[String,Number,Boolean],defaultValue:{type:[String,Number,Boolean],default:null},size:String,disabled:{type:Boolean,default:void 0},"onUpdate:value":[Function,Array],onUpdateValue:[Function,Array]};var ho=ae({name:"RadioGroup",props:go,setup(t){const e=I(null),{mergedSizeRef:r,mergedDisabledRef:s,nTriggerFormChange:h,nTriggerFormInput:m,nTriggerFormBlur:c,nTriggerFormFocus:i}=Ie(t),{mergedClsPrefixRef:b,inlineThemeDisabled:x,mergedRtlRef:C}=ye(t),S=ue("Radio","-radio-group",vo,Ne,t,b),_=I(t.defaultValue),v=Ce(t,"value"),y=Pe(v,_);function V(d){const{onUpdateValue:f,"onUpdate:value":P}=t;f&&te(f,d),P&&te(P,d),_.value=d,h(),m()}function T(d){const{value:f}=e;f&&(f.contains(d.relatedTarget)||i())}function p(d){const{value:f}=e;f&&(f.contains(d.relatedTarget)||c())}We(He,{mergedClsPrefixRef:b,nameRef:Ce(t,"name"),valueRef:y,disabledRef:s,mergedSizeRef:r,doUpdateValue:V});const q=Te("Radio",C,b),A=$(()=>{const{value:d}=r,{common:{cubicBezierEaseInOut:f},self:{buttonBorderColor:P,buttonBorderColorActive:K,buttonBorderRadius:Q,buttonBoxShadow:J,buttonBoxShadowFocus:W,buttonBoxShadowHover:N,buttonColor:X,buttonColorActive:de,buttonTextColor:re,buttonTextColorActive:ce,buttonTextColorHover:ne,opacityDisabled:be,[ie("buttonHeight",d)]:ve,[ie("fontSize",d)]:pe}}=S.value;return{"--n-font-size":pe,"--n-bezier":f,"--n-button-border-color":P,"--n-button-border-color-active":K,"--n-button-border-radius":Q,"--n-button-box-shadow":J,"--n-button-box-shadow-focus":W,"--n-button-box-shadow-hover":N,"--n-button-color":X,"--n-button-color-active":de,"--n-button-text-color":re,"--n-button-text-color-hover":ne,"--n-button-text-color-active":ce,"--n-height":ve,"--n-opacity-disabled":be}}),w=x?Ae("radio-group",$(()=>r.value[0]),A,t):void 0;return{selfElRef:e,rtlEnabled:q,mergedClsPrefix:b,mergedValue:y,handleFocusout:p,handleFocusin:T,cssVars:x?void 0:A,themeClass:w?.themeClass,onRender:w?.onRender}},render(){const{mergedValue:t,mergedClsPrefix:e,handleFocusin:r,handleFocusout:s}=this,{options:h,labelField:m,valueField:c}=this.$props,{children:i,isButtonGroup:b}=fo(h?h.map(x=>{const C=x[c];return l(),D(uo,{key:typeof C=="boolean"?`__n_${C}`:C,value:C,disabled:x.disabled,label:x[m]},null,8,["value","disabled","label"])}):Ke(Qe(this)),t,e);return this.onRender?.(),l(),R("div",{onFocusin:r,onFocusout:s,ref:"selfElRef",class:H([`${e}-radio-group`,this.rtlEnabled&&`${e}-radio-group--rtl`,this.themeClass,b&&`${e}-radio-group--button-group`]),style:De(this.cssVars)},[Y(()=>i)],46,po)}});const mo={xmlns:"http://www.w3.org/2000/svg","xmlns:xlink":"http://www.w3.org/1999/xlink",viewBox:"0 0 512 512"},Fe=ae({name:"ArrowBackOutline",render:function(e,r){return l(),R("svg",mo,r[0]||(r[0]=[B("path",{fill:"none",stroke:"currentColor","stroke-linecap":"round","stroke-linejoin":"round","stroke-width":"48",d:"M244 400L100 256l144-144"},null,-1),B("path",{fill:"none",stroke:"currentColor","stroke-linecap":"round","stroke-linejoin":"round","stroke-width":"48",d:"M120 256h292"},null,-1)]))}}),xo={class:"page group-page"},ko={class:"top-actions"},wo={class:"group-header"},Co={key:0,class:"header-status-badge"},yo={class:"plugin-toolbar"},Ro={key:0,class:"plugin-grid"},So={class:"top-actions"},_o={class:"detail-header"},zo={class:"detail-eyebrow"},$o={class:"page-heading"},Bo={key:0,class:"detail-stack"},Fo={key:0,class:"global-entry"},Io=ae({__name:"GroupDetailView",setup(t){const e=Je(),r=eo(),s=I(null),h=I([]),m=I([]),c=I(""),i=I(!1),b=I("all"),x=I(!1),C=I("global");let S=0,_="";Ye(()=>{S++});const v=$(()=>String(e.params.groupId)),y=$(()=>typeof e.params.plugin=="string"?e.params.plugin:""),V=$(()=>!!y.value),T=$(()=>(s.value?.plugins??[]).filter(a=>a.managed)),p=$(()=>T.value.find(a=>a.short_name===y.value)),q=$(()=>{const a=!!p.value?.resources.global,o=!!p.value?.resources.startup;return a&&o?"全局与启动设置":o?"启动设置":"全局设置"}),A=$(()=>h.value.find(a=>a.group_id===v.value)),w=$(()=>A.value?.name??`群 ${v.value}`),d=$(()=>typeof e.query.groups=="string"?e.query.groups:""),f=$(()=>b.value==="enabled"?T.value.filter(a=>a.control?.config.enabled===!0):T.value),P=[{label:"全部插件",value:"all"},{label:"本群已启用",value:"enabled"}],K=$(()=>`xducraft-group-plugin-filter:${v.value}`),Q=$(()=>`xducraft-group-plugin-scroll:${v.value}`);function J(){const a=e.query.filter;return a==="enabled"||a==="all"?a:localStorage.getItem(K.value)==="enabled"?"enabled":"all"}async function W(){if(V.value)return;await Xe();const a=Number(sessionStorage.getItem(Q.value)??"0");Number.isFinite(a)&&a>0&&window.scrollTo({top:a})}async function N(a=!1){const o=++S,g=v.value;i.value=!0,c.value="",_!==g&&(s.value=null);const[L,Z,le]=await Promise.allSettled([se(`/api/groups/${encodeURIComponent(g)}/plugins`),a?se("/api/groups"):Promise.resolve(null),a?se("/api/overview"):Promise.resolve(null)]);return o!==S||g!==v.value?!1:(L.status==="fulfilled"?(s.value=L.value,_=g):c.value=L.reason instanceof Error?L.reason.message:"读取群插件失败",Z.status==="fulfilled"&&Z.value?(h.value=Z.value.groups,m.value=Z.value.warnings):Z.status==="rejected"&&(m.value=["群目录暂时不可用，当前群身份未能确认。"]),le.status==="fulfilled"&&le.value&&(he.connectedBots=le.value.bots.filter(Ge=>Ge.connected).length,he.restartRequired=le.value.restart_required),i.value=!1,L.status==="fulfilled"&&await W(),L.status==="fulfilled")}function X(a=!0){const o={};return d.value&&(o.groups=d.value),a&&(o.filter=b.value),o}function de(){r.push({name:"groups",query:d.value?{q:d.value}:{}})}function re(a){a!=="all"&&a!=="enabled"||(b.value=a,localStorage.setItem(K.value,a),r.replace({name:"group-plugins",params:{groupId:v.value},query:X()}))}function ce(a){sessionStorage.setItem(Q.value,String(window.scrollY)),r.push({name:"group-plugin-settings",params:{groupId:v.value,plugin:a.short_name},query:X()})}function ne(){r.push({name:"group-plugins",params:{groupId:v.value},query:X()})}function be(a){C.value=a,x.value=!0}function ve(){re("all")}async function pe(){await N();const a=S;try{const o=await se("/api/overview");a===S&&(he.restartRequired=o.restart_required)}catch{}}return fe(v,(a,o)=>{b.value=J(),a!==o&&N(!0)},{immediate:!0}),fe(y,(a,o)=>{o&&!a&&W()}),fe(()=>e.query.filter,a=>{(a==="all"||a==="enabled")&&(b.value=a)}),(a,o)=>(l(),R("main",xo,[V.value?(l(),R(ee,{key:1},[B("div",So,[k(n(G),{text:"",onClick:ne},{icon:u(()=>[k(n(oe),{component:n(Fe)},null,8,["component"])]),default:u(()=>[o[14]||(o[14]=z("返回插件列表",-1))]),_:1}),k(n(G),{loading:i.value,onClick:o[2]||(o[2]=g=>N(!0))},{icon:u(()=>[k(n(oe),{component:n(ze)},null,8,["component"])]),default:u(()=>[o[15]||(o[15]=z("刷新",-1))]),_:1},8,["loading"])]),B("header",_o,[B("div",null,[B("div",zo,M(w.value),1),B("h1",$o,M(p.value?.name??y.value),1)])]),c.value?(l(),D(n(ke),{key:0,type:"error",class:"page-alert"},{default:u(()=>[z(M(c.value)+" ",1),k(n(G),{size:"small",onClick:o[3]||(o[3]=g=>N(!0))},{default:u(()=>[...o[16]||(o[16]=[z("重试",-1)])]),_:1})]),_:1})):O("",!0),k(n($e),{show:i.value,class:_e({"spin-container-min":i.value&&!p.value})},{default:u(()=>[p.value?(l(),R("div",Bo,[k(Be,{plugin:p.value,"group-id":v.value,scope:"group",variant:"detail",refresh:()=>N()},null,8,["plugin","group-id","refresh"]),p.value.resources.global||p.value.resources.startup?(l(),R("section",Fo,[k(n(G),{secondary:"",size:"small",onClick:o[4]||(o[4]=g=>be(p.value.resources.global?"global":"startup"))},{icon:u(()=>[k(n(oe),{component:n(Ze)},null,8,["component"])]),default:u(()=>[z(M(q.value),1)]),_:1})])):O("",!0),p.value.resources.group?(l(),D(ro,{key:p.value.resources.group.path,descriptor:p.value.resources.group,media:p.value.media,title:"本群配置",onSaved:o[5]||(o[5]=g=>N())},null,8,["descriptor","media"])):O("",!0)])):i.value?O("",!0):(l(),D(n(me),{key:1,description:"此业务插件不在当前群目录中"},{extra:u(()=>[k(n(G),{onClick:ne},{default:u(()=>[...o[17]||(o[17]=[z("返回插件列表",-1)])]),_:1})]),_:1}))]),_:1},8,["show","class"]),k(ao,{show:x.value,plugin:p.value??null,"initial-scope":C.value,onClose:o[6]||(o[6]=g=>x.value=!1),onSaved:pe},null,8,["show","plugin","initial-scope"])],64)):(l(),R(ee,{key:0},[B("div",ko,[k(n(G),{text:"",onClick:de},{icon:u(()=>[k(n(oe),{component:n(Fe)},null,8,["component"])]),default:u(()=>[o[7]||(o[7]=z("全部群聊",-1))]),_:1}),k(n(G),{loading:i.value,onClick:o[0]||(o[0]=g=>N(!0))},{icon:u(()=>[k(n(oe),{component:n(ze)},null,8,["component"])]),default:u(()=>[o[8]||(o[8]=z("刷新",-1))]),_:1},8,["loading"])]),B("header",wo,[k(to,{"group-id":v.value,name:w.value,size:58,"name-tag":"h1",eager:""},null,8,["group-id","name"]),A.value?(l(),R("div",Co,[A.value.connected?(l(),D(n(xe),{key:0,size:"small",type:"success",bordered:!1,round:""},{default:u(()=>[...o[9]||(o[9]=[z("在线",-1)])]),_:1})):A.value.stale?(l(),D(n(xe),{key:1,size:"small",type:"warning",bordered:!1,round:""},{default:u(()=>[...o[10]||(o[10]=[z("最近连接",-1)])]),_:1})):(l(),D(n(xe),{key:2,size:"small",bordered:!1,round:""},{default:u(()=>[...o[11]||(o[11]=[z("未连接",-1)])]),_:1}))])):O("",!0)]),c.value?(l(),D(n(ke),{key:0,type:"error",class:"page-alert"},{default:u(()=>[z(M(c.value)+" ",1),k(n(G),{size:"small",onClick:o[1]||(o[1]=g=>N(!0))},{default:u(()=>[...o[12]||(o[12]=[z("重试",-1)])]),_:1})]),_:1})):O("",!0),(l(!0),R(ee,null,ge([...m.value,...s.value?.warnings??[]],g=>(l(),D(n(ke),{key:g,type:"warning",class:"page-alert"},{default:u(()=>[z(M(g),1)]),_:2},1024))),128)),B("div",yo,[k(n(ho),{value:b.value,name:"group-plugin-filter","aria-label":"筛选群插件","onUpdate:value":re},{default:u(()=>[(l(),R(ee,null,ge(P,g=>k(n(bo),{key:g.value,value:g.value},{default:u(()=>[z(M(g.label),1)]),_:2},1032,["value"])),64))]),_:1},8,["value"]),B("span",null,M(f.value.length)+" 个插件",1)]),k(n($e),{show:i.value,class:_e({"spin-container-min":i.value&&!f.value.length})},{default:u(()=>[f.value.length?(l(),R("div",Ro,[(l(!0),R(ee,null,ge(f.value,g=>(l(),D(Be,{key:g.id,plugin:g,"group-id":v.value,scope:"group",variant:"group-list",refresh:()=>N(),onConfigure:L=>ce(g)},null,8,["plugin","group-id","refresh","onConfigure"]))),128))])):!i.value&&b.value==="enabled"?(l(),D(n(me),{key:1,description:"本群还没有已启用的插件",class:"empty-state"},{extra:u(()=>[k(n(G),{type:"primary",secondary:"",onClick:ve},{default:u(()=>[...o[13]||(o[13]=[z("查看全部插件",-1)])]),_:1})]),_:1})):i.value?O("",!0):(l(),D(n(me),{key:2,description:"当前没有可管理的业务插件",class:"empty-state"}))]),_:1},8,["show","class"])],64))]))}}),Go=oo(Io,[["__scopeId","data-v-696ec636"]]);export{Go as default};

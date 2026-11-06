(function(){
  'use strict';
  const TOKEN_KEY='wb_eng_token';
  const CHILD_KEY='englishlab_child_id';
  const AVATARS={fox:'🦊',bear:'🐻',owl:'🦉',bunny:'🐰',panda:'🐼',lion:'🦁'};
  let token=localStorage.getItem(TOKEN_KEY)||'';
  let toastTimer=null;

  function escapeHTML(value){
    return String(value??'').replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
  }
  async function request(path,opts={}){
    const controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),12000);
    const headers=Object.assign({},opts.headers||{});
    if(!headers['Content-Type']&&opts.body)headers['Content-Type']='application/json';
    if(token)headers.Authorization='Bearer '+token;
    try{
      const response=await fetch(path,Object.assign({},opts,{headers,signal:opts.signal||controller.signal}));
      let body={};try{body=await response.json();}catch(e){}
      if(response.status===401){localStorage.removeItem(TOKEN_KEY);token='';}
      return{status:response.status,body};
    }finally{clearTimeout(timer);}
  }
  function toast(message){
    let el=document.getElementById('kidsToast');
    if(!el){el=document.createElement('div');el.id='kidsToast';el.className='toast';document.body.appendChild(el);}
    el.textContent=message;el.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>el.classList.remove('show'),2200);
  }
  function showLoading(show){const el=document.getElementById('kidsLoading');if(el)el.classList.toggle('hide',!show);}
  async function requireUser(){
    if(!token){location.href='/login';return null;}
    try{
      const res=await request('/api/me');
      if(res.status===200)return res.body.user;
    }catch(e){}
    location.href='/login';return null;
  }
  async function listChildren(){const r=await request('/api/children');if(r.status!==200)throw new Error(r.body.error||'档案加载失败');return r.body.children||[];}
  async function createChild(data){const r=await request('/api/children',{method:'POST',body:JSON.stringify(data)});if(r.status!==201)throw new Error(r.body.error||'创建失败');return r.body.child;}
  async function updateChild(id,data){const r=await request('/api/children/'+id,{method:'PUT',body:JSON.stringify(data)});if(r.status!==200)throw new Error(r.body.error||'更新失败');return r.body.child;}
  async function deleteChild(id){const r=await request('/api/children/'+id,{method:'DELETE'});if(r.status!==200)throw new Error(r.body.error||'删除失败');return r.body;}
  async function loadProgress(id){const r=await request('/api/children/'+id+'/progress');if(r.status!==200)throw new Error(r.body.error||'进度加载失败');return r.body.progress||{};}
  async function saveProgress(id,progress){const r=await request('/api/children/'+id+'/progress',{method:'PUT',body:JSON.stringify({progress})});if(r.status!==200)throw new Error(r.body.error||'进度保存失败');return r.body;}
  async function event(id,eventType,module,detail={}){try{await request('/api/children/'+id+'/events',{method:'POST',body:JSON.stringify({event_type:eventType,module,score:detail.score,duration_seconds:detail.duration||0,metadata:detail.metadata||{}})});}catch(e){}}
  async function switchLearningMode(stage,ageBand){
    const r=await request('/api/learning-mode',{method:'PUT',body:JSON.stringify({learning_stage:stage,age_band:ageBand})});
    if(r.status!==200)throw new Error(r.body.error||'学习模式切换失败');
    localStorage.setItem('wb_eng_learning_stage',stage);
    localStorage.setItem('wb_eng_age_band',ageBand);
    return r.body;
  }
  async function switchToAdult(event,control){
    if(event)event.preventDefault();
    if(control){control.setAttribute('aria-busy','true');control.classList.add('busy');}
    showLoading(true);
    try{
      const result=await switchLearningMode('general','13+');
      location.replace(result.landing||'/app/home');
    }catch(error){
      showLoading(false);toast(error.message||'无法返回成人学习台');
      if(control){control.removeAttribute('aria-busy');control.classList.remove('busy');}
    }
    return false;
  }
  function currentChildId(){const n=Number(localStorage.getItem(CHILD_KEY)||0);return Number.isInteger(n)&&n>0?n:0;}
  function setCurrentChild(id){localStorage.setItem(CHILD_KEY,String(id));}
  function clearCurrentChild(){localStorage.removeItem(CHILD_KEY);}
  async function selectedChild(requiredTrack){
    await requireUser();
    const children=await listChildren();
    const id=currentChildId();
    const child=children.find(x=>x.id===id)||(requiredTrack?children.find(x=>x.track===requiredTrack):children[0]);
    if(!child){location.href='/kids?new=1';return null;}
    if(requiredTrack&&child.track!==requiredTrack){
      const match=children.find(x=>x.track===requiredTrack);
      if(match){setCurrentChild(match.id);return match;}
      location.href='/kids?new=1&track='+encodeURIComponent(requiredTrack);return null;
    }
    setCurrentChild(child.id);return child;
  }
  function avatar(id){return AVATARS[id]||AVATARS.fox;}
  function shuffled(items){
    const result=Array.from(items||[]);
    for(let i=result.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[result[i],result[j]]=[result[j],result[i]];}
    return result;
  }
  function speak(text,rate=.85){
    if(!text)return;
    if('speechSynthesis'in window){
      speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(text);u.lang='en-US';u.rate=rate;u.pitch=1.08;speechSynthesis.speak(u);return;
    }
    const audio=new Audio('/api/tts?text='+encodeURIComponent(text));audio.play().catch(()=>{});
  }
  function today(){const d=new Date();return d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');}
  function normalizeProgress(value){
    const p=value&&typeof value==='object'&&!Array.isArray(value)?value:{};
    if(!p.kindergarten||typeof p.kindergarten!=='object')p.kindergarten={completed:[],stars:0,stickers:[]};
    if(!Array.isArray(p.kindergarten.completed))p.kindergarten.completed=[];
    if(!Array.isArray(p.kindergarten.stickers))p.kindergarten.stickers=[];
    if(!p.primary||typeof p.primary!=='object')p.primary={completed:[],stars:0,coins:0,scores:{}};
    if(!Array.isArray(p.primary.completed))p.primary.completed=[];
    if(!p.primary.scores||typeof p.primary.scores!=='object')p.primary.scores={};
    if(!p.activityDays||typeof p.activityDays!=='object')p.activityDays={};
    return p;
  }
  window.KidsAPI={request,requireUser,listChildren,createChild,updateChild,deleteChild,loadProgress,saveProgress,event,switchLearningMode,switchToAdult,currentChildId,setCurrentChild,clearCurrentChild,selectedChild,avatar,shuffled,speak,today,normalizeProgress,escapeHTML,toast,showLoading,avatars:AVATARS};
})();

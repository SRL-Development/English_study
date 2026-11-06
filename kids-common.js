(function(){
  'use strict';
  const TOKEN_KEY='wb_eng_token';
  const CHILD_KEY='englishlab_child_id';
  const AVATARS={fox:'🦊',bear:'🐻',owl:'🦉',bunny:'🐰',panda:'🐼',lion:'🦁'};
  let token=localStorage.getItem(TOKEN_KEY)||'';
  let toastTimer=null;
  let activeAudio=null,speechRun=0;

  function escapeHTML(value){
    return String(value==null?'':value).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
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
  function playServerSpeech(text,run){
    return new Promise(resolve=>{
      if(run!==speechRun){resolve(false);return;}
      if(activeAudio){activeAudio.pause();activeAudio.src='';}
      const audio=new Audio('/api/tts?text='+encodeURIComponent(text));
      activeAudio=audio;audio.preload='auto';
      audio.onended=()=>resolve(true);audio.onerror=()=>{toast('语音暂时不可用，请稍后重试');resolve(false);};
      const promise=audio.play();if(promise&&promise.catch)promise.catch(()=>{toast('请再次点击播放按钮');resolve(false);});
    });
  }
  function speak(text,rate=.85){
    if(!text)return Promise.resolve(false);
    const run=++speechRun;
    if(activeAudio){activeAudio.pause();activeAudio.src='';activeAudio=null;}
    return new Promise(resolve=>{
      if(!('speechSynthesis'in window)||!window.SpeechSynthesisUtterance){playServerSpeech(text,run).then(resolve);return;}
      const synth=window.speechSynthesis;
      let started=false,finished=false;
      const done=value=>{if(finished)return;finished=true;clearTimeout(fallbackTimer);resolve(value);};
      const fallback=()=>{if(finished||run!==speechRun)return;finished=true;try{synth.cancel();}catch(e){}playServerSpeech(text,run).then(resolve);};
      const utterance=new SpeechSynthesisUtterance(text);utterance.lang='en-US';utterance.rate=rate;utterance.pitch=1.03;
      const voices=typeof synth.getVoices==='function'?synth.getVoices():[];utterance.voice=voices.find(v=>/^en[-_](US|GB)/i.test(v.lang))||voices.find(v=>/^en/i.test(v.lang))||null;
      utterance.onstart=()=>{started=true;clearTimeout(fallbackTimer);};
      utterance.onend=()=>done(true);utterance.onerror=fallback;
      const fallbackTimer=setTimeout(()=>{if(!started)fallback();},1200);
      try{if(synth.paused)synth.resume();if(synth.speaking||synth.pending)synth.cancel();synth.speak(utterance);}catch(e){fallback();}
    });
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
    if(!p.wrongBook||typeof p.wrongBook!=='object'||Array.isArray(p.wrongBook))p.wrongBook={};
    if(!Number.isFinite(Number(p.reviewCounter)))p.reviewCounter=0;
    return p;
  }
  function wrongEntries(progress,scope){
    const p=normalizeProgress(progress);
    return Object.values(p.wrongBook).filter(x=>x&&x.scope===scope).sort((a,b)=>String(b.lastWrong||'').localeCompare(String(a.lastWrong||'')));
  }
  function recordAttempt(progress,scope,id,payload,correct,userAnswer=''){
    const p=normalizeProgress(progress),key=scope+'|'+id,existing=p.wrongBook[key];
    if(correct){
      if(!existing)return{removed:false,streak:0};
      existing.streak=Number(existing.streak||0)+1;existing.attempts=Number(existing.attempts||0)+1;existing.lastAnswer=userAnswer;
      if(existing.streak>=10){delete p.wrongBook[key];return{removed:true,streak:10};}
      return{removed:false,streak:existing.streak};
    }
    p.wrongBook[key]={key,scope,id,payload:JSON.parse(JSON.stringify(payload||{})),streak:0,attempts:Number(existing&&existing.attempts||0)+1,lastAnswer:userAnswer,lastWrong:new Date().toISOString()};
    return{removed:false,streak:0};
  }
  function interleaveReviews(base,reviews,every=3){
    const result=Array.from(base||[]),items=Array.from(reviews||[]);
    items.forEach((item,index)=>result.splice(Math.min(result.length,(index+1)*every),0,item));
    return result;
  }
  window.KidsAPI={request,requireUser,listChildren,createChild,updateChild,deleteChild,loadProgress,saveProgress,event,switchLearningMode,switchToAdult,currentChildId,setCurrentChild,clearCurrentChild,selectedChild,avatar,shuffled,speak,today,normalizeProgress,wrongEntries,recordAttempt,interleaveReviews,escapeHTML,toast,showLoading,avatars:AVATARS};
})();

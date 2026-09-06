const __vite__mapDeps=(i,m=__vite__mapDeps,d=(m.f||(m.f=["assets/sql-wasm-browser-nIYtdfVT.js","assets/rolldown-runtime-Dqfqb5bO.js","assets/jszip.min-ukytsSc5.js"])))=>i.map(i=>d[i]);
import{a as e}from"./rolldown-runtime-Dqfqb5bO.js";import{a as t}from"./vendor-react-CF2eQL22.js";var n=`
CREATE TABLE col (
    id              integer primary key,
    crt             integer not null,
    mod             integer not null,
    scm             integer not null,
    ver             integer not null,
    dty             integer not null,
    usn             integer not null,
    ls              integer not null,
    conf            text not null,
    models          text not null,
    decks           text not null,
    dconf           text not null,
    tags            text not null
);
CREATE TABLE notes (
    id              integer primary key,
    guid            text not null,
    mid             integer not null,
    mod             integer not null,
    usn             integer not null,
    tags            text not null,
    flds            text not null,
    sfld            integer not null,
    csum            integer not null,
    flags           integer not null,
    data            text not null
);
CREATE TABLE cards (
    id              integer primary key,
    nid             integer not null,
    did             integer not null,
    ord             integer not null,
    mod             integer not null,
    usn             integer not null,
    type            integer not null,
    queue           integer not null,
    due             integer not null,
    ivl             integer not null,
    factor          integer not null,
    reps            integer not null,
    lapses          integer not null,
    left            integer not null,
    odue            integer not null,
    odid            integer not null,
    flags           integer not null,
    data            text not null
);
CREATE TABLE revlog (
    id              integer primary key,
    cid             integer not null,
    usn             integer not null,
    ease            integer not null,
    ivl             integer not null,
    lastIvl         integer not null,
    factor          integer not null,
    time            integer not null,
    type            integer not null
);
CREATE TABLE graves (
    usn             integer not null,
    oid             integer not null,
    type            integer not null
);
CREATE INDEX ix_notes_usn on notes (usn);
CREATE INDEX ix_cards_usn on cards (usn);
CREATE INDEX ix_revlog_usn on revlog (usn);
CREATE INDEX ix_cards_nid on cards (nid);
CREATE INDEX ix_cards_sched on cards (did, queue, due);
CREATE INDEX ix_revlog_cid on revlog (cid);
CREATE INDEX ix_notes_csum on notes (csum);
`,r={nextPos:1,estTimes:!0,activeDecks:[1],sortType:`noteFld`,timeLim:0,sortBackwards:!1,addToCur:!0,curDeck:1,newBury:!0,newSpread:0,dueCounts:!0,curModel:null,collapseTime:1200},i={1:{id:1,name:`Default`,replayq:!0,lapse:{leechFails:8,minInt:1,delays:[10],leechAction:0,mult:0},rev:{perDay:200,fuzz:.05,ivlFct:1,maxIvl:36500,ease4:1.3,bury:!1,minSpace:1},timer:0,maxTaken:60,usn:0,new:{perDay:20,delays:[1,10],separate:!0,ints:[1,4,7],initialFactor:2500,bury:!1,order:1},mod:0,autoplay:!0}},a=1607392319e3,o=1607392319001,s={id:a,name:`Basic`,type:0,mod:0,usn:0,sortf:0,did:1,tmpls:[{name:`Card 1`,ord:0,qfmt:`{{Front}}`,afmt:`{{FrontSide}}

<hr id="answer">

{{Back}}`,bqfmt:``,bafmt:``,did:null,bfont:``,bsize:0}],flds:[{name:`Front`,ord:0,sticky:!1,rtl:!1,font:`Arial`,size:20,description:``},{name:`Back`,ord:1,sticky:!1,rtl:!1,font:`Arial`,size:20,description:``}],css:`.card {
 font-family: arial;
 font-size: 20px;
 text-align: center;
 color: black;
 background-color: white;
}
`,latexPre:``,latexPost:``,latexsvg:!1,req:[[0,`any`,[0]]]},c={id:o,name:`Cloze`,type:1,mod:0,usn:0,sortf:0,did:1,tmpls:[{name:`Cloze`,ord:0,qfmt:`{{cloze:Text}}`,afmt:`{{cloze:Text}}<br>
{{Extra}}`,bqfmt:``,bafmt:``,did:null,bfont:``,bsize:0}],flds:[{name:`Text`,ord:0,sticky:!1,rtl:!1,font:`Arial`,size:20,description:``},{name:`Extra`,ord:1,sticky:!1,rtl:!1,font:`Arial`,size:20,description:``}],css:`.card {
 font-family: arial;
 font-size: 20px;
 text-align: center;
 color: black;
 background-color: white;
}
.cloze {
 font-weight: bold;
 color: blue;
}
`,latexPre:``,latexPost:``,latexsvg:!1,req:[[0,`any`,[0]]]},l=null;async function u(){if(l!==null)return l;let n=(await t(async()=>{let{default:t}=await import(`./sql-wasm-browser-nIYtdfVT.js`).then(t=>e(t.default,1));return{default:t}},__vite__mapDeps([0,1]))).default,r=(await t(async()=>{let{default:e}=await import(`./sql-wasm-Dqp2Kqtv.js`);return{default:e}},[])).default;return l=await n({locateFile:()=>r}),l}function d(e){let t=2166136261;for(let n=0;n<e.length;n++)t^=e.charCodeAt(n),t=t*16777619>>>0;return t&2147483647}function f(e){let t=new Set,n=/\{\{c(\d+)::/g,r;for(;(r=n.exec(e))!==null;)t.add(Number.parseInt(r[1],10)-1);return t.size===0&&t.add(0),[...t].sort((e,t)=>e-t)}function p(e){if(!e||e.length===0)return``;let t=e.map(e=>e.replace(/\s+/g,`_`)).filter(Boolean);return t.length===0?``:` ${t.join(` `)} `}async function m(l,m){if(l.length===0)throw Error(`buildApkg: cannot export an empty deck`);let h=await u(),g=(await t(async()=>{let{default:t}=await import(`./jszip.min-ukytsSc5.js`).then(t=>e(t.t(),1));return{default:t}},__vite__mapDeps([2,1]))).default,_=new h.Database;try{_.run(n);let e=Math.floor(Date.now()/1e3),t=Date.now(),u={1:{id:1,name:m.name,desc:m.description??``,extendRev:50,usn:0,collapsed:!1,browserCollapsed:!1,newToday:[0,0],revToday:[0,0],lrnToday:[0,0],timeToday:[0,0],dyn:0,extendNew:10,conf:1,mod:e,mid:0}},h={[String(a)]:s,[String(o)]:c};_.run(`INSERT INTO col (id, crt, mod, scm, ver, dty, usn, ls, conf, models, decks, dconf, tags)
             VALUES (1, ?, ?, ?, ?, 0, 0, 0, ?, ?, ?, ?, '{}')`,[e,e,e,11,JSON.stringify(r),JSON.stringify(h),JSON.stringify(u),JSON.stringify(i)]);let v=t,y=t,b=0;for(let t=0;t<l.length;t++){let n=l[t],r=n.type===`basic`,i=r?a:o,s=`${n.front}\u001f${n.back}`,c=n.front,u=d(n.front);_.run(`INSERT INTO notes (id, guid, mid, mod, usn, tags, flds, sfld, csum, flags, data)
                 VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, 0, '')`,[v,n.guid,i,e,p(n.tags),s,c,u]);let m=r?[0]:f(n.front);for(let t of m)_.run(`INSERT INTO cards (id, nid, did, ord, mod, usn, type, queue, due, ivl, factor, reps, lapses, left, odue, odid, flags, data)
                     VALUES (?, ?, ?, ?, ?, 0, 0, 0, ?, 0, 0, 0, 0, 0, 0, 0, 0, '')`,[y,v,1,t,e,b+1]),y+=1,b+=1;v+=1}let x=_.export(),S=new g;return S.file(`collection.anki2`,x),S.file(`media`,JSON.stringify({})),{blob:await S.generateAsync({type:`blob`}),filename:`${m.name.replace(/[^a-zA-Z0-9_\- ]/g,`_`).slice(0,80).trim().replace(/\s+/g,`_`)||`deck`}.apkg`,cardCount:b}}finally{_.close()}}export{m as buildApkg};
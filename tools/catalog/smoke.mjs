import fs from 'fs';
import { CARDS } from './monaco-suprem.js';
const data = JSON.parse(fs.readFileSync('./monaco-suprem.json','utf8'));
const byCard = new Map(data.cards.map(c=>[c.name,c]));
const resolve=(t,ns)=>{ if(ns.includes(t))return t; const h=ns.filter(n=>n.startsWith(t)); return h.length===1?h[0]:null; };
const lines = ['line x loc = 0     spacing = 0.02 tag = top',
               'implant boron dose=3e14 energy=70 pearson',
               'meth    grid.ox=0.03',
               'structure out=boron.str',
               'plot.1d x.ma=2.0 y.mi=14.0 y.max=20.0'];
for (const line of lines){
  const m=line.match(/^\s*%?([A-Za-z][\w.]*)/);
  const cn=resolve(m[1],CARDS); const c=byCard.get(cn);
  const toks=[...line.slice(m[0].length).matchAll(/([A-Za-z][\w./]*)\s*(=\s*\S+)?/g)].map(x=>x[1]);
  const res=toks.map(t=>{const r=resolve(t,c.params.map(p=>p.name)); return `${t}->${r}`;});
  console.log(`${m[1]} -> ${cn} | ${res.join(', ')}`);
}
console.log('\n--- sample hover: implant.dose ---');
console.log(byCard.get('implant').params.find(p=>p.name==='dose').doc);
console.log('\n--- sample hover: implant.pearson ---');
console.log(byCard.get('implant').params.find(p=>p.name==='pearson').doc);
console.log('\n--- sample card hover: diffuse ---');
console.log(byCard.get('diffuse').doc);

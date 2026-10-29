import {chromium} from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import http from 'node:http';
const root=path.resolve('dist');const output=path.resolve('../../artifacts/ui');fs.mkdirSync(output,{recursive:true});
const server=http.createServer((req,res)=>{const p=path.resolve(root,'.'+decodeURIComponent(req.url.split('?')[0]==='/'?'/index.html':req.url.split('?')[0]));if(!p.startsWith(root+path.sep)||!fs.existsSync(p)){res.writeHead(404);return res.end();}res.setHeader('Content-Type',p.endsWith('.js')?'application/javascript':p.endsWith('.css')?'text/css':'text/html');fs.createReadStream(p).pipe(res);});
await new Promise(r=>server.listen(0,'127.0.0.1',r));
const browser=await chromium.launch({channel:'msedge',headless:true});const page=await browser.newPage({viewport:{width:1500,height:950}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto(`http://127.0.0.1:${server.address().port}`);await page.getByRole('heading',{name:'数据清洗工作台',exact:true}).waitFor();await page.screenshot({path:path.join(output,'workspace-light.png')});
 await page.getByRole('button',{name:'切换明暗主题',exact:true}).click();await page.waitForFunction(()=>document.documentElement.dataset.theme==='dark');await page.screenshot({path:path.join(output,'workspace-dark.png')});
 await page.getByRole('button',{name:'数据预览',exact:true}).click();await page.locator('.ag-row').first().waitFor();await page.screenshot({path:path.join(output,'preview-dark.png')});
 await page.getByRole('button',{name:'统计分析',exact:true}).click();await page.locator('canvas').first().waitFor();await page.screenshot({path:path.join(output,'analysis-dark.png')});
 await page.getByRole('button',{name:'切换明暗主题',exact:true}).click();await page.getByRole('button',{name:'文件工作台',exact:true}).click();await page.getByRole('checkbox',{name:'选择当前全部输入',exact:true}).check();await page.getByRole('button',{name:'开始批量模拟'}).click();await page.getByRole('button',{name:'历史任务',exact:true}).click();await page.getByText('模拟格式错误，用于验证失败与重试反馈。').waitFor();await page.screenshot({path:path.join(output,'history.png')});
 await page.setViewportSize({width:1024,height:768});await page.getByRole('button',{name:'文件工作台',exact:true}).click();await page.screenshot({path:path.join(output,'workspace-small.png')});
 if(errors.length)throw Error(errors.join('\n'));console.log('PASS: six-page React prototype, theme, grid, charts, tasks, responsive screenshots; no JS exceptions');
}finally{await browser.close();server.close();}

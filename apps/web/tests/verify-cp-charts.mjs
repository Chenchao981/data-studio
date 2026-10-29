// Exercise the real local CP Cockpit, including rendered Plotly figures.
import {chromium} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
const [url,output]=process.argv.slice(2);
await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true,channel:'msedge'});
let page;
try {
 page=await browser.newPage({viewport:{width:1600,height:1100}});
 await page.goto(url);await page.getByRole('button',{name:'绘制图形',exact:false}).waitFor({timeout:90000});
 await writeFile(output+'/initial.txt',await page.locator('body').innerText());
 await page.getByRole('button',{name:'绘制图形',exact:false}).click();
 await page.locator('.js-plotly-plot').first().waitFor({timeout:90000});
 await page.getByRole('tab',{name:'💾 数据表'}).click();
 await page.getByText('为保持前端流畅，页面预览最多显示前 5000 行；下载/原始文件仍保留完整数据。',{exact:true}).waitFor({timeout:180000});
 const tabs=page.getByRole('tab'),names=await tabs.allTextContents(),visited=[];
 for(let i=0;i<names.length;i++){
  await tabs.nth(i).click();
  const panel=page.getByRole('tabpanel',{includeHidden:false});
  await panel.waitFor();
  const errors=await page.locator('[data-testid="stException"]').allTextContents();
  if(errors.length)throw Error(errors.join('\n'));
  const text=await panel.innerText();
  if(!text.trim())throw Error('Empty tab '+names[i]);
  if(text.includes('was removed'))throw Error('Incompatible chart API: '+names[i]);
  visited.push({name:names[i],figures:await panel.locator('.js-plotly-plot').count(),images:await panel.locator('img').count(),text:text.slice(0,1500)});
  await page.screenshot({path:output+'/tab-'+i+'.png',fullPage:true});
 }
 if(!visited.some(v=>v.figures>0))throw Error('No rendered plots');
 for(const [all,label,desired] of [['全选参数','筛选参数','VTH'],['全选片号','筛选片号',' / W2']]){
  await page.getByText(all,{exact:true}).click();
  const input=page.getByRole('combobox',{name:label,exact:true});await input.waitFor();
  const block=page.getByTestId('stMultiSelect').filter({has:input});
  await input.fill(desired);
  const option=page.getByRole('option',label==='筛选片号'?{name:/\/ W2$/}:{name:desired,exact:true});
  const value=(await option.innerText()).trim();await option.click();
  await input.press('Escape');
  await block.getByRole('button',{name:'Remove '+value,exact:true}).waitFor();
  const removeNames=await block.getByRole('button',{name:/^Remove /}).evaluateAll(es=>es.map(e=>e.getAttribute('aria-label')));
  for(const name of removeNames){
   if(name!=='Remove '+value)await block.getByRole('button',{name,exact:true}).click();
  }
  await page.getByText(label==='筛选参数'?'当前：1/1 个批次，25/25 片，1/13 个参数。':'当前：1/1 个批次，1/25 片，1/13 个参数。',{exact:true}).waitFor();
  await page.waitForFunction(()=>document.querySelector('[data-testid="stApp"]')?.getAttribute('data-test-script-state')==='notRunning');
 }
 await page.getByText('当前：1/1 个批次，1/25 片，1/13 个参数。',{exact:true}).waitFor();
 // Streamlit batches native widget changes. Commit the editing focus and wait
 // for that UI transaction before the separate explicit draw operation.
 await page.getByText('CP 交互分析前端 · 复用 cleaned / yield / spec 标准 CSV · 服务研发、质量和工艺分析',{exact:true}).click();
 await page.waitForTimeout(1000);
 await page.getByRole('button',{name:'绘制图形',exact:false}).click();
 await page.getByRole('tab',{name:'💾 数据表'}).click();
 await page.getByText('为保持前端流畅，页面预览最多显示前 5000 行；下载/原始文件仍保留完整数据。',{exact:true}).waitFor({timeout:90000});
 await page.getByRole('tab',{name:'⚠ Cpk/超限'}).click();
 const downloadPromise=page.waitForEvent('download');
 await page.getByRole('button',{name:'⬇ 导出 Cpk/超限表',exact:true}).click();
 const download=await downloadPromise;await download.saveAs(output+'/filtered-cpk.csv');
 await page.screenshot({path:output+'/filtered-cpk.png',fullPage:true});
 await writeFile(output+'/evidence.json',JSON.stringify({url,visited,filtered:'Wafer 2 / VTH',download:download.suggestedFilename()},null,2));
 console.log(JSON.stringify(visited.map(({name,figures})=>({name,figures}))));
} catch(error){
 if(page){await writeFile(output+'/failure-body.txt',await page.locator('body').innerText());await page.screenshot({path:output+'/failure.png'});}
 throw error;
} finally {await browser.close();}

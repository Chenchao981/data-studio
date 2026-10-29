// Real CP viewer: default combined plot, draft/apply, every optional chart/export.
// Uses actual CSV filters; no synthetic 25-wafer assumptions.
import {chromium,expect} from '@playwright/test';
import {mkdir,writeFile} from 'node:fs/promises';
import {performance} from 'node:perf_hooks';
const [url,output]=process.argv.slice(2);
if(!/^http:\/\/127\.0\.0\.1:\d+$/.test(url||''))throw Error('Expected owned local CP viewer URL');
await mkdir(output,{recursive:true});
const browser=await chromium.launch({headless:true,channel:'msedge'});
let page;
const combined='📊 箱线散点图';
const optional=['🎯 BIN总览','📋 Pareto','📈 良率趋势','📊 箱体图','🔵 散点图','🗺️ Wafer Mapping','🎯 区域分析','🔍 失效叠加','📊 Wafer Summary','⚠ Cpk/超限','💾 数据表'];
try {
 page=await browser.newPage({viewport:{width:1600,height:1100},acceptDownloads:true});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 async function idle(){
  await expect.poll(()=>page.locator('[data-testid="stApp"]').getAttribute('data-test-script-state'),{timeout:180000}).toBe('notRunning');
  const exceptions=await page.getByTestId('stException').allTextContents();
  if(exceptions.length)throw Error(exceptions.join('\n'));
 }
 async function tabs(expected){await expect.poll(()=>page.getByRole('tab').allTextContents(),{timeout:180000}).toEqual(expected);await idle();}
 async function redraw(){await page.getByRole('button',{name:'重新绘制',exact:false}).click();}
 const began=performance.now();
 await page.goto(url);
 await page.locator('[role="tab"],[data-testid="stException"]').first().waitFor({timeout:90000});
 await idle();await tabs([combined]);
 await expect(page.getByTestId('stImage').locator('img')).toHaveCount(1,{timeout:90000});
 await expect(page.locator('.js-plotly-plot')).toHaveCount(0);
 const initialMs=performance.now()-began;
 await expect(page.getByRole('checkbox',{name:'全选参数',exact:true})).not.toBeChecked();
 await writeFile(output+'/initial.txt',await page.locator('body').innerText());
 const image=page.getByTestId('stImage').locator('img').first();
 const focusedSrc=await image.getAttribute('src');
 await writeFile(output+'/combined-focus.png',await (await page.request.get(new URL(focusedSrc,url).href)).body());
 await page.screenshot({path:output+'/default.png',fullPage:true});
 await page.getByText('显示完整纵轴范围',{exact:true}).click();
 await expect(page.getByRole('checkbox',{name:'显示完整纵轴范围',exact:true})).toBeChecked();
 await expect(image).not.toHaveAttribute('src',focusedSrc,{timeout:90000});await idle();
 await writeFile(output+'/combined-full.png',await (await page.request.get(new URL(await image.getAttribute('src'),url).href)).body());
 const extra=page.getByRole('combobox',{name:'其他图形',exact:true});
 for(const label of optional){
  await extra.fill(label);await page.getByRole('option',{name:label,exact:true}).click();await extra.press('Escape');
  await idle();await tabs([combined]);
  await expect(page.locator('.js-plotly-plot')).toHaveCount(0);
 }
 await page.screenshot({path:output+'/draft-before-redraw.png',fullPage:true});
 const allBegan=performance.now();await redraw();await tabs([combined,...optional]);
 await expect(page.locator('.js-plotly-plot').first()).toBeAttached({timeout:90000});await idle();
 const allSelectedMs=performance.now()-allBegan;
 const visited=[];
 for(const name of [combined,...optional]){
  await page.getByRole('tab',{name,exact:true}).click();
  const panel=page.getByRole('tabpanel',{includeHidden:false});
  await expect(panel).toBeVisible();const text=await panel.innerText();
  if(!text.trim())throw Error('Empty chart panel '+name);
  visited.push({name,figures:await panel.locator('.js-plotly-plot').count(),images:await panel.locator('img').count(),text:text.slice(0,2000)});
  await page.screenshot({path:output+'/tab-'+(visited.length-1)+'.png',fullPage:true});
 }
 await page.getByRole('tab',{name:'⚠ Cpk/超限',exact:true}).click();
 const downloaded=page.waitForEvent('download');await page.getByRole('button',{name:'⬇ 导出 Cpk/超限表',exact:true}).click();
 await (await downloaded).saveAs(output+'/cpk.csv');
 const extraBlock=page.getByTestId('stMultiSelect').filter({has:extra});
 for(const label of optional){await extraBlock.getByRole('button',{name:'Remove '+label,exact:true}).click();await idle();}
 await tabs([combined,...optional]);
 await redraw();await tabs([combined]);await expect(page.locator('.js-plotly-plot')).toHaveCount(0);
 await expect(page.getByTestId('stImage').locator('img')).toHaveCount(1);
 const parameter=page.getByRole('combobox',{name:'筛选参数',exact:true});
 const block=page.getByTestId('stMultiSelect').filter({has:parameter});
 const first=(await block.getByRole('button',{name:/^Remove /}).getAttribute('aria-label')).replace(/^Remove /,'');
 await parameter.click();const names=await page.getByRole('option').allTextContents();
 const choices=names.map(s=>s.trim());const next=choices.find(s=>s==='VTH1')||choices.find(s=>s&&s!==first);
 if(!next)throw Error('Requires at least two real parameters');
 await page.getByRole('option',{name:next,exact:true}).click();await parameter.press('Escape');await idle();
 await block.getByRole('button',{name:'Remove '+first,exact:true}).click();await idle();
 const parameterMetric=page.getByTestId('stMetric').filter({has:page.getByText('参数',{exact:true})});
 await expect(parameterMetric).toContainText(first);
 await redraw();await idle();await expect(parameterMetric).toContainText(next);
 await page.screenshot({path:output+'/redrawn-parameter.png',fullPage:true});
 if(errors.length)throw Error(errors.join('\n'));
 await writeFile(output+'/evidence.json',JSON.stringify({status:'PASS',url,initialMs,allSelectedMs,defaultTabs:[combined],defaultParameters:1,
  optionalDraftDoesNotRender:true,removalRequiresRedraw:true,parameterRequiresRedraw:true,visited,exported:'cpk.csv',parameters:{first,next}},null,2));
 console.log(JSON.stringify({status:'PASS',initialMs,allSelectedMs,visited:visited.map(({name,figures,images})=>({name,figures,images}))}));
}catch(error){
 if(page){await writeFile(output+'/failure-body.txt',await page.locator('body').innerText());await page.screenshot({path:output+'/failure.png',fullPage:true});}
 throw error;
}finally{await browser.close();}

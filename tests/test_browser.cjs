const { chromium } = require('playwright');
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const server = http.createServer((request,response)=>{
  const file = path.join(root, new URL(request.url,'http://localhost').pathname);
  if(!file.startsWith(root+path.sep) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
    response.writeHead(404);response.end();return;
  }
  const mime={'.html':'text/html; charset=utf-8','.css':'text/css','.js':'text/javascript','.sh':'text/plain','.ps1':'text/plain'};
  response.setHeader('Content-Type',mime[path.extname(file)]||'application/octet-stream');
  fs.createReadStream(file).pipe(response);
});
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base='http://127.0.0.1:'+server.address().port;
  const browser = await chromium.launch();
  fs.mkdirSync(path.join(root,'.test-artifacts'),{recursive:true});
  try{
    for(const width of [1280,390]){
      const context=await browser.newContext({viewport:{width,height:900},permissions:['clipboard-read','clipboard-write']});
      const page=await context.newPage();
      const errors=[];
      page.on('pageerror',error=>errors.push(error.message));
      for(const lang of ['sv','en']){
        await page.goto(`${base}/download_${lang}.html`);
        assert.equal(await page.locator('html').getAttribute('lang'),lang);
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
        await page.locator('#os').selectOption('windows');
        await page.locator('#version').selectOption('main');
        assert.match(await page.locator('#command').textContent(),/-Ref main/);
        await page.locator('#copy').click();
        assert.match(await page.locator('#status').textContent(),/kopierades|copied/);
        const [download]=await Promise.all([page.waitForEvent('download'),page.locator('#installer').click()]);
        assert.equal(download.suggestedFilename(),'runcom-install.ps1');
        assert.match(fs.readFileSync(await download.path(),'utf8'),/^param\(/);
        await page.locator('#os').selectOption('arch');
        assert.match(await page.locator('#command').textContent(),/--ref main/);
        await page.locator('#version').selectOption('release');
        assert.ok(!(await page.locator('#command').textContent()).includes('--ref main'));
        await page.screenshot({path:path.join(root,`.test-artifacts/${lang}-${width}.png`),fullPage:true});
      }
      assert.deepEqual(errors,[]);
      await context.close();
    }
    console.log('Real Chromium: responsive layout, both languages, version selection, clipboard and script download PASS');
  }finally{await browser.close();server.close();}
})().catch(error=>{console.error(error);server.close();process.exit(1);});

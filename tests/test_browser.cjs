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
        await page.screenshot({path:path.join(root,`.test-artifacts/${lang}-${width}.png`),fullPage:true});
        assert.equal(await page.locator('html').getAttribute('lang'),lang);
        assert.equal(await page.locator('#version').count(),0);
        assert.ok(!(await page.locator('#command').textContent()).includes('ref main'));
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
        await page.locator('#os').selectOption('windows');
        await page.locator('#copy').click();
        await page.waitForFunction(()=>/kopierades|copied/.test(document.getElementById('status').textContent));
        const [download]=await Promise.all([page.waitForEvent('download'),page.locator('#installer').click()]);
        assert.equal(download.suggestedFilename(),'runcom-install.ps1');
        const releaseInstaller=fs.readFileSync(await download.path(),'utf8');
        assert.ok(releaseInstaller.includes(`-Language ${lang}`));
        assert.ok(!releaseInstaller.includes('-Ref main'));
        await page.locator('#os').selectOption('arch');
        assert.ok(!(await page.locator('#command').textContent()).includes('--ref main'));
        await page.screenshot({path:path.join(root,`.test-artifacts/${lang}-${width}.png`),fullPage:true});
        for(const distro of ['arch','ubuntu','debian','mint','fedora','opensuse','alpine']) {
          await page.locator('#uninstall-os').selectOption(distro);
          assert.ok((await page.locator('#uninstall-tools').textContent()).length>10);
          assert.match(await page.locator('#uninstall-command').textContent(),/bash runcom-uninstall.sh/);
          assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
        }
        await page.locator('#uninstall-os').selectOption('windows');
        const [removeDownload]=await Promise.all([page.waitForEvent('download'),page.locator('#uninstaller').click()]);
        assert.equal(removeDownload.suggestedFilename(),'runcom-uninstall.ps1');
        assert.ok(fs.readFileSync(await removeDownload.path(),'utf8').includes('[switch]$Yes'));
        await page.locator('#uninstall-copy').click();
        await page.waitForFunction(()=>/kopierades|copied/.test(document.getElementById('uninstall-status').textContent));
        await page.screenshot({path:path.join(root,`.test-artifacts/uninstall-${lang}-${width}.png`),fullPage:true});
        await page.getByRole('link',{name:lang==='sv'?'Hjälp':'Help',exact:true}).click();
        assert.ok(page.url().endsWith(lang==='sv'?'/help.html':'/help_en.html'));
        assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
        assert.equal(await page.locator('.guide-section').count(),9);
        assert.equal(await page.locator('#troubleshooting details').count(),5);
        const question = page.locator('#troubleshooting details').first();
        await question.locator('summary').click();
        assert.equal(await question.evaluate(node=>node.open),true);
        await page.screenshot({path:path.join(root,`.test-artifacts/help-${lang}-${width}.png`),fullPage:true});
      }
      await page.goto('file://' + path.join(root,'help.html'));
      assert.equal(await page.locator('#troubleshooting details').count(),5);
      assert.equal(await page.locator('body').evaluate(node=>getComputedStyle(node).backgroundColor),'rgb(12, 18, 28)');
      assert.deepEqual(errors,[]);
      await context.close();
    }
    console.log('Real Chromium: responsive layout, both languages, latest-release downloads and clipboard PASS');
  }finally{await browser.close();server.close();}
})().catch(error=>{console.error(error);server.close();process.exit(1);});

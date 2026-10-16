const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const script = fs.readFileSync(path.join(__dirname, '../download.js'), 'utf8');
(async()=>{
  for (const lang of ['sv','en']) {
    for (const platform of ['Linux','Win32','MacIntel']) {
      const elements = {};
      for (const id of ['os','version','status','prerequisites','command','installer','launch','copy']) {
        elements[id] = {value:id === 'version'?'main':'',textContent:'',events:{},addEventListener(event,fn){this.events[event]=fn;}};
      }
      let clipboard = '';
      const context = {document:{documentElement:{lang},getElementById:id=>elements[id]},navigator:{platform,clipboard:{writeText:async value=>{clipboard=value;}}}};
      vm.runInNewContext(script, context);
      assert.equal(elements.os.value, platform==='Win32'?'windows':platform==='MacIntel'?'mac':'linux');
      for (const os of ['arch','ubuntu','fedora','mac','windows','linux']) {
        for (const version of ['main','release']) {
          elements.os.value=os; elements.version.value=version; elements.os.events.change();
          assert.ok(elements.prerequisites.textContent.length>10);
          assert.equal(elements.installer.href,os==='windows'?'install.ps1':'install.sh');
          const command = elements.command.textContent;
          assert.match(command,/raw\.githubusercontent\.com\/tvrdprijatelj\/runcom\/main\/install\./);
          assert.equal(command.includes(os==='windows'?'-Ref main':'--ref main'),version==='main');
          if(os==='windows') assert.ok(command.includes('.\\runcom-install.ps1'));
          await elements.copy.events.click();
          assert.equal(clipboard,command);
        }
      }
      context.navigator.clipboard.writeText=async()=>{throw Error('denied');};
      await elements.copy.events.click();
      assert.match(elements.status.textContent,/manuellt|manually/);
    }
  }
  console.log('Download flow: all platforms, languages, versions and clipboard fallback PASS');
})().catch(error=>{console.error(error);process.exit(1);});

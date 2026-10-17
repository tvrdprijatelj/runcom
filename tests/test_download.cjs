const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const script = fs.readFileSync(path.join(__dirname, '../download.js'), 'utf8');
(async()=>{
  for (const lang of ['sv','en']) {
    for (const platform of ['Linux','Win32','MacIntel']) {
      const elements = {};
      for (const id of ['os','version','status','prerequisites','command','installer','launch','copy','uninstall-os','uninstaller','uninstall-command','uninstall-copy','uninstall-status','uninstall-custom','uninstall-distro','uninstall-menu','uninstall-terminal','uninstall-tools','uninstall-tools-note']) {
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
          assert.equal(elements.installer.href,`install_${lang}.${os==='windows'?'ps1':'sh'}`);
          const command = elements.command.textContent;
          assert.ok(command.includes(os==='windows'?`-Language ${lang}`:`--lang ${lang}`));
          assert.match(command,/raw\.githubusercontent\.com\/tvrdprijatelj\/runcom\/main\/install\./);
          assert.equal(command.includes(os==='windows'?'-Ref main':'--ref main'),version==='main');
          if(os==='windows') assert.ok(command.includes('.\\runcom-install.ps1'));
          await elements.copy.events.click();
          assert.equal(clipboard,command);
        }
      }
      for (const selected of ['arch','ubuntu','debian','mint','fedora','opensuse','alpine','linux','mac','windows']) {
        elements['uninstall-os'].value = selected;
        elements['uninstall-os'].events.change();
        const win = selected === 'windows';
        assert.ok(elements['uninstall-menu'].textContent.length>20);
        assert.ok(elements['uninstall-terminal'].textContent.length>20);
        const managers={arch:'pacman',ubuntu:'apt',debian:'apt',mint:'apt',fedora:'dnf',opensuse:'zypper',alpine:'apk'};
        if(managers[selected]) assert.ok(elements['uninstall-tools'].textContent.includes(managers[selected]));
        assert.equal(elements.uninstaller.href, `uninstall.${win ? 'ps1' : 'sh'}`);
        assert.equal(elements.uninstaller.download, `runcom-uninstall.${win ? 'ps1' : 'sh'}`);
        const command = elements['uninstall-command'].textContent;
        assert.match(command, /raw\.githubusercontent\.com\/tvrdprijatelj\/runcom\/main\/uninstall\./);
        assert.ok(command.includes(win ? 'powershell -ExecutionPolicy Bypass' : 'bash runcom-uninstall.sh'));
        await elements['uninstall-copy'].events.click();
        assert.equal(clipboard, command);
        assert.match(elements['uninstall-custom'].textContent, win ? /-InstallDir/ : /RUNCOM_INSTALL_DIR/);
      }
      context.navigator.clipboard.writeText=async()=>{throw Error('denied');};
      await elements.copy.events.click();
      assert.match(elements.status.textContent,/manuellt|manually/);
      await elements['uninstall-copy'].events.click();
      assert.match(elements['uninstall-status'].textContent,/manuellt|manually/);
    }
  }
  console.log('Download flow: all platforms, languages, versions and clipboard fallback PASS');
})().catch(error=>{console.error(error);process.exit(1);});

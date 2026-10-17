"use strict";
const sv = document.documentElement.lang === 'sv';
const text = (a,b) => sv ? a : b;
const os = document.getElementById('os');
const version = document.getElementById('version');
const status = document.getElementById('status');
const prerequisites = {
  arch:'sudo pacman -Syu --needed python tk curl',
  ubuntu:'sudo apt update && sudo apt install python3 python3-venv python3-tk curl',
  fedora:'sudo dnf install python3 python3-tkinter python3-pip curl',
  mac:text('Installera Python med Tcl/Tk från https://www.python.org/downloads/macos/', 'Install Python with Tcl/Tk from https://www.python.org/downloads/macos/'),
  windows:text('Installera Python från https://www.python.org/downloads/windows/ — välj Tcl/Tk och Python launcher.', 'Install Python from https://www.python.org/downloads/windows/ — include Tcl/Tk and Python launcher.'),
  linux:text('Installera Python 3.8+, Tkinter, venv och curl via din pakethanterare.', 'Install Python 3.8+, Tkinter, venv and curl using your package manager.')
};
function updateOS(){
  const win = os.value === 'windows';
  const main = version.value === 'main';
  document.getElementById('prerequisites').textContent = prerequisites[os.value];
  const base = 'https://raw.githubusercontent.com/tvrdprijatelj/runcom/main/';
  document.getElementById('command').textContent = win
    ? `Invoke-WebRequest -UseBasicParsing '${base}install.ps1' -OutFile runcom-install.ps1\npowershell -ExecutionPolicy Bypass -File .\\runcom-install.ps1${main ? ' -Ref main' : ''} -Language ${sv ? 'sv' : 'en'}`
    : `curl -fL '${base}install.sh' -o runcom-install.sh\nbash runcom-install.sh${main ? ' --ref main' : ''} --lang ${sv ? 'sv' : 'en'}`;
  const link = document.getElementById('installer');
  link.href = `install_${sv ? 'sv' : 'en'}.${win ? 'ps1' : 'sh'}`;
  link.textContent = text('Ladda ner installerare (main)', 'Download installer (main)');
  link.download = win ? 'runcom-install.ps1' : 'runcom-install.sh';
  document.getElementById('launch').textContent = win
    ? text('Sök efter Runcom i Start-menyn eller använd skrivbordsgenvägen. Installationen visar också ett startkommando.', 'Find Runcom in the Start menu or use the desktop shortcut. The installer also prints a launch command.')
    : text('Linux: sök efter Runcom i programmenyn. Installationen visar även startkommandot. Standardplats: ~/.local/share/runcom/runcom.', 'Linux: find Runcom in the application menu. The installer also prints a launch command. Default location: ~/.local/share/runcom/runcom.');
  status.textContent = main
    ? text('Valt: aktuell källkod på main, inklusive de nya rättningarna.', 'Selected: current source on main, including the latest fixes.')
    : text('Valt: senaste publicerade release. Den kan vara äldre än rättningarna på main.', 'Selected: latest published release. It may predate fixes on main.');
}
const platform = navigator.userAgentData?.platform || navigator.platform || '';
os.value = /Win/i.test(platform) ? 'windows' : /Mac/i.test(platform) ? 'mac' : 'linux';
os.addEventListener('change', updateOS);
version.addEventListener('change', updateOS);
updateOS();
document.getElementById('copy').addEventListener('click', async()=>{
  try {
    await navigator.clipboard.writeText(document.getElementById('command').textContent);
    status.textContent = text('Kommandona kopierades.', 'Commands copied.');
  } catch {
    status.textContent = text('Markera och kopiera kommandona manuellt.', 'Select and copy the commands manually.');
  }
});

const uninstallOS = document.getElementById('uninstall-os');
uninstallOS.value = /Win/i.test(platform) ? 'windows' : /Mac/i.test(platform) ? 'mac' : 'linux';
function updateUninstall(){
  const win = uninstallOS.value === 'windows';
  const extension = win ? 'ps1' : 'sh';
  const link = document.getElementById('uninstaller');
  link.href = `uninstall.${extension}`;
  link.download = `runcom-uninstall.${extension}`;
  link.textContent = text('Ladda ner avinstallationsskript', 'Download uninstaller');
  const base = 'https://raw.githubusercontent.com/tvrdprijatelj/runcom/main/';
  document.getElementById('uninstall-command').textContent = win
    ? `Invoke-WebRequest -UseBasicParsing '${base}uninstall.ps1' -OutFile runcom-uninstall.ps1\npowershell -ExecutionPolicy Bypass -File .\\runcom-uninstall.ps1`
    : `curl -fL '${base}uninstall.sh' -o runcom-uninstall.sh\nbash runcom-uninstall.sh`;
  document.getElementById('uninstall-custom').textContent = win
    ? 'powershell -ExecutionPolicy Bypass -File .\\runcom-uninstall.ps1 -InstallDir "C:\\path\\to\\Runcom"'
    : 'RUNCOM_INSTALL_DIR="/path/to/runcom" bash runcom-uninstall.sh';
  document.getElementById('uninstall-status').textContent = '';
}
uninstallOS.addEventListener('change', updateUninstall);
updateUninstall();
document.getElementById('uninstall-copy').addEventListener('click', async()=>{
  const result = document.getElementById('uninstall-status');
  try {
    await navigator.clipboard.writeText(document.getElementById('uninstall-command').textContent);
    result.textContent = text('Kommandona kopierades.', 'Commands copied.');
  } catch {
    result.textContent = text('Markera och kopiera kommandona manuellt.', 'Select and copy the commands manually.');
  }
});

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
    ? `Invoke-WebRequest -UseBasicParsing '${base}install.ps1' -OutFile runcom-install.ps1\npowershell -ExecutionPolicy Bypass -File .\\runcom-install.ps1${main ? ' -Ref main' : ''}`
    : `curl -fL '${base}install.sh' -o runcom-install.sh\nbash runcom-install.sh${main ? ' --ref main' : ''}`;
  const link = document.getElementById('installer');
  link.href = win ? 'install.ps1' : 'install.sh';
  link.download = win ? 'runcom-install.ps1' : 'runcom-install.sh';
  document.getElementById('launch').textContent = win
    ? text('Starta med genvägen Runcom på skrivbordet. Installationen visar även ett startkommando.', 'Launch with the Runcom desktop shortcut. The installer also prints a launch command.')
    : text('Installationen visar startkommandot. Standardplats: ~/.local/share/runcom/runcom.', 'The installer prints the launch command. Default location: ~/.local/share/runcom/runcom.');
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
